"""Deck version-history command handlers: graph readout, saves, and moves.

The graph is painted pixels, so a screenshot can show that it *looks* like a
fork but not that the right commit forked. ``deck_history`` reports the same
placement the canvas paints -- row, lane, branch labels, HEAD -- so a script can
assert the shape and the screenshot is left to prove it rendered.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class DeckHistoryMixin(_Base):
    """Read and drive the deck version graph."""

    def _history_panel(self) -> Any:
        return getattr(self.frame, "deck_history_panel", None)

    def _handle_deck_name(self, name: str | None = None) -> dict[str, Any]:
        """Read the deck's name, or set it the way clicking the label does.

        Setting it here is the rename action without the text dialog, which is
        also how a script gets a deck named without the first save's details
        dialog -- and a modal starves this socket (see ``automation/README.md``).
        """
        from services.deck_name import deck_name_of, set_deck_name

        deck = self.frame.controller.deck_repo.get_current_deck()
        if name is not None:
            if deck is None:
                deck = {"source": "manual"}
                self.frame.controller.deck_repo.set_current_deck(deck)
            stored = set_deck_name(deck, name)
            if not stored:
                return {"named": False, "error": f"{name!r} is not a usable name"}
            self.frame.refresh_deck_name_displays()
            panel = self._history_panel()
            if panel is not None:
                self._refresh_and_settle(panel)

        return {
            "named": bool(deck_name_of(deck)),
            "name": deck_name_of(deck),
            "display": self.frame.deck_name_display_text(),
        }

    def _handle_deck_save(self) -> dict[str, Any]:
        """Save through the real ``on_save_clicked``.

        A named deck takes the branch that opens no dialog, which is the whole
        point of the flow under test; an unnamed one would open the details
        dialog and starve the socket, so that is refused rather than hung.
        """
        from services.deck_name import deck_file_for, has_deck_name

        controller = self.frame.controller
        deck = controller.deck_repo.get_current_deck()
        if not has_deck_name(deck):
            return {"saved": False, "error": "Deck has no name; set one first"}

        expected = deck_file_for(deck, controller.resolve_deck_dialog_dir())
        self.frame.on_save_clicked(None)
        return {"saved": True, "path": str(expected)}

    @staticmethod
    def _settle(panel: Any, timeout: float = 10.0) -> bool:
        """Pump until the panel's pending read has been painted.

        The graph is read on a background worker, so ``refresh_history`` returns
        before the answer exists. Every readout here is asserted against by the
        scripts that call it, so they have to see the settled graph rather than
        whatever the previous deck left behind. This handler already runs on the
        UI thread (``transport`` marshals it there), so yielding is what lets
        the worker's ``wx.CallAfter`` land.
        """
        import time

        deadline = time.monotonic() + timeout
        while panel.refresh_pending and time.monotonic() < deadline:
            wx.Yield()
            time.sleep(0.005)
        return not panel.refresh_pending

    def _refresh_and_settle(self, panel: Any) -> bool:
        panel.refresh_history()
        return self._settle(panel)

    def _handle_deck_history(self) -> dict[str, Any]:
        """The version graph as the canvas has it placed."""
        from widgets.panels.deck_history_panel.layout import build_layout

        panel = self._history_panel()
        if panel is None:
            return {"error": "History panel not built"}
        settled = self._refresh_and_settle(panel)
        layout = build_layout(panel.graph)
        deck_key = panel.current_deck_key()
        return {
            "deck_key": deck_key,
            "settled": settled,
            "branch": panel.vcs_service.current_branch(deck_key),
            "branches": panel.vcs_service.list_branches(deck_key),
            "selected": panel.selected_sha,
            "baseline": panel.baseline_sha,
            "lane_count": layout.lane_count,
            "nodes": [
                {
                    "sha": node.sha[:7],
                    "row": node.row,
                    "lane": node.lane,
                    "message": node.graph_commit.label,
                    "branches": list(node.graph_commit.commit.branches),
                    "is_head": node.graph_commit.commit.is_head,
                    "is_baseline": node.graph_commit.commit.is_baseline,
                    "parents": [p[:7] for p in node.graph_commit.commit.parents],
                }
                for node in sorted(layout.nodes, key=lambda n: n.row)
            ],
            "edges": [
                {
                    "child": edge.child_sha[:7],
                    "parent": edge.parent_sha[:7],
                    "is_fork": edge.is_fork,
                }
                for edge in layout.edges
            ],
        }

    def _handle_deck_history_save(self, message: str | None = None) -> dict[str, Any]:
        """Commit the loaded decklist as a version, bypassing the Save As dialog.

        The real Save flow opens two modal dialogs, and a modal starves the
        automation socket (see ``automation/README.md``), so a scripted save
        goes through the same service call the dialog ends at instead.
        """
        from services.deck_vcs_service import deck_key_for, get_deck_vcs_service

        panel = self._history_panel()
        if panel is None:
            return {"error": "History panel not built"}
        deck_text = self.frame.controller.build_deck_text(self.frame.zone_cards).strip()
        if not deck_text:
            return {"saved": False, "error": "No deck loaded"}

        deck_file = panel.current_deck_file()
        deck_key = deck_key_for(self.frame.controller.deck_repo.get_current_deck(), deck_file)
        sha = get_deck_vcs_service().record_save(deck_key, deck_text, message=message)
        if deck_file is not None:
            # Keep the user-facing file in step with the version just recorded,
            # which is what the real save path does by writing it first.
            from repositories.deck_vcs_repository.normalize import normalize_decklist
            from utils.atomic_io import atomic_write_text

            atomic_write_text(Path(deck_file), normalize_decklist(deck_text))
        self._refresh_and_settle(panel)
        return {"saved": sha is not None, "sha": (sha or "")[:7], "deck_key": deck_key}

    #: Preview notebook page order, as ``_build_body`` adds them.
    VIEWS = {"decklist": 0, "diff": 1}

    def _handle_deck_history_select(self, sha: str, view: str | None = None) -> dict[str, Any]:
        """Select a node — the preview path, which must not check anything out.

        ``view`` brings the decklist or the diff page to the front. The values
        are returned either way; this is for the screenshot, since the preview
        notebook is inside the panel and the generic ``switch_tab`` only reaches
        the two top-level notebooks.
        """
        panel = self._history_panel()
        if panel is None:
            return {"error": "History panel not built"}
        full = self._resolve_sha(panel, sha)
        if full is None:
            return {"error": f"No such version: {sha}"}
        panel.on_node_selected(full)
        if view is not None:
            if view not in self.VIEWS:
                return {"error": f"Unknown view: {view}"}
            panel.preview_tabs.SetSelection(self.VIEWS[view])
        return {
            "selected": full[:7],
            "view": view,
            "decklist": panel.preview_text.GetValue(),
            "diff": panel.diff_text.GetValue(),
        }

    def _handle_deck_history_checkout(self, sha: str) -> dict[str, Any]:
        """Check out a version, writing the user's deck file."""
        panel = self._history_panel()
        if panel is None:
            return {"error": "History panel not built"}
        full = self._resolve_sha(panel, sha)
        if full is None:
            return {"error": f"No such version: {sha}"}
        deck_key = panel.current_deck_key()
        deck_file = panel.current_deck_file()
        branch, text = panel.vcs_service.checkout(deck_key, full, deck_file=deck_file)
        self.frame._on_history_checkout(text)
        return {"checked_out": full[:7], "branch": branch, "deck_file": str(deck_file or "")}

    def _handle_deck_history_branch(self, sha: str, name: str) -> dict[str, Any]:
        panel = self._history_panel()
        if panel is None:
            return {"error": "History panel not built"}
        full = self._resolve_sha(panel, sha)
        if full is None:
            return {"error": f"No such version: {sha}"}
        created = panel.vcs_service.create_branch(panel.current_deck_key(), name, full)
        self._refresh_and_settle(panel)
        return {"created": created, "at": full[:7]}

    def _handle_deck_history_switch(self, name: str) -> dict[str, Any]:
        panel = self._history_panel()
        if panel is None:
            return {"error": "History panel not built"}
        text = panel.vcs_service.switch_branch(
            panel.current_deck_key(), name, deck_file=panel.current_deck_file()
        )
        self.frame._on_history_checkout(text)
        return {"branch": name}

    def _handle_deck_history_baseline(self, sha: str | None = None) -> dict[str, Any]:
        panel = self._history_panel()
        if panel is None:
            return {"error": "History panel not built"}
        full = self._resolve_sha(panel, sha) if sha else None
        panel.set_baseline(full)
        return {"baseline": (full or "")[:7], "diff": panel.diff_text.GetValue()}

    @staticmethod
    def _resolve_sha(panel: Any, sha: str) -> str | None:
        """Accept a short sha, the way every other git tool does."""
        return next((g.sha for g in panel.graph if g.sha.startswith(sha)), None)
