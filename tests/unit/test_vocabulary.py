"""The vocabulary rules of docs/glossary.md, enforced.

The core is domain-neutral (CLAUDE.md): education words belong to presets, and we say
"anonymous", never "blind". Only the preset files may name them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "peerview"

# Files that define preset content: education words are their job.
PRESET_FILES = {"domain/tenancy.py", "domain/rubrics.py"}

FORBIDDEN = {
    "course": r"\bcourses?\b",
    "student": r"\bstudents?\b",
    "teacher": r"\bteachers?\b",
    "assignment": r"\bassignments?\b",  # Education's word for a Call; reviewers are *allocated*
    "blind": r"\bblind\w*|_blind\b",  # say anonymous
}


def _core_files() -> list[Path]:
    files: list[Path] = []
    for folder in ("domain", "application", "plugins"):
        files += sorted((SRC / folder).rglob("*.py"))
    files += sorted((SRC / "adapters" / "web" / "templates").rglob("*.html"))
    return [f for f in files if f.relative_to(SRC).as_posix() not in PRESET_FILES]


@pytest.mark.parametrize("word", sorted(FORBIDDEN))
def test_core_does_not_use_preset_or_banned_words(word: str) -> None:
    pattern = re.compile(FORBIDDEN[word], re.IGNORECASE)
    hits = [
        f"{f.relative_to(SRC)}:{n}: {line.strip()}"
        for f in _core_files()
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert not hits, f"'{word}' is banned outside presets (docs/glossary.md):\n" + "\n".join(hits)


def test_glossary_exists_and_is_linked_from_claude_md() -> None:
    root = SRC.parents[1]
    assert (root / "docs" / "glossary.md").is_file()
    assert "docs/glossary.md" in (root / "CLAUDE.md").read_text(encoding="utf-8")


# -- the brand (ADR 0027) --------------------------------------------------------------------------

ROOT = SRC.parents[1]
BRAND_FOLDERS = ("src", "tests", "docs", "utils", "scripts", ".github")
BRAND_SUFFIXES = {".py", ".html", ".js", ".css", ".md", ".toml", ".sh", ".yml", ".yaml", ".txt"}
OLD_NAME = re.compile(r"previewit|prreview", re.IGNORECASE)
WRONG_SPELLING = re.compile(r"\bPeer ?[Vv]iew\b|\bPEERVIEW\b(?!_)")  # say peerview.it
# Only these may name the old brand: they keep old settings working or record the change.
OLD_NAME_ALLOWED = {
    "docs/adr/0021-site-addresses.md",  # a record of what was decided then
    "docs/adr/0027-brand-peerview-it.md",
    "docs/glossary.md",
    "docs/business/actions-now.md",
    "src/peerview/adapters/settings.py",
    "src/peerview/adapters/web/session.py",
    "tests/unit/test_config_file.py",
    "tests/unit/test_vocabulary.py",
}


SPELLING_ALLOWED = {
    "docs/glossary.md",
    "docs/adr/0021-site-addresses.md",
    "docs/adr/0027-brand-peerview-it.md",
}


def _brand_files() -> list[Path]:
    files = [ROOT / name for name in ("README.md", "CLAUDE.md", "CONTRIBUTING.md", "SECURITY.md",
                                      "CODE_OF_CONDUCT.md", "Makefile", "pyproject.toml",
                                      "peerview.example.toml")]  # fmt: skip
    for folder in BRAND_FOLDERS:
        files += [
            f
            for f in sorted((ROOT / folder).rglob("*"))
            if f.is_file() and f.suffix in BRAND_SUFFIXES and "__pycache__" not in f.parts
        ]
    return [f for f in files if f.is_file()]


def test_the_brand_is_peerview_it_everywhere() -> None:
    old, wrong = [], []
    for f in _brand_files():
        where = f.relative_to(ROOT).as_posix()
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if OLD_NAME.search(line) and where not in OLD_NAME_ALLOWED:
                old.append(f"{where}:{n}: {line.strip()}")
            if WRONG_SPELLING.search(line) and where not in SPELLING_ALLOWED:
                wrong.append(f"{where}:{n}: {line.strip()}")
    assert not old, "The product is peerview.it (ADR 0027), not its old name:\n" + "\n".join(old)
    assert not wrong, "Write the brand as peerview.it:\n" + "\n".join(wrong)
