"""Tests for osv_vulnerabilities: ecosystem names, the OSV query and paging, alias merging, and main()."""

import json

import pytest
import requests

import osv_vulnerabilities as osv
from helpers import FakeResponse


def _record(vuln_id, aliases=(), summary="A bug", severity=None, fixed=("2.0",),
            published="2020-01-02T00:00:00Z", package="jinja2", ecosystem="PyPI", **extra):
    record = {
        "id": vuln_id,
        "aliases": list(aliases),
        "summary": summary,
        "details": f"Details of {vuln_id}.",
        "published": published,
        "modified": "2024-05-06T00:00:00Z",
        "affected": [{
            "package": {"name": package, "ecosystem": ecosystem},
            "ranges": [{"type": "ECOSYSTEM",
                        "events": [{"introduced": "0"}] + [{"fixed": f} for f in fixed]}],
        }],
    }
    if severity:
        record["database_specific"] = {"severity": severity}
    record.update(extra)
    return record


class TestCanonicalEcosystem:
    @pytest.mark.parametrize("given,expected", [
        ("pypi", "PyPI"), ("PYPI", "PyPI"), ("NPM", "npm"), ("go", "Go"),
        ("Crates.IO", "crates.io"), ("rubygems", "RubyGems"), ("github actions", "GitHub Actions"),
    ])
    def test_case_insensitive(self, given, expected):
        assert osv.canonical_ecosystem(given) == expected

    @pytest.mark.parametrize("given,expected", [
        ("pip", "PyPI"), ("cargo", "crates.io"), ("golang", "Go"), ("gem", "RubyGems"),
        ("composer", "Packagist"), ("node", "npm"),
    ])
    def test_aliases(self, given, expected):
        assert osv.canonical_ecosystem(given) == expected

    def test_release_suffix_kept(self):
        assert osv.canonical_ecosystem("debian:12") == "Debian:12"
        assert osv.canonical_ecosystem("ubuntu:22.04:LTS") == "Ubuntu:22.04:LTS"

    def test_unknown_passed_through(self):
        assert osv.canonical_ecosystem(" Nonsense ") == "Nonsense"


class TestSourceName:
    @pytest.mark.parametrize("vuln_id,source", [
        ("GHSA-462w-v97r-4m45", "GitHub Advisory Database"),
        ("PYSEC-2019-217", "PyPI Advisory Database"),
        ("GO-2023-2102", "Go Vulnerability Database"),
        ("RUSTSEC-2021-0001", "RustSec Advisory Database"),
        ("MAL-2024-1", "OpenSSF Malicious Packages"),
    ])
    def test_known_prefixes(self, vuln_id, source):
        assert osv.source_name(vuln_id) == source

    def test_unknown_prefix_is_itself(self):
        assert osv.source_name("ZZZ-1") == "ZZZ"


class TestPostQuery:
    def test_posts_json_with_timeout(self, monkeypatch):
        calls = []

        def fake_post(url, json=None, timeout=None):
            calls.append((url, json, timeout))
            return FakeResponse(json_data={"vulns": []})

        monkeypatch.setattr(osv.requests, "post", fake_post)
        assert osv.post_query({"a": 1}) == {"vulns": []}
        assert calls == [(osv.QUERY_URL, {"a": 1}, osv.REQUEST_TIMEOUT)]

    def test_surfaces_osv_message(self, monkeypatch):
        response = FakeResponse(json_data={"code": 3, "message": "invalid ecosystem"},
                                status_code=400)
        monkeypatch.setattr(osv.requests, "post", lambda *a, **k: response)
        with pytest.raises(requests.HTTPError, match="400: invalid ecosystem"):
            osv.post_query({})

    def test_non_json_error_falls_back_to_status(self, monkeypatch):
        response = FakeResponse(status_code=503,
                                raise_for_status=requests.HTTPError("503 Server Error"))
        monkeypatch.setattr(osv.requests, "post", lambda *a, **k: response)
        with pytest.raises(requests.HTTPError, match="503"):
            osv.post_query({})


