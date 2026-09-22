"""Behaviour for the deck history tab: selecting, previewing, and moving.

The split that matters here is between *looking* and *moving*. Selecting a node
reads a blob out of the object store and fills the preview -- nothing on disk
changes. Checkout, branch creation and branch switching all rewrite the user's
decklist file, so each is an explicit menu action with its own confirmation
path, never a consequence of a click.

Reading the history is disk work and runs on the app's background worker, behind
the same stale-token guard the Baseline tab uses: the graph, the branches and
the opening preview arrive together as one :class:`HistorySnapshot`, and only
applying it touches wx. It used to run inline, which put a deck's whole history
on the UI thread on every save, every deck load and every visit to this tab --
over three seconds for a deck with a hundred versions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import wx
from loguru import logger

from services.deck_vcs_service import HistorySnapshot, VersionPreview
from utils.perf import perf_phase
from widgets.panels.deck_history_panel.layout import build_layout, diff_lines

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
        """Read the deck's history on the worker, then repaint from the answer."""
        self._refresh_deck_name()
        deck_key = self.current_deck_key()
        # A selection and a pinned baseline are shas in *one* deck's repo, so
        # carrying them across a deck change points them at commits that do not
        # exist there.
        if deck_key != self._last_deck_key:
            self._last_deck_key = deck_key
            self._selected_sha = None
            self._baseline_sha = None

        self._run_token += 1
        token = self._run_token
        service = self.vcs_service
        selected = self._selected_sha
        baseline = self._baseline_sha

        def work() -> HistorySnapshot:
            # Timed on both sides of the hand-off: this one is allowed to be
            # slow and the paint below is not, so a regression that moves work
            # back onto the UI thread shows up as the second number growing.
            with perf_phase("deck history read (worker)"):
                return service.read_history(deck_key, selected_sha=selected, baseline_sha=baseline)

        def done(snapshot: HistorySnapshot) -> None:
            if token != self._run_token:
                return  # a newer refresh has started; this answer is stale
            self._refresh_pending = False
            self._apply_snapshot(snapshot)

        def failed(exc: Exception) -> None:
            if token != self._run_token:
                return
            self._refresh_pending = False
            logger.warning(f"Could not read deck history for {deck_key}: {exc}")
            self._apply_snapshot(HistorySnapshot())

        if self.worker is None:
            # No worker (tests, or a standalone panel): read inline.
            try:
                done(work())
            except Exception as exc:  # noqa: BLE001
                failed(exc)
            return

        self._refresh_pending = True
        self.worker.submit(work, on_success=done, on_error=failed)

    @property
    def refresh_pending(self) -> bool:
        """Whether a read is still on its way to the canvas.

        The graph is read on a worker, so what is painted lags a refresh by a
        few hundred milliseconds. A caller that has to read the *settled* graph
        -- the automation harness does, since its readouts are asserted against
        -- waits on this rather than racing it.
        """
        return self._refresh_pending

    def _apply_snapshot(self, snapshot: HistorySnapshot) -> None:
        """Put a history that has already been read on screen. wx only."""
        with perf_phase("deck history paint (ui)"):
            self._paint_snapshot(snapshot)
        # The rail beside the deck tables shows the same versions. It is handed
        # this snapshot rather than reading its own, so a deck's history is read
        # once however many views are looking at it.
        if self._on_snapshot is not None:
            self._on_snapshot(snapshot)

    def _paint_snapshot(self, snapshot: HistorySnapshot) -> None:
        self._graph = list(snapshot.graph)
        self._selected_sha = snapshot.selected_sha

        # Frozen for the same reason the Baseline tree is: every one of these
        # repaints on its own otherwise, and a long history is a lot of them.
        self.Freeze()
        try:
            self.graph_canvas.set_layout(build_layout(self._graph))
            if self._selected_sha is not None:
                self.graph_canvas.select(self._selected_sha)
            self._apply_branches(snapshot.branches, snapshot.current_branch)
            self._apply_preview(snapshot.preview)
        finally:
            self.Thaw()

    def _refresh_deck_name(self) -> None:
        """Show the loaded deck's name, or the prompt when it has none.

        Read from the record rather than cached, so this tab agrees with the
        deck tables header without either knowing about the other.
        """
        from services.deck_name import deck_name_of

        name = deck_name_of(self.deck_repo.get_current_deck())
        self.set_deck_name_text(name or self._t("deck_name.unset"), named=bool(name))

    def _apply_branches(self, branches: Sequence[str], current: str | None) -> None:
        branches = list(branches)
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
        """Re-read the selected version. Two blob reads against a graph in hand.

        Kept inline rather than deferred: the graph is already read, so this is
        one session and two small reads, and a click on a node should fill the
        panes now rather than a frame later.
        """
        sha = self._selected_sha
        if sha is None:
            self._apply_preview(None)
            return
        self._apply_preview(
            self.vcs_service.read_preview(
                self.current_deck_key(), self._graph, sha, self._baseline_sha
            )
        )

    def _apply_preview(self, preview: VersionPreview | None) -> None:
        """Put a preview that has already been read on screen. wx only."""
        if preview is None:
            self.preview_text.SetValue("")
            self.diff_text.SetValue("")
            self.baseline_label.SetLabel(self._t("history.baseline.none"))
            return

        self.preview_text.SetValue(preview.text)
        base = preview.base_sha
        if base is None or preview.diff is None:
            self.diff_text.SetValue(self._t("history.diff.no_baseline"))
            self.baseline_label.SetLabel(self._t("history.baseline.none"))
            return
        # Net card changes, not line changes: cutting a playset to two is one
        # "-2", which is the change the player made. See :func:`diff_lines`.
        lines = diff_lines(
            preview.diff,
            before_label=base[:7],
            after_label=preview.sha[:7],
            main_heading=self._t("history.diff.maindeck"),
            sideboard_heading=self._t("history.diff.sideboard"),
            identical=self._t("history.diff.identical"),
        )
        self.diff_text.SetValue("\n".join(lines))
        self.baseline_label.SetLabel(
            self._t("history.baseline.explicit", sha=base[:7])
            if self._baseline_sha
            else self._t("history.baseline.parent", sha=base[:7])
        )

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

        Asked no confirmation. Moving between versions is the feature, and a
        modal on every move makes it cost two clicks instead of one; the version
        being left is still a node on the graph, so the move is undone by making
        the opposite one. The status bar says where the deck landed.

        What a confirmation *would* protect is unsaved work: the zones are
        rewritten from the version, so edits never committed are gone. Saving is
        a single click and makes a version of its own, which is the answer to
        that rather than a dialog in front of every checkout.
        """
        deck_key = self.current_deck_key()
        deck_file = self.current_deck_file()
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
