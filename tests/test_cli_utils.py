"""Tests for cli_utils: the die() error-exit helper and the positive_int argparse type."""

import argparse
import json

import pytest

from cli_utils import die, positive_int


class TestPositiveInt:
    @pytest.mark.parametrize("raw,expected", [("1", 1), ("10", 10), ("999", 999)])
    def test_accepts_positive(self, raw, expected):
        assert positive_int(raw) == expected

    @pytest.mark.parametrize("raw", ["0", "-1", "-999"])
    def test_rejects_non_positive(self, raw):
        with pytest.raises(argparse.ArgumentTypeError, match="positive integer"):
            positive_int(raw)

    @pytest.mark.parametrize("raw", ["abc", "1.5", "", "  ", "3x"])
    def test_rejects_non_integer(self, raw):
        with pytest.raises(argparse.ArgumentTypeError, match="expected an integer"):
            positive_int(raw)


class TestDie:
    def test_plain_message_to_stderr_and_exit_1(self, capsys):
        with pytest.raises(SystemExit) as exc:
            die("something broke")
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.strip() == "Error: something broke"

    def test_json_message(self, capsys):
        with pytest.raises(SystemExit) as exc:
            die("bad symbol", as_json=True)
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err) == {"error": "bad symbol"}