class TestFetchVulns:
    def test_payload_with_and_without_version(self, monkeypatch):
        payloads = []
        monkeypatch.setattr(osv, "post_query", lambda p: payloads.append(dict(p)) or {})
        osv.fetch_vulns("jinja2", "PyPI", "2.4.1")
        osv.fetch_vulns("jinja2", "PyPI")
        assert payloads == [
            {"package": {"name": "jinja2", "ecosystem": "PyPI"}, "version": "2.4.1"},
            {"package": {"name": "jinja2", "ecosystem": "PyPI"}},
        ]

    def test_empty_body_is_no_vulns(self, monkeypatch):
        monkeypatch.setattr(osv, "post_query", lambda p: {})
        assert osv.fetch_vulns("x", "PyPI") == ([], True)

    def test_follows_page_tokens(self, monkeypatch):
        pages = [
            {"vulns": [{"id": "A"}], "next_page_token": "t1"},
            {"vulns": [{"id": "B"}]},
        ]
        tokens = []

        def fake(payload):
            tokens.append(payload.get("page_token"))
            return pages.pop(0)

        monkeypatch.setattr(osv, "post_query", fake)
        vulns, complete = osv.fetch_vulns("x", "PyPI")
        assert [v["id"] for v in vulns] == ["A", "B"]
        assert complete is True
        assert tokens == [None, "t1"]

    def test_page_cap_marks_incomplete(self, monkeypatch):
        monkeypatch.setattr(osv, "post_query",
                            lambda p: {"vulns": [{"id": "A"}], "next_page_token": "more"})
        vulns, complete = osv.fetch_vulns("x", "PyPI", max_pages=3)
        assert len(vulns) == 3
        assert complete is False


class TestGroupVulns:
    def test_merges_mutual_aliases(self):
        groups = osv.group_vulns([
            _record("GHSA-1", ["CVE-1", "PYSEC-1"]),
            _record("PYSEC-1", ["CVE-1", "GHSA-1"]),
            _record("GHSA-2", ["CVE-2"]),
        ])
        assert [[r["id"] for r in g] for g in groups] == [["GHSA-1", "PYSEC-1"], ["GHSA-2"]]

    def test_merges_through_shared_cve(self):
        # Neither lists the other's id, but both name the same CVE.
        groups = osv.group_vulns([_record("GHSA-1", ["CVE-9"]), _record("GO-1", ["CVE-9"])])
        assert len(groups) == 1

    def test_one_way_alias_still_merges(self):
        groups = osv.group_vulns([_record("GHSA-1", ["PYSEC-1"]), _record("PYSEC-1")])
        assert len(groups) == 1

    def test_unrelated_non_cve_alias_does_not_merge(self):
        # A shared alias that is neither a returned id nor a CVE is not a link.
        groups = osv.group_vulns([_record("GHSA-1", ["SNYK-1"]), _record("GHSA-2", ["SNYK-1"])])
        assert len(groups) == 2

    def test_transitive_merge(self):
        groups = osv.group_vulns([
            _record("A-1", ["B-1"]), _record("B-1", ["C-1"]), _record("C-1"),
        ])
        assert len(groups) == 1


class TestFixedVersions:
    def test_reads_ecosystem_ranges(self):
        assert osv.fixed_versions([_record("X", fixed=("2.8.1", "2.10.1"))],
                                  "jinja2", "PyPI") == ["2.8.1", "2.10.1"]

    def test_deduplicates_across_records(self):
        records = [_record("A", fixed=("2.0",)), _record("B", fixed=("2.0", "3.0"))]
        assert osv.fixed_versions(records, "jinja2", "PyPI") == ["2.0", "3.0"]

    def test_pypi_name_normalization(self):
        record = _record("X", package="Foo_Bar", fixed=("1.1",))
        assert osv.fixed_versions([record], "foo-bar", "PyPI") == ["1.1"]

    def test_other_package_ignored(self):
        record = _record("X", package="markupsafe")
        assert osv.fixed_versions([record], "jinja2", "PyPI") == []

    def test_release_suffix_ignored_for_match(self):
        record = _record("X", package="openssl", ecosystem="Debian:12", fixed=("3.0.1",))
        assert osv.fixed_versions([record], "openssl", "Debian") == ["3.0.1"]

    def test_git_ranges_skipped(self):
        record = _record("X")
        record["affected"][0]["ranges"] = [
            {"type": "GIT", "events": [{"introduced": "0"}, {"fixed": "abc123"}]},
        ]
        assert osv.fixed_versions([record], "jinja2", "PyPI") == []


