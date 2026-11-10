"""Hermes refuses to install a plugin whose source trips its hardcoded-secret rule."""

from __future__ import annotations

import re
from pathlib import Path

# Hermes tools/skills_guard.py "hardcoded_secret": a critical finding that
# `hermes plugins install --force` cannot override.
HARDCODED_SECRET = re.compile(
    r'(?:api[_-]?key|token|secret|password)\s*[=:]\s*["\']'
    r'(?!(?-i:[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)["\'])'
    r"[A-Za-z0-9+/=_-]{20,}",
    re.IGNORECASE,
)
ROOT = Path(__file__).resolve().parents[1]
SCANNED_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".toml", ".json", ".sh", ".txt"}
SKIPPED_DIRS = {".git", "tests", ".venv"}


def _shipped_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix in SCANNED_SUFFIXES and not SKIPPED_DIRS & set(path.parts)
    ]


def test_shipped_files_pass_the_hermes_hardcoded_secret_rule() -> None:
    hits = []
    for path in _shipped_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if HARDCODED_SECRET.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{number}")
    assert hits == []
