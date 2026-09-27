"""The repository is public (D-002): private material must never be tracked.

These run against git itself, so they fail the moment content-import/ stops being ignored or a
private file slips into the index.
"""

import re
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

from apps.core.content import TODO_MARKER

ROOT = Path(settings.BASE_DIR)


def git(*args):
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    return result.returncode, result.stdout


@pytest.fixture(scope="module")
def tracked():
    code, out = git("ls-files")
    if code != 0:
        pytest.skip("not a git checkout")
    return out.splitlines()


def test_content_import_is_ignored():
    code, _out = git("check-ignore", "-q", "content-import/cv.pdf")
    assert code == 0


def test_nothing_under_content_import_is_tracked(tracked):
    assert [path for path in tracked if path.startswith("content-import/")] == []


def test_no_media_or_documents_are_tracked(tracked):
    private_like = re.compile(r"\.(pdf|docx?|jpe?g|heic|png|webp|avif)$", re.IGNORECASE)
    assert [path for path in tracked if private_like.search(path)] == []


def test_migrations_contain_schema_not_content(tracked):
    """Real career content is data, never migrations (CLAUDE.md, hard rules)."""
    for path in tracked:
        if "/migrations/" in path and path.endswith(".py"):
            text = (ROOT / path).read_text(encoding="utf-8")
            assert "migrations.RunPython" not in text, path
            # The bare marker is legitimately part of the schema (the no-TODO constraints search
            # for it); a draft note always reads "TODO(odilbek): ...", which must never appear.
            assert f"{TODO_MARKER}):" not in text, path
            assert not re.search(r"[\w.+-]+@(?!example\.com)[\w-]+\.[\w.]+", text), path