class TestSummarizeGroup:
    def test_prefers_ghsa_and_collects_fields(self):
        records = [
            _record("PYSEC-1", ["CVE-1", "GHSA-1"], summary=None),
            _record("GHSA-1", ["CVE-1", "PYSEC-1"], summary="Sandbox escape",
                    severity="high", published="2019-04-10T14:30:24Z"),
        ]
        records[1]["severity"] = [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N"}]
        out = osv.summarize_group(records, "jinja2", "PyPI")
        assert out["id"] == "GHSA-1"
        assert out["url"] == "https://osv.dev/vulnerability/GHSA-1"
        assert out["summary"] == "Sandbox escape"
        assert out["severity"] == "HIGH"
        assert out["cvss"] == [{"type": "CVSS_V3", "vector": "CVSS:3.1/AV:N"}]
        assert out["cve"] == ["CVE-1"]
        assert out["aliases"] == ["CVE-1"]
        assert out["fixed"] == ["2.0"]
        assert out["published"] == "2019-04-10"
        assert out["modified"] == "2024-05-06"
        assert out["malicious"] is False
        assert out["advisories"] == [
            {"id": "GHSA-1", "source": "GitHub Advisory Database",
             "url": "https://osv.dev/vulnerability/GHSA-1"},
            {"id": "PYSEC-1", "source": "PyPI Advisory Database",
             "url": "https://osv.dev/vulnerability/PYSEC-1"},
        ]

    def test_summary_falls_back_to_details(self):
        out = osv.summarize_group([_record("GO-1", summary=None)], "x", "Go")
        assert out["summary"] == "Details of GO-1."

    def test_details_clipped(self):
        record = _record("X")
        record["details"] = "word " * 200
        out = osv.summarize_group([record], "jinja2", "PyPI")
        assert len(out["details"]) == osv.DETAILS_CHARS
        assert out["details"].endswith("…")

    def test_no_severity_is_none(self):
        assert osv.summarize_group([_record("PYSEC-1")], "jinja2", "PyPI")["severity"] is None

    def test_malicious_flag(self):
        assert osv.summarize_group([_record("MAL-2024-1")], "jinja2", "PyPI")["malicious"] is True

    def test_earliest_published(self):
        records = [_record("A", published="2021-01-01T00:00:00Z"),
                   _record("B", published="2020-06-01T00:00:00Z")]
        assert osv.summarize_group(records, "jinja2", "PyPI")["published"] == "2020-06-01"


class TestBuildResults:
    def test_sorted_malicious_then_severity_then_newest(self):
        vulns = [
            _record("GHSA-low", severity="LOW", published="2024-01-01T00:00:00Z"),
            _record("GHSA-high-old", severity="HIGH", published="2019-01-01T00:00:00Z"),
            _record("GHSA-high-new", severity="HIGH", published="2023-01-01T00:00:00Z"),
            _record("PYSEC-unrated", published="2025-01-01T00:00:00Z"),
            _record("GHSA-critical", severity="CRITICAL", published="2018-01-01T00:00:00Z"),
            _record("MAL-1", published="2017-01-01T00:00:00Z"),
        ]
        ids = [i["id"] for i in osv.build_results(vulns, "jinja2", "PyPI")]
        assert ids == ["MAL-1", "GHSA-critical", "GHSA-high-new", "GHSA-high-old",
                       "GHSA-low", "PYSEC-unrated"]

    def test_withdrawn_dropped(self):
        vulns = [_record("GHSA-1", withdrawn="2024-01-01T00:00:00Z"), _record("GHSA-2")]
        assert [i["id"] for i in osv.build_results(vulns, "jinja2", "PyPI")] == ["GHSA-2"]

    def test_withdrawn_member_dropped_from_group(self):
        vulns = [_record("GHSA-1", ["PYSEC-1"]),
                 _record("PYSEC-1", withdrawn="2024-01-01T00:00:00Z")]
        out = osv.build_results(vulns, "jinja2", "PyPI")
        assert [a["id"] for a in out[0]["advisories"]] == ["GHSA-1"]


class TestParseArgs:
    def test_defaults(self):
        args = osv.parse_args(["jinja2", "-e", "pypi"])
        assert (args.package, args.version, args.ecosystem) == ("jinja2", None, "PyPI")
        assert args.limit == osv.DEFAULT_LIMIT
        assert args.json is False

    def test_version_positional(self):
        assert osv.parse_args(["jinja2", "2.4.1", "-e", "PyPI"]).version == "2.4.1"

    def test_ecosystem_required(self):
        with pytest.raises(SystemExit) as exc:
            osv.parse_args(["jinja2"])
        assert exc.value.code == 2

    @pytest.mark.parametrize("bad", ["0", "-1", "x"])
    def test_bad_limit_exits_2(self, bad):
        with pytest.raises(SystemExit) as exc:
            osv.parse_args(["jinja2", "-e", "PyPI", "--limit", bad])
        assert exc.value.code == 2

    def test_blank_package_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            osv.parse_args(["  ", "-e", "PyPI"])
        assert exc.value.code == 2


class TestMain:
    VULNS = [
        _record("GHSA-1", ["CVE-1", "PYSEC-1"], severity="HIGH"),
        _record("PYSEC-1", ["CVE-1", "GHSA-1"]),
        _record("GHSA-2", ["CVE-2"], severity="MODERATE", fixed=()),
    ]

    def _wire(self, monkeypatch, vulns=None, complete=True):
        vulns = self.VULNS if vulns is None else vulns
        calls = []

        def fetch(package, ecosystem, version=None):
            calls.append((package, ecosystem, version))
            return list(vulns), complete

        monkeypatch.setattr(osv, "fetch_vulns", fetch)
        return calls

    def test_json_shape(self, monkeypatch, capsys):
        calls = self._wire(monkeypatch)
        osv.main(["jinja2", "2.4.1", "-e", "pip", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert calls == [("jinja2", "PyPI", "2.4.1")]
        assert (payload["package"], payload["version"], payload["ecosystem"]) == (
            "jinja2", "2.4.1", "PyPI")
        assert (payload["count"], payload["advisories"], payload["complete"]) == (2, 3, True)
        assert [v["id"] for v in payload["vulnerabilities"]] == ["GHSA-1", "GHSA-2"]
        assert "CC-BY 4.0" in payload["attribution"]

    def test_limit_cuts_list_not_count(self, monkeypatch, capsys):
        self._wire(monkeypatch)
        osv.main(["jinja2", "-e", "PyPI", "--limit", "1", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["count"] == 2
        assert len(payload["vulnerabilities"]) == 1

    def test_text_report(self, monkeypatch, capsys):
        self._wire(monkeypatch)
        osv.main(["jinja2", "2.4.1", "-e", "PyPI"])
        out = capsys.readouterr().out
        assert out.startswith("Querying OSV.dev for jinja2 2.4.1 (PyPI)...")
        assert "2 known vulnerabilities from 3 advisories" in out
        assert "[HIGH] GHSA-1 (CVE-1)" in out
        assert "fixed in: 2.0" in out
        assert "no fixed version listed" in out
        assert "PYSEC-1 (PyPI Advisory Database)" in out
        assert "https://osv.dev/vulnerability/GHSA-1" in out
        assert out.rstrip().endswith(osv.ATTRIBUTION)

    def test_text_more_and_incomplete_notes(self, monkeypatch, capsys):
        self._wire(monkeypatch, complete=False)
        osv.main(["jinja2", "-e", "PyPI", "--limit", "1"])
        out = capsys.readouterr().out
        assert "(any version)" in out
        assert "... and 1 more" in out
        assert "more results than the" in out

    def test_text_malicious_label(self, monkeypatch, capsys):
        self._wire(monkeypatch, vulns=[_record("MAL-2024-9")])
        osv.main(["evil-pkg", "-e", "npm"])
        assert "[MALICIOUS] MAL-2024-9" in capsys.readouterr().out

    def test_no_vulns_text_warns_about_spelling(self, monkeypatch, capsys):
        self._wire(monkeypatch, vulns=[])
        osv.main(["jinja2", "3.1.6", "-e", "PyPI"])
        out = capsys.readouterr().out
        assert "No known vulnerabilities in OSV.dev for jinja2 3.1.6 (PyPI), this version." in out
        assert "check the spelling" in out
        assert osv.ATTRIBUTION in out

    def test_no_vulns_json(self, monkeypatch, capsys):
        self._wire(monkeypatch, vulns=[])
        osv.main(["jinja2", "-e", "PyPI", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert (payload["count"], payload["vulnerabilities"]) == (0, [])

    def test_fetch_error_exits_1_json(self, monkeypatch, capsys):
        def boom(package, ecosystem, version=None):
            raise requests.HTTPError("400: invalid ecosystem")

        monkeypatch.setattr(osv, "fetch_vulns", boom)
        with pytest.raises(SystemExit) as exc:
            osv.main(["jinja2", "-e", "Nonsense", "--json"])
        assert exc.value.code == 1
        error = json.loads(capsys.readouterr().err)["error"]
        assert error == "OSV.dev lookup failed for jinja2 (Nonsense): 400: invalid ecosystem"

    def test_fetch_error_exits_1_text(self, monkeypatch, capsys):
        def boom(package, ecosystem, version=None):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(osv, "fetch_vulns", boom)
        with pytest.raises(SystemExit) as exc:
            osv.main(["jinja2", "-e", "PyPI"])
        assert exc.value.code == 1
        assert capsys.readouterr().err.startswith("Error: OSV.dev lookup failed")

    def test_missing_ecosystem_exits_2_before_fetch(self, monkeypatch):
        calls = self._wire(monkeypatch)
        with pytest.raises(SystemExit) as exc:
            osv.main(["jinja2"])
        assert exc.value.code == 2
        assert calls == []
