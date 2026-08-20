"""The app's one container idiom (issue #962, phase 6, §4.4 / G2).

``wx.StaticBox`` draws a near-white etched groove with the label sitting *on* it,
and neither the groove's colour nor the label's position is reachable from wx.
This suite pins the replacement's structure -- which is load-bearing, because the
whole point of :attr:`SectionPanel.body` is that children get parented to it
rather than to a box that owns its own reparenting rules -- and fails if a
``wx.StaticBox`` ever comes back.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from utils.constants import theme as T

wx = pytest.importorskip("wx")

from widgets.section import SECTION_BORDER_WIDTH, SectionPanel  # noqa: E402


@pytest.fixture(scope="module")
def app() -> Iterator[object]:
    yield wx.App.Get() or wx.App()


@pytest.fixture
def frame(app: object) -> Iterator[object]:
    window = wx.Frame(None)
    yield window
    window.Destroy()


def _rgb(colour: object) -> tuple[int, int, int]:
    return (colour.Red(), colour.Green(), colour.Blue())


def test_the_heading_is_a_real_label_above_the_card(frame: object) -> None:
    section = SectionPanel(frame, title="Card Inspector")
    assert section.heading is not None
    assert section.heading.GetLabel() == "Card Inspector"
    # Above, not embedded in the edge: the heading and the card are two separate
    # slots of the same vertical sizer, in that order.
    children = [item.GetWindow() for item in section.GetSizer().GetChildren()]
    assert children[0] is section.heading
    assert section.body.GetParent() in children[1:]


def test_a_section_can_have_no_heading(frame: object) -> None:
    """The deck workspace: the notebook's tab strip already names the region."""
    section = SectionPanel(frame, title=None)
    assert section.heading is None
    assert len(section.GetSizer().GetChildren()) == 1


def test_the_border_is_one_subtle_pixel(frame: object) -> None:
    section = SectionPanel(frame, title="X")
    border_panel = section.body.GetParent()
    assert _rgb(border_panel.GetBackgroundColour()) == T.BORDER_SUBTLE
    item = border_panel.GetSizer().GetItem(section.body)
    assert item.GetBorder() == SECTION_BORDER_WIDTH == 1


def test_the_border_token_is_the_decorative_one_not_the_control_one() -> None:
    """Phase 0 reserved BORDER_STRONG for borders that identify a *control*.

    A section card is a grouping region named by the heading above it, so its
    edge is ornament: WCAG 1.4.11 does not apply and BORDER_SUBTLE is correct.
    Ten cards outlined in BORDER_STRONG would re-create the problem phase 6 is
    fixing.
    """
    assert T.contrast_ratio(T.BORDER_SUBTLE, T.SURFACE_PANEL) < 3.0
    assert T.contrast_ratio(T.BORDER_STRONG, T.SURFACE_PANEL) >= 3.0


def test_the_body_carries_the_fill_and_the_wrapper_carries_the_outer_surface(
    frame: object,
) -> None:
    section = SectionPanel(frame, title="X", surface="panel", outer_surface="base")
    assert _rgb(section.body.GetBackgroundColour()) == T.SURFACE_PANEL
    assert _rgb(section.GetBackgroundColour()) == T.SURFACE_BASE
    assert section.surface == "panel"


def test_children_go_into_body_and_add_delegates_to_the_body_sizer(frame: object) -> None:
    section = SectionPanel(frame, title="X")
    child = wx.Panel(section.body)
    section.add(child, 1, wx.EXPAND)
    assert section.sizer.GetItem(child) is not None
    assert child.GetParent() is section.body


def test_set_title_relabels_and_is_a_no_op_without_a_heading(frame: object) -> None:
    section = SectionPanel(frame, title="X")
    section.set_title("Y")
    assert section.heading.GetLabel() == "Y"
    SectionPanel(frame, title=None).set_title("Z")  # must not raise


def test_zero_padding_gives_the_body_the_content_sizer_directly(frame: object) -> None:
    """padding=0 is a real mode: the archetype summary's well fills its card."""
    section = SectionPanel(frame, title="X", padding=0)
    assert section.body.GetSizer() is section.sizer


def test_no_static_box_survives_in_the_widget_tree() -> None:
    """wxMSW draws the StaticBox groove at #DCDCDC and ignores every colour call."""
    root = Path(__file__).resolve().parent.parent
    offenders = [
        path.relative_to(root).as_posix()
        for path in (root / "widgets").rglob("*.py")
        if "wx.StaticBox(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        "wx.StaticBox draws a near-white etched groove with the label sitting on "
        f"it; use widgets.section.SectionPanel instead. Found in: {offenders}"
    )
