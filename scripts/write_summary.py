"""Wrap-up entry point. Run with --help for options."""

import os
import sys

import _bootstrap  # noqa: F401  (sets sys.path and stream encoding)

from ops_kit.summary import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr, os.environ))
