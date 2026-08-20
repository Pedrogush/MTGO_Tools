"""Comprehensive Rules browser — a tree-and-document help viewer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
import wx.html

from utils.constants import DARK_PANEL, LIGHT_TEXT, SPACE_XS

if TYPE_CHECKING:
    from services.comp_rules_service import CompRulesService, Section, Subsection
from utils.i18n import translate
from widgets.frames.rules_browser.html_render import (
    _DEFAULT_BG,
    _DEFAULT_TEXT,
    render_outline_to_html,
)
from widgets.splitter import DarkSplitter
from widgets.stylize import init_top_level_window


class RulesBrowserFrame(wx.Frame):
    """Tree of sections + subsections on the left, full document on the right.

    Selecting a node in the tree scrolls the right pane to that subsection's
    anchor. Cross-references in body text are anchored locally so clicking
    "rule 702.9" jumps within the same document — wx.html handles the
    ``href="#anchor"`` form natively.
    """

    def __init__(
        self,
        parent: wx.Window | None = None,
        *,
        controller=None,
        locale: str | None = None,
    ) -> None:
        super().__init__(
            parent,
            title=translate(locale, "window.title.rules_browser"),
            size=(900, 720),
            style=wx.DEFAULT_FRAME_STYLE,
        )
        init_top_level_window(self)
        self._locale = locale
        self.controller = controller
        self._service: CompRulesService = controller.comp_rules_service
        self.SetBackgroundColour(DARK_PANEL)

        self._sections: list[Section] = self._service.get_outline()
        self._tree_anchors: dict[wx.TreeItemId, str] = {}
        self._build_ui()
        self._populate_tree()
        self._render_document()
        self.Centre(wx.BOTH)

    # ----------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        self.splitter = DarkSplitter(self)

        self.tree = wx.TreeCtrl(
            self.splitter,
            style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT | wx.NO_BORDER,
        )
        self.tree.SetBackgroundColour(DARK_PANEL)
        self.tree.SetForegroundColour(LIGHT_TEXT)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_tree_select)

        self.doc = wx.html.HtmlWindow(
            self.splitter,
            style=wx.html.HW_SCROLLBAR_AUTO | wx.NO_BORDER,
        )
        self.doc.SetBackgroundColour(DARK_PANEL)
        self.doc.SetBorders(SPACE_XS)

        self.splitter.SplitVertically(self.tree, self.doc, sashPosition=300)
        self.splitter.SetMinimumPaneSize(180)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def _populate_tree(self) -> None:
        self.tree.DeleteAllItems()
        self._tree_anchors = {}
        root = self.tree.AddRoot("rules")
        if not self._sections:
            placeholder = self.tree.AppendItem(
                root,
                translate(self._locale, "rules_browser.tree.empty"),
            )
            self._tree_anchors[placeholder] = ""
            return
        for sec in self._sections:
            label = sec.title if sec.number == 0 else f"{sec.number}. {sec.title}"
            sec_node = self.tree.AppendItem(root, label)
            self._tree_anchors[sec_node] = f"section-{sec.number}"
            for sub in sec.subsections:
                sub_label = _format_subsection_label(sub)
                sub_node = self.tree.AppendItem(sec_node, sub_label)
                self._tree_anchors[sub_node] = sub.rule_id
            self.tree.Expand(sec_node)

    def _render_document(self) -> None:
        if not self._sections:
            empty = translate(self._locale, "rules_browser.body.empty")
            self.doc.SetPage(
                f'<html><body bgcolor="{_DEFAULT_BG}" text="{_DEFAULT_TEXT}">'
                f'<p align="center">{empty}</p></body></html>'
            )
            return
        html = render_outline_to_html(
            self._sections,
            cross_ref_linkifier=self.controller.linkify_cross_refs,
        )
        self.doc.SetPage(html)

    # -------------------------------------------------------------- events

    def _on_tree_select(self, event: wx.TreeEvent) -> None:
        anchor = self._tree_anchors.get(event.GetItem())
        if anchor:
            self.doc.ScrollToAnchor(anchor)
        event.Skip()

    # ----------------------------------------------------------- public api

    def show_anchor(self, anchor: str) -> None:
        """Scroll the right pane to ``anchor`` and surface the frame."""
        if not self.IsShown():
            self.Show()
        self.Raise()
        if anchor:
            self.doc.ScrollToAnchor(anchor)


def _format_subsection_label(sub: Subsection) -> str:
    if sub.rule_id == "glossary":
        return sub.title
    return f"{sub.rule_id}. {sub.title}"
