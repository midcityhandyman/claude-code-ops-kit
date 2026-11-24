from pathlib import Path

from ops_kit import checklist as cl

FIXTURES = Path(__file__).parent / "fixtures"


def states(text, **kwargs):
    return [item.state(**kwargs) for item in cl.parse_scope(text)]


def test_mixed_fixture_states_and_line_numbers():
    items = cl.parse_scope((FIXTURES / "scope_mixed.md").read_text(encoding="utf-8"))
    assert [i.state() for i in items] == [cl.DONE, cl.UNLABELED, cl.BLOCKED, cl.OPEN, cl.UNLABELED]
    assert [i.line_no for i in items] == [3, 4, 5, 7, 13]
    assert items[2].note == "token request needs an admin to approve it"
    assert items[0].has_evidence


def test_code_fence_lines_are_not_items():
    text = "```\n- [ ] not an item\n```\n~~~\n- [ ] also not\n~~~\n- [ ] real\n"
    assert len(cl.parse_scope(text)) == 1


def test_label_needs_a_reason():
    assert states("- [ ] ship it blocked:\n") == [cl.UNLABELED]
    assert states("- [ ] ship it open:   \n") == [cl.UNLABELED]
    assert states("- [ ] ship it BLOCKED: waiting on review\n") == [cl.BLOCKED]


def test_label_must_be_a_whole_word():
    assert states("- [ ] fix the reopen: handler\n") == [cl.UNLABELED]
    assert states("- [ ] fix un-blocked: path\n") == [cl.UNLABELED]


def test_done_when_clause_is_not_a_label():
    assert states("- [ ] add index (done when: EXPLAIN shows an index scan)\n") == [cl.UNLABELED]


def test_continuation_line_carries_the_label():
    text = "- [ ] rotate key\n    open: next step is a ticket, owner is the platform team\n"
    items = cl.parse_scope(text)
    assert items[0].state() == cl.OPEN
    assert "platform team" in items[0].note


def test_unindented_following_text_is_not_a_continuation():
    text = "- [ ] rotate key\nblocked: this is a separate paragraph\n"
    assert states(text) == [cl.UNLABELED]


def test_blank_line_ends_continuation():
    text = "- [ ] rotate key\n\n    open: stray indented text\n"
    assert states(text) == [cl.UNLABELED]


def test_nested_items_are_their_own_items():
    text = "- [ ] parent. open: split below, owner is this session\n  - [ ] child one\n  - [x] child two\n"
    assert states(text) == [cl.OPEN, cl.UNLABELED, cl.DONE]


def test_bullet_styles_and_uppercase_x():
    assert states("* [X] a\n+ [ ] b\n- [x] c\n") == [cl.DONE, cl.UNLABELED, cl.DONE]


def test_plain_bullets_and_prose_are_ignored():
    assert cl.parse_scope("# Title\n\n- plain bullet\nSome prose with [ ] in it.\n") == []


def test_require_evidence_marks_bare_ticks_unproven():
    text = "- [x] bare tick\n- [x] proven. evidence: 3 passed\n"
    assert states(text) == [cl.DONE, cl.DONE]
    assert states(text, require_evidence=True) == [cl.UNPROVEN, cl.DONE]
    assert len(cl.unresolved(cl.parse_scope(text), require_evidence=True)) == 1


def test_counts():
    items = cl.parse_scope((FIXTURES / "scope_mixed.md").read_text(encoding="utf-8"))
    assert cl.counts(items) == {cl.DONE: 1, cl.BLOCKED: 1, cl.OPEN: 1, cl.UNLABELED: 2, cl.UNPROVEN: 0}


def test_short_session_id_is_sanitized():
    assert cl.short_session_id("5e11a0c4-0000-4000") == "5e11a0c4"
    assert cl.short_session_id("../../etc/passwd") == "etcpassw"
    assert cl.short_session_id("") == ""
    assert cl.short_session_id(None) == ""
    assert cl.scope_file_name("..") == ""


def test_find_scope_file_falls_back_to_project_dir(tmp_path):
    project = tmp_path / "project"
    sub = project / "src"
    (project / ".context").mkdir(parents=True)
    sub.mkdir()
    scope = project / ".context" / "scope-5e11a0c4.md"
    scope.write_text("- [ ] a\n", encoding="utf-8")
    assert cl.find_scope_file(str(sub), "5e11a0c4-rest", {}) is None
    assert cl.find_scope_file(str(sub), "5e11a0c4-rest", {"CLAUDE_PROJECT_DIR": str(project)}) == scope


def test_env_flag():
    assert cl.env_flag({"A": "1"}, "A") and cl.env_flag({"A": "TRUE"}, "A")
    assert not cl.env_flag({"A": "0"}, "A") and not cl.env_flag({}, "A")
    assert cl.env_flag({}, "A", default=True) and not cl.env_flag({"A": "off"}, "A", default=True)
