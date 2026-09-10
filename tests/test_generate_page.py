"""Tests for app/hottest_discussions/generate_page: option/page rendering, arg parsing, and main()."""

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "app" / "hottest_discussions"))

import generate_page as gp  # noqa: E402


class TestRenderLimitOptions:
    def test_marks_the_selected_option_only(self):
        out = gp.render_limit_options(25)
        assert 'value="25" selected' in out
        assert 'value="10" selected' not in out
        assert out.count(" selected") == 1
        assert out.count("<option") == len(gp.LIMIT_OPTIONS) == 3


class TestRenderPage:
    def test_contains_shell_and_timestamp(self):
        html = gp.render_page(10)
        assert "<!DOCTYPE html>" in html
        assert 'id="refresh-btn"' in html
        assert re.search(r"\d{4}-\d\d-\d\d \d\d:\d\d UTC", html)

    def test_template_braces_are_resolved(self):
        html = gp.render_page(10)
        assert "{{" not in html and "}}" not in html
        assert "{limit_options}" not in html and "{generated_at}" not in html
        assert ":root {" in html  # doubled brace in the template collapsed to one

    def test_invalid_limit_raises(self):
        with pytest.raises(ValueError, match="limit must be one of"):
            gp.render_page(99)


class TestParseArgs:
    def test_defaults(self):
        args = gp.parse_args([])
        assert args.limit == gp.RESULTS_TO_SHOW
        assert args.output == gp.DEFAULT_OUTPUT

    def test_limit_choice_enforced(self):
        with pytest.raises(SystemExit):
            gp.parse_args(["--limit", "7"])

    def test_output_is_path(self):
        args = gp.parse_args(["--output", "/tmp/x.html"])
        assert isinstance(args.output, Path)


class TestMain:
    def test_writes_file_and_creates_parent_dir(self, tmp_path, capsys):
        target = tmp_path / "nested" / "page.html"
        gp.main(["--output", str(target)])
        assert target.exists()
        assert "<!DOCTYPE html>" in target.read_text(encoding="utf-8")
        assert "Wrote empty page shell" in capsys.readouterr().out


class TestConsistency:
    def test_limit_options_first_is_results_to_show(self):
        assert gp.LIMIT_OPTIONS[0] == gp.RESULTS_TO_SHOW
