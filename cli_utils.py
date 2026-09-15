#!/usr/bin/env python3
"""
Shared helpers for the command-line entry-point scripts in this repo:
uniform error exits, a couple of argparse ``type`` callables, ``.env``
loading, and the result-list formatting/printing shared by the
``web_search_*.py`` scripts that return a flat list of results.

Not a CLI itself - this module is imported, not run.
"""

import argparse
import json
import os
import sys

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_dotenv(path=ENV_FILE):
    """Populate os.environ from a simple KEY=VALUE .env file.

    Existing environment variables are never overwritten, so real env
    vars always take precedence over .env values. Missing files are
    silently ignored.
    """
    try:
        with open(path, encoding="utf-8") as env_file:
            lines = env_file.readlines()
    except FileNotFoundError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def format_result(row):
    """Render a {rank, title, url, snippet} record as a text block."""
    lines = [
        f"{row['rank']}. {row['title']}",
        f"   {row['url']}",
        f"   {row['snippet']}",
    ]
    return "\n".join(lines)


def print_results(rows, as_json):
    """Print a list of {rank, title, url, snippet} records.

    With ``as_json``, prints the list as a JSON array; otherwise prints
    ``"No results found."`` for an empty list, or each row through
    ``format_result()`` separated by a blank line.
    """
    if as_json:
        print(json.dumps(rows, indent=2))
        return

    if not rows:
        print("No results found.")
        return

    for row in rows:
        print(format_result(row))
        print()


def die(message, as_json=False):
    """Print an error to stderr and exit the process non-zero.

    With ``as_json`` the error is emitted as ``{"error": message}`` so an
    agent parsing the script's output gets structured data; otherwise it is
    a plain ``Error: <message>`` line.
    """
    if as_json:
        print(json.dumps({"error": message}), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def positive_int(value):
    """argparse ``type`` for an integer that must be 1 or greater."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {number}")
    return number
