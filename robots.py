#!/usr/bin/env python3
"""
Shared helper: may this client fetch a page, and may an AI use it?

Reads a site's robots.txt by the rules of RFC 9309 - User-agent groups,
Allow / Disallow with the `*` and `$` wildcards, the longest matching rule
winning and Allow winning a tie - and its Content-Signal lines
(https://contentsignals.org/), e.g. `Content-Signal: search=yes, ai-input=no`,
which say what fetched content may be used for. Only `ai-input` is acted on:
it covers feeding a page into an AI model to answer a question or write a
summary, which is what this repo's agents do with fetched pages.

Python's own urllib.robotparser isn't used: it takes the first matching rule
rather than the longest (so `Allow: /` before `Disallow: /search` would allow
/search) and it ignores Content-Signal.

Used by url_content.py's --respect-robots. Not a CLI - this module is
imported, not run.
"""

import re
from urllib.parse import urlsplit, urlunsplit

import requests

TIMEOUT_SECONDS = 10
# RFC 9309: crawlers must parse at least 500 KiB; anything after that may be ignored.
MAX_BYTES = 500 * 1024


def parse(text):
    """Parse robots.txt text into (groups, global_signals).

    Each group is {"agents": [lowercased names], "rules": [(allow, pattern)],
    "signals": [(path_or_None, {key: value})]}. Consecutive User-agent lines
    share one group. A Content-Signal line before any User-agent line
    applies to every client and goes into global_signals.
    """
    groups, global_signals = [], []
    current, in_agents = None, False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if current is None or not in_agents:
                current = {"agents": [], "rules": [], "signals": []}
                groups.append(current)
            current["agents"].append(value.lower())
            in_agents = True
            continue
        in_agents = False
        if field in ("allow", "disallow"):
            # An empty Disallow means "nothing is disallowed": no rule at all.
            if current is not None and value:
                current["rules"].append((field == "allow", value))
        elif field == "content-signal":
            signal = parse_signal(value)
            if signal[1]:
                (current["signals"] if current is not None else global_signals).append(signal)
    return groups, global_signals


def parse_signal(value):
    """`[/path] key=value, key=value` -> (path or None, {key: value}), lowercased."""
    path = None
    first, _, rest = value.partition(" ")
    if first.startswith("/"):
        path, value = first, rest
    pairs = {}
    for item in re.split(r"[,\s]+", value):
        key, sep, val = item.partition("=")
        if sep and key:
            pairs[key.strip().lower()] = val.strip().lower()
    return path, pairs


def matching_groups(groups, token):
    """The groups for `token` (a product token, e.g. online-search-url-content).

    A group naming the token (case-insensitively) wins; otherwise the `*`
    groups apply; with neither, none do (everything is allowed).
    """
    token = token.lower()
    named = [g for g in groups if token in g["agents"]]
    if named:
        return named
    return [g for g in groups if "*" in g["agents"]]


def _pattern_regex(pattern):
    """A robots.txt path pattern as a regex: `*` is any run, a final `$` anchors the end."""
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""))


def path_matches(pattern, path):
    return _pattern_regex(pattern).match(path) is not None


def url_path(url):
    """The path-plus-query a robots.txt rule is matched against ("/" if empty)."""
    parts = urlsplit(url)
    path = parts.path or "/"
    return path + ("?" + parts.query if parts.query else "")


def is_allowed(groups, token, path):
    """Whether `path` may be fetched: the longest matching rule wins, Allow wins a tie."""
    if path == "/robots.txt":
        return True
    best_len, allowed = -1, True
    for group in matching_groups(groups, token):
        for allow, pattern in group["rules"]:
            if path_matches(pattern, path):
                length = len(pattern)
                if length > best_len or (length == best_len and allow):
                    best_len, allowed = length, allow
    return allowed


def ai_input_allowed(groups, global_signals, token, path):
    """False if the Content-Signal that applies to `path` says ai-input=no.

    Signals come from the groups matching `token` plus any global ones. A
    path-scoped signal beats an unscoped one, and a longer path a shorter
    one. No ai-input signal at all means no stated preference (allowed).
    """
    best_len, value = -1, None
    signals = list(global_signals)
    for group in matching_groups(groups, token):
        signals.extend(group["signals"])
    for scope, pairs in signals:
        if "ai-input" not in pairs:
            continue
        if scope is not None and not path_matches(scope, path):
            continue
        length = len(scope) if scope else 0
        if length >= best_len:
            best_len, value = length, pairs["ai-input"]
    return value != "no"


def robots_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


def fetch(url, user_agent, timeout=TIMEOUT_SECONDS):
    """Fetch the robots.txt for `url`'s site.

    Returns (text, problem): text is the file (empty when the site has none),
    problem is None, or a reason the file couldn't be read. Following RFC
    9309, a 4xx (no file) allows everything, while a 5xx or a connection
    failure means the site can't be assumed to allow anything.
    """
    try:
        response = requests.get(
            robots_url(url), headers={"User-Agent": user_agent},
            timeout=timeout, allow_redirects=True,
        )
    except requests.RequestException as exc:
        return None, f"its robots.txt couldn't be fetched ({exc.__class__.__name__})"
    if 400 <= response.status_code < 500:
        return "", None
    if response.status_code >= 500:
        return None, f"its robots.txt returned HTTP {response.status_code}"
    return response.content[:MAX_BYTES].decode("utf-8", errors="replace"), None


def check(url, user_agent, token, timeout=TIMEOUT_SECONDS):
    """None if `url` may be fetched and given to an AI, else the reason it may not.

    `user_agent` is the full header sent when fetching robots.txt; `token`
    is the product token matched against its User-agent groups.
    """
    host = urlsplit(url).netloc
    text, problem = fetch(url, user_agent, timeout)
    if problem:
        return f"{host}: {problem}, which counts as a full disallow"
    groups, global_signals = parse(text)
    path = url_path(url)
    if not is_allowed(groups, token, path):
        return f"{host}'s robots.txt disallows {path} for {token}"
    if not ai_input_allowed(groups, global_signals, token, path):
        return f"{host}'s robots.txt opts out of AI input (Content-Signal: ai-input=no)"
    return None
