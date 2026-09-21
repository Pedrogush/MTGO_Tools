"""Deck version-history command handlers: graph readout, saves, and moves.

The graph is painted pixels, so a screenshot can show that it *looks* like a
fork but not that the right commit forked. ``deck_history`` reports the same
placement the canvas paints -- row, lane, branch labels, HEAD -- so a script can
assert the shape and the screenshot is left to prove it rendered.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class DeckHistoryMixin(_Base):
    """Read and drive the deck version graph."""

    def _history_panel(self) -> Any:
        return getattr(self.frame, "deck_history_panel", None)

    def _handle_deck_history(self) -> dict[str, Any]:
        """The version graph as the canvas has it placed."""
        from widgets.panels.deck_history_panel.layout import build_layout

        panel = self._history_panel()
        if panel is None:
            return {"error": "History panel not built"}
        panel.refresh_history()
        layout = build_layout(panel._graph)
        deck_key = panel.current_deck_key()
        return {
            "deck_key": deck_key,
            "branch": panel.vcs_service.current_branch(deck_key),
            "branches": panel.vcs_service.list_branches(deck_key),
            "selected": panel._selected_sha,
            "baseline": panel._baseline_sha,
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
        panel.refresh_history()
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
        panel.refresh_history()
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
        return next((g.sha for g in panel._graph if g.sha.startswith(sha)), None)
