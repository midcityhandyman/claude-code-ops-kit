"""Parse a session scope checklist and classify each item.

A scope file is plain markdown. Every task list line is one item:

    - [ ] Add retry to the sync job (done when: pytest tests/test_sync.py passes)
    - [x] Rename the config key. evidence: grep shows 0 old references
    - [ ] Rotate the staging token. blocked: needs an admin to approve the request
    - [ ] Backfill old rows. open: next step is a dry run, owner is the data team

Item states:
    done       ticked
    blocked    unticked, carries "blocked: <reason>"
    open       unticked, carries "open: <next step>"
    unlabeled  unticked with no label. This is the state the Stop hook refuses.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

DEFAULT_SCOPE_DIR = ".context"

DONE = "done"
BLOCKED = "blocked"
OPEN = "open"
UNLABELED = "unlabeled"
UNPROVEN = "unproven"  # ticked without evidence, only used in strict mode

_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)[-*+][ \t]+\[(?P<mark>[ xX])\][ \t]*(?P<text>.*)$")
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
# A label needs a reason after the colon. "blocked:" on its own does not count.
_LABEL_RE = re.compile(r"(?<![\w-])(?P<label>blocked|open)[ \t]*:[ \t]*(?P<note>\S.*)", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"(?<![\w-])evidence[ \t]*:[ \t]*\S", re.IGNORECASE)
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]")


@dataclass
class Item:
    line_no: int
    text: str
    checked: bool
    label: Optional[str] = None
    note: str = ""
    has_evidence: bool = False

    def state(self, require_evidence: bool = False) -> str:
        if self.checked:
            if require_evidence and not self.has_evidence:
                return UNPROVEN
            return DONE
        if self.label == BLOCKED:
            return BLOCKED
        if self.label == OPEN:
            return OPEN
        return UNLABELED


def _indent_width(indent: str) -> int:
    return len(indent.expandtabs(4))


def parse_scope(text: str) -> List[Item]:
    """Return every task list item in the markdown text, in file order.

    Lines inside fenced code blocks are ignored. An indented line that follows
    an item and is not itself an item is treated as a continuation of it, so a
    label or evidence note may sit on the next line.
    """
    items: List[Item] = []
    raw: List[List[str]] = []
    in_fence = False
    current_indent: Optional[int] = None

    for line_no, line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            current_indent = None
            continue
        if in_fence:
            continue
        match = _ITEM_RE.match(line)
        if match:
            current_indent = _indent_width(match.group("indent"))
            items.append(Item(line_no, match.group("text").strip(), match.group("mark") != " "))
            raw.append([match.group("text").strip()])
            continue
        stripped = line.strip()
        if not stripped:
            current_indent = None
            continue
        leading = _indent_width(line[: len(line) - len(line.lstrip())])
        if current_indent is not None and leading > current_indent:
            raw[-1].append(stripped)
        else:
            current_indent = None

    for item, parts in zip(items, raw):
        full = " ".join(p for p in parts if p)
        item.text = full
        label = _LABEL_RE.search(full)
        if label:
            item.label = label.group("label").lower()
            item.note = label.group("note").strip()
        item.has_evidence = bool(_EVIDENCE_RE.search(full))
    return items


def counts(items: Iterable[Item], require_evidence: bool = False) -> dict:
    result = {DONE: 0, BLOCKED: 0, OPEN: 0, UNLABELED: 0, UNPROVEN: 0}
    for item in items:
        result[item.state(require_evidence)] += 1
    return result


def unresolved(items: Iterable[Item], require_evidence: bool = False) -> List[Item]:
    """Items that must not be left as they are when the turn ends."""
    return [i for i in items if i.state(require_evidence) in (UNLABELED, UNPROVEN)]


def short_session_id(session_id: object) -> str:
    """First 8 safe characters of a session id. Empty string if unusable."""
    if not isinstance(session_id, str):
        return ""
    return _SAFE_ID_RE.sub("", session_id)[:8]


def scope_file_name(session_id: object) -> str:
    short = short_session_id(session_id)
    return "scope-%s.md" % short if short else ""


def scope_dir_name(env: Mapping[str, str]) -> str:
    return (env.get("OPS_KIT_SCOPE_DIR") or "").strip() or DEFAULT_SCOPE_DIR


def candidate_paths(cwd: object, session_id: object, env: Mapping[str, str]) -> List[Path]:
    """Where the scope file may live: the session cwd first, then the project root."""
    name = scope_file_name(session_id)
    if not name:
        return []
    roots: List[str] = []
    for root in (cwd, env.get("CLAUDE_PROJECT_DIR")):
        if isinstance(root, str) and root.strip() and root not in roots:
            roots.append(root)
    return [Path(root) / scope_dir_name(env) / name for root in roots]


def find_scope_file(cwd: object, session_id: object, env: Mapping[str, str]) -> Optional[Path]:
    for path in candidate_paths(cwd, session_id, env):
        if path.is_file():
            return path
    return None


def read_scope(path: Path) -> List[Item]:
    return parse_scope(path.read_text(encoding="utf-8", errors="replace"))


def env_flag(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    value = (env.get(name) or "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def display_path(path: Path, cwd: object) -> str:
    """Path relative to cwd with forward slashes when possible, for messages."""
    try:
        return os.path.relpath(str(path), str(cwd)).replace("\\", "/")
    except (ValueError, TypeError):
        return str(path).replace("\\", "/")
