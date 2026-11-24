"""Print the state of every item in a session scope file.

Usage: python scripts/scope_status.py --session <session id> [--cwd <dir>]
Exit code 0 when nothing is unresolved, 1 when the Stop hook would block
(with OPS_KIT_REQUIRE_EVIDENCE=1 that includes ticked items without evidence).
"""

import argparse
import os
import sys

import _bootstrap  # noqa: F401  (sets sys.path and stream encoding)

from ops_kit import checklist as cl


def main(argv):
    parser = argparse.ArgumentParser(prog="scope_status")
    parser.add_argument("--session", required=True)
    parser.add_argument("--cwd", default=".")
    args = parser.parse_args(argv)
    path = cl.find_scope_file(args.cwd, args.session, os.environ)
    if not path:
        expected = "%s/%s" % (cl.scope_dir_name(os.environ), cl.scope_file_name(args.session))
        print("no scope file (expected %s)" % expected)
        return 0
    items = cl.read_scope(path)
    strict = cl.env_flag(os.environ, "OPS_KIT_REQUIRE_EVIDENCE")
    for item in items:
        print("%-9s line %-3d %s" % (item.state(strict), item.line_no, item.text))
    tally = cl.counts(items, strict)
    line = "%d done, %d blocked, %d open, %d unlabeled" % (
        tally[cl.DONE],
        tally[cl.BLOCKED],
        tally[cl.OPEN],
        tally[cl.UNLABELED],
    )
    if strict:
        line += ", %d ticked without evidence" % tally[cl.UNPROVEN]
    print(line)
    return 1 if cl.unresolved(items, strict) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
