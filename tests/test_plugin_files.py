"""Static checks on the plugin files against the documented formats."""

import json
import re

from conftest import REPO


def test_manifest_has_required_name_and_no_reserved_prefix():
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", manifest["name"])
    assert not manifest["name"].startswith(("claude-", "anthropic-", "anthropics-", "cc-plugin-"))
    assert manifest["author"]["name"]


def test_hooks_file_uses_wrapper_and_points_at_real_scripts():
    config = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert set(config["hooks"]) == {"Stop", "SessionStart"}
    for groups in config["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                assert hook["type"] == "command"
                match = re.search(r'"\$\{CLAUDE_PLUGIN_ROOT\}"/(scripts/\w+\.py)', hook["command"])
                assert match, "plugin root must be quoted in shell form"
                assert (REPO / match.group(1)).is_file()
    assert "matcher" not in config["hooks"]["Stop"][0]  # Stop does not support matchers


def test_skills_have_frontmatter_on_line_one():
    for name in ("scope", "wrapup"):
        text = (REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\n")
        front = text.split("---\n")[1]
        assert "name: %s\n" % name in front and "description: " in front


def test_no_em_dashes_anywhere():
    banned = (chr(0x2014), chr(0x2013))
    skip = {".venv", ".deps", ".git", "__pycache__", ".pytest_cache"}
    for path in REPO.rglob("*"):
        if path.is_file() and not skip.intersection(path.parts):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            assert not any(char in text for char in banned), path
