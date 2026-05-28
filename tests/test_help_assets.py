"""Smoke checks for the bundled help assets.

These guard against regressions where the help viewer can't find its docs
(see issue #464): the path helper must resolve to the real ``help/`` tree
and the manifest's default topic must exist on disk.
"""

from __future__ import annotations

from utils.constants.paths import resource_path


def test_help_index_is_loadable():
    hhp = resource_path("help", "mtgo_tools.hhp")
    assert hhp.is_file(), f"expected help project file at {hhp}"

    text = hhp.read_text(encoding="utf-8")
    assert "Default topic=" in text

    default_topic = next(
        (line.split("=", 1)[1].strip() for line in text.splitlines() if line.startswith("Default topic=")),
        None,
    )
    assert default_topic, "help project file missing Default topic"

    topic_path = hhp.parent / default_topic
    assert topic_path.is_file(), f"default help topic missing: {topic_path}"
