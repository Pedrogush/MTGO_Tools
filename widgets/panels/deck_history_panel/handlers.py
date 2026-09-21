"""Behaviour for the deck history tab: selecting, previewing, and moving.

The split that matters here is between *looking* and *moving*. Selecting a node
reads a blob out of the object store and fills the preview -- nothing on disk
changes. Checkout, branch creation and branch switching all rewrite the user's
decklist file, so each is an explicit menu action with its own confirmation
path, never a consequence of a click.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

from repositories.deck_vcs_repository.diffs import unified_lines
from widgets.panels.deck_history_panel.layout import build_layout, changed_lines_only

if TYPE_CHECKING:
    from widgets.panels.deck_history_panel.protocol import DeckHistoryPanelProto

    _Base = DeckHistoryPanelProto
else:
    _Base = object

_MENU_CHECKOUT = wx.NewIdRef()
_MENU_BRANCH = wx.NewIdRef()
_MENU_BASELINE = wx.NewIdRef()


class DeckHistoryPanelHandlersMixin(_Base):
    """Graph refresh, node selection, and the version-moving actions."""

    # ------------------------------------------------------------------ refresh ------------------------------------------------------------------
    def on_shown(self) -> None:
        """Tab became visible: show the history of whatever deck is loaded now.

        A save that happened while another tab was on screen, or a deck loaded
        since this tab was last looked at, both leave the graph stale; rebuilding
        on the way in is cheaper than trying to catch every path that could have
        invalidated it.
        """
        self.refresh_history()

    def refresh_history(self) -> None:
        """Rebuild the graph from the deck's repo and repaint."""
        deck_key = self.current_deck_key()
        # A selection and a pinned baseline are shas in *one* deck's repo, so
        # carrying them across a deck change points them at commits that do not
        # exist there.
        if deck_key != self._last_deck_key:
            self._last_deck_key = deck_key
            self._selected_sha = None
            self._baseline_sha = None
        try:
            self._graph = self.vcs_service.build_graph(deck_key)
        except Exception as exc:  # noqa: BLE001 - a broken repo must not kill the tab
            logger.warning(f"Could not read deck history for {deck_key}: {exc}")
            self._graph = []

        self.graph_canvas.set_layout(build_layout(self._graph))
        self._refresh_branches(deck_key)

        if self._selected_sha is None and self._graph:
            head = next((g for g in self._graph if g.commit.is_head), self._graph[0])
            self._select_sha(head.sha)
        else:
            self._refresh_preview()

    def _refresh_branches(self, deck_key: str) -> None:
        branches = self.vcs_service.list_branches(deck_key)
        current = self.vcs_service.current_branch(deck_key)
        self.branch_choice.Set(branches)
        if current in branches:
            self.branch_choice.SetSelection(branches.index(current))
        self.branch_choice.Enable(bool(branches))
        self.branch_label.SetLabel(
            self._t("history.on_branch", branch=current)
            if current
            else self._t("history.no_branch")
        )

    # ------------------------------------------------------------------ selection ------------------------------------------------------------------
    def _select_sha(self, sha: str) -> None:
        self._selected_sha = sha
        self.graph_canvas.select(sha)
        self._refresh_preview()

    def on_node_selected(self, sha: str) -> None:
        """A node was clicked. Preview only -- this must never check anything out."""
        self._select_sha(sha)

    def _refresh_preview(self) -> None:
        sha = self._selected_sha
        if sha is None:
            self.preview_text.SetValue("")
            self.diff_text.SetValue("")
            return
        deck_key = self.current_deck_key()
        try:
            self.preview_text.SetValue(self.vcs_service.version_text(deck_key, sha))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not read version {sha[:7]}: {exc}")
            self.preview_text.SetValue("")
            return

        base = self._baseline_sha or self._parent_of(sha)
        if base is None or base == sha:
            self.diff_text.SetValue(self._t("history.diff.no_baseline"))
            self.baseline_label.SetLabel(self._t("history.baseline.none"))
            return
        try:
            lines = unified_lines(
                self.vcs_service.version_text(deck_key, base),
                self.vcs_service.version_text(deck_key, sha),
                before_label=base[:7],
                after_label=sha[:7],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not diff {base[:7]}..{sha[:7]}: {exc}")
            return
        # Only what moved: see :func:`changed_lines_only`. A diff whose every
        # remaining line is a file header changed nothing the reader can act on,
        # so it reads as identical rather than as two bare header lines.
        lines = changed_lines_only(lines)
        changed = [line for line in lines if not line.startswith(("---", "+++"))]
        self.diff_text.SetValue("\n".join(lines) if changed else self._t("history.diff.identical"))
        self.baseline_label.SetLabel(
            self._t("history.baseline.explicit", sha=base[:7])
            if self._baseline_sha
            else self._t("history.baseline.parent", sha=base[:7])
        )

    def _parent_of(self, sha: str) -> str | None:
        entry = next((g for g in self._graph if g.sha == sha), None)
        if entry is None or not entry.commit.parents:
            return None
        return entry.commit.parents[0]

    # ------------------------------------------------------------------ context menu ------------------------------------------------------------------
    def on_node_context(self, sha: str, position: wx.Point) -> None:
        menu = wx.Menu()
        menu.Append(_MENU_CHECKOUT, self._t("history.menu.checkout"))
        menu.Append(_MENU_BRANCH, self._t("history.menu.branch_here"))
        menu.Append(_MENU_BASELINE, self._t("history.menu.set_baseline"))
        menu.Bind(wx.EVT_MENU, lambda _e: self.checkout_version(sha), id=_MENU_CHECKOUT)
        menu.Bind(wx.EVT_MENU, lambda _e: self.create_branch_at(sha), id=_MENU_BRANCH)
        menu.Bind(wx.EVT_MENU, lambda _e: self.set_baseline(sha), id=_MENU_BASELINE)
        self.graph_canvas.PopupMenu(menu, position)
        menu.Destroy()

    # ------------------------------------------------------------------ actions ------------------------------------------------------------------
    def set_baseline(self, sha: str | None) -> None:
        """Pin the version every diff is taken against.

        Phase 3 hangs the archetype baseline off this: when a deck's root commit
        *is* the computed archetype baseline, "diff vs. baseline" is just this
        pointed at the root, with no separate concept needed.
        """
        self._baseline_sha = sha
        self._refresh_preview()
        if sha:
            self._status("app.status.deck_history_baseline", sha=sha[:7])

    def create_branch_at(self, sha: str) -> None:
        deck_key = self.current_deck_key()
        suggested = f"branch-from-{sha[:7]}"
        with wx.TextEntryDialog(
            self, self._t("history.branch.prompt"), self._t("history.branch.title"), suggested
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            name = dlg.GetValue().strip()
        if not name:
            return
        try:
            created = self.vcs_service.create_branch(deck_key, name, sha)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not create branch {name}: {exc}")
            wx.MessageBox(str(exc), self._t("history.branch.title"), wx.OK | wx.ICON_ERROR)
            return
        self._status("app.status.deck_history_branched", branch=created)
        self.refresh_history()

    def checkout_version(self, sha: str) -> None:
        """Move onto ``sha``, rewriting the user's decklist file.

        This is the one action here that touches the file the user keeps, so it
        asks first -- and it says what it will do to it.
        """
        deck_key = self.current_deck_key()
        deck_file = self.current_deck_file()
        confirm = wx.MessageBox(
            self._t("history.checkout.confirm", sha=sha[:7]),
            self._t("history.checkout.title"),
            wx.YES_NO | wx.ICON_QUESTION,
        )
        if confirm != wx.YES:
            return
        try:
            branch, text = self.vcs_service.checkout(deck_key, sha, deck_file=deck_file)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Checkout of {sha[:7]} failed: {exc}")
            wx.MessageBox(str(exc), self._t("history.checkout.title"), wx.OK | wx.ICON_ERROR)
            return
        self._status("app.status.deck_history_checked_out", branch=branch, sha=sha[:7])
        self._selected_sha = None
        self.refresh_history()
        if self._on_checkout is not None:
            self._on_checkout(text)

    def on_branch_chosen(self, _event: wx.CommandEvent) -> None:
        name = self.branch_choice.GetStringSelection()
        if not name:
            return
        deck_key = self.current_deck_key()
        if name == self.vcs_service.current_branch(deck_key):
            return
        try:
            text = self.vcs_service.switch_branch(
                deck_key, name, deck_file=self.current_deck_file()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not switch to branch {name}: {exc}")
            return
        self._status("app.status.deck_history_switched", branch=name)
        self._selected_sha = None
        self.refresh_history()
        if self._on_checkout is not None:
            self._on_checkout(text)

    def _status(self, key: str, **kwargs: object) -> None:
        if self._on_status_update is not None:
            self._on_status_update(key, **kwargs)
