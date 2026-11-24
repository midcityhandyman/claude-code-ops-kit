import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).parent.parent
SESSION = "5e11a0c4-0000-4000-8000-000000000001"
SHORT = "5e11a0c4"


def load_hook_json(name, cwd):
    """Load a sample hook payload and point its cwd at a temp directory."""
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    payload["cwd"] = str(cwd)
    return payload


@pytest.fixture
def workdir(tmp_path):
    (tmp_path / ".context").mkdir()
    return tmp_path


@pytest.fixture
def write_scope(workdir):
    def _write(text, folder=".context"):
        target = workdir / folder
        target.mkdir(exist_ok=True)
        path = target / ("scope-%s.md" % SHORT)
        path.write_text(text, encoding="utf-8")
        return path

    return _write
