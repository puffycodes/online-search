#!/usr/bin/env python3
"""
Shared helpers for the command-line entry-point scripts in this repo:
uniform error exits and a couple of argparse ``type`` callables.

Not a CLI itself - this module is imported, not run.
"""

import argparse
import json
import sys


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
