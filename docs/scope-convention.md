# Session scope checklist convention

One file per session, never a shared one:

```
<working directory>/.context/scope-<first 8 characters of the session id>.md
```

Several sessions often share one working directory. A shared `scope.md` would let one
session's unfinished work block another, or let one session tick another's items. The
short session id keeps them apart. The folder name can be changed with `OPS_KIT_SCOPE_DIR`.

## Writing items

```
- [ ] Add retry to the sync job (done when: pytest tests/test_sync.py passes)
```

One markdown task list line per deliverable. The `done when:` clause names a command, a
query or a read-back that fails right now and will pass when the item is done.

## End states

| State | Line | Counts as resolved |
| :- | :- | :- |
| done | `- [x] ... evidence: <proof>` | yes |
| blocked | `- [ ] ... blocked: <first failing check, and what the user must do>` | yes |
| open | `- [ ] ... open: <next step and who owns it>` | yes |
| unlabeled | `- [ ] ...` with no label | no, the Stop hook holds the turn open |

## Parsing rules

These are the exact rules in `ops_kit/checklist.py`, covered by `tests/test_checklist.py`.

- An item is a line starting with `-`, `*` or `+`, then `[ ]`, `[x]` or `[X]`.
- A label is the whole word `blocked` or `open`, a colon, and at least one character of
  reason. `blocked:` with nothing after it does not count. `reopen:` is not a label.
- Labels are case insensitive. If both appear, the first one wins.
- An indented line directly under an item, that is not itself an item, continues that
  item. The label or evidence may sit there. A blank line ends the continuation.
- Nested task list lines are items in their own right.
- Lines inside fenced code blocks are ignored.
- With `OPS_KIT_REQUIRE_EVIDENCE=1`, a ticked item without `evidence: <text>` is treated
  as unresolved.

## Why labels instead of deleting the line

Deleting an unfinished item hides it. A `blocked:` or `open:` label keeps the item in the
file, in the wrap-up summary and in the session log, with the reason attached, so the next
session or the person reading the summary can pick it up.
