"""SessionStart hook entry point. Reads hook JSON on stdin."""

import os
import sys

import _bootstrap  # noqa: F401  (sets sys.path and stream encoding)

from ops_kit.session_start import main

if __name__ == "__main__":
    sys.exit(main(sys.stdin, sys.stdout, sys.stderr, os.environ))
