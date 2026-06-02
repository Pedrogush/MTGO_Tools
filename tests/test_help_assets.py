"""Smoke checks for the bundled help assets.

These guard against regressions where the help viewer can't find its docs
(see issue #464): the path helper must resolve to the real ``help/`` tree,
the manifest's default topic and every file it references must exist on disk,
and every topic linked from the table of contents must exist as well.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.constants.paths import resource_path


def _read_hhp() -> tuple[Path, str]:
    hhp = resource_path("help", "mtgo_tools.hhp")
    assert hhp.is_file(), f"expected help project file at {hhp}"
    return hhp, hhp.read_text(encoding="utf-8")


def _option(text: str, key: str) -> str | None:
    return next(
        (line.split("=", 1)[1].strip() for line in text.splitlines() if line.startswith(f"{key}=")),
        None,
    )


def test_help_index_is_loadable():
    hhp, text = _read_hhp()

    default_topic = _option(text, "Default topic")
    assert default_topic, "help project file missing Default topic"

    topic_path = hhp.parent / default_topic
    assert topic_path.is_file(), f"default help topic missing: {topic_path}"


def test_help_contents_and_index_files_exist():
    hhp, text = _read_hhp()

    for key in ("Contents file", "Index file"):
        value = _option(text, key)
        assert value, f"help project file missing {key}"
        path = hhp.parent / value
        assert path.is_file(), f"{key} missing: {path}"


def test_help_manifest_files_all_exist():
    hhp, text = _read_hhp()

    files_section = text.split("[FILES]", 1)
    assert len(files_section) == 2, "help project file missing [FILES] section"

    listed = [line.strip() for line in files_section[1].splitlines() if line.strip()]
    # Stop at the next bracketed section, if any follows [FILES].
    files = []
    for entry in listed:
        if entry.startswith("["):
            break
        files.append(entry)
    assert files, "help project file [FILES] section is empty"

    for entry in files:
        path = hhp.parent / entry
        assert path.is_file(), f"manifest file missing: {path}"


def test_help_contents_topics_all_exist():
    hhp = resource_path("help", "mtgo_tools.hhp")
    hhc = hhp.parent / "contents.hhc"
    assert hhc.is_file(), f"contents file missing: {hhc}"

    text = hhc.read_text(encoding="utf-8")
    locals_ = re.findall(r'<param\s+name="Local"\s+value="([^"]+)"', text, flags=re.IGNORECASE)
    assert locals_, "contents.hhc references no topics"

    for topic in locals_:
        path = hhp.parent / topic
        assert path.is_file(), f"contents topic missing: {path}"
