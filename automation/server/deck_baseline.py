"""Baseline tab command handlers: computing, reading, and rooting.

A screenshot of the tree proves it drew; it cannot prove a card was classified
correctly or that the flex arithmetic is right. ``deck_baseline`` reports the
same numbers the tree is built from so a script can assert them against a
hand-checked expectation.

``deck_baseline_pin_root`` is the other half of the feature: it points the
History tab's diff baseline at the deck's root commit, which -- when that root
*is* the archetype baseline -- is what makes "diff vs. archetype" an ordinary
ancestor diff rather than a second concept.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class DeckBaselineMixin(_Base):
    """Read and drive the archetype baseline tab."""

    def _baseline_panel(self) -> Any:
        return getattr(self.frame, "deck_baseline_panel", None)

    def _handle_deck_baseline(self) -> dict[str, Any]:
        """The computed breakdown, as the tree shows it."""
        panel = self._baseline_panel()
        if panel is None:
            return {"error": "Baseline panel not built"}

        baseline = panel._baseline
        if baseline is None:
            return {
                "pending": bool(panel._pending),
                "computed": False,
                "status": panel.status_label.GetLabel(),
                "target": panel.target_label.GetLabel(),
            }

        from services.archetype_baseline_service import CardRole

        def cards(role: CardRole) -> list[dict[str, Any]]:
            return [
                {
                    "name": card.name,
                    "zone": "sideboard" if card.is_sideboard else "main",
                    "fixed_count": card.fixed_count,
                    "floor": card.frequency.floor_count,
                    "max": card.frequency.max_count,
                    "play_rate": round(card.play_rate, 4),
                    "decks_with": card.frequency.decks_with,
                }
                for card in baseline.by_role(role)
            ]

        return {
            "pending": bool(panel._pending),
            "computed": True,
            "status": panel.status_label.GetLabel(),
            "target": panel.target_label.GetLabel(),
            "archetype": baseline.archetype,
            "format": baseline.mtg_format,
            "pool_size": baseline.pool_size,
            "threshold": baseline.threshold,
            "main": {
                "size": baseline.main.size,
                "fixed": baseline.main.fixed,
                "flex": baseline.main.flex,
            },
            "sideboard": {
                "size": baseline.sideboard.size,
                "fixed": baseline.sideboard.fixed,
                "flex": baseline.sideboard.flex,
            },
            "flex_slots": baseline.flex_slots,
            "staples": cards(CardRole.STAPLE),
            "partial_staples": cards(CardRole.PARTIAL_STAPLE),
            "flex_candidates": [
                {
                    "name": candidate.name,
                    "zone": "sideboard" if candidate.is_sideboard else "main",
                    "play_rate": round(candidate.play_rate, 4),
                    "average_count": round(candidate.average_count, 3),
                    "above_floor": candidate.above_floor,
                }
                for candidate in baseline.flex_candidates
            ],
            "decklist": baseline.decklist(),
        }

    def _handle_deck_baseline_compute(self, threshold: float | None = None) -> dict[str, Any]:
        """Compute the baseline for the archetype selected in Research."""
        panel = self._baseline_panel()
        if panel is None:
            return {"error": "Baseline panel not built"}

        if threshold is not None:
            from widgets.panels.deck_baseline_panel.handlers import THRESHOLD_CHOICES

            wanted = float(threshold)
            index = next(
                (i for i, (_label, value) in enumerate(THRESHOLD_CHOICES) if value == wanted),
                None,
            )
            if index is None:
                allowed = [value for _label, value in THRESHOLD_CHOICES]
                return {"error": f"Threshold {wanted} not one of {allowed}"}
            panel.threshold_choice.SetSelection(index)

        panel.refresh_target()
        panel.compute()
        return {
            "triggered": True,
            "pending": bool(panel._pending),
            "threshold": panel.selected_threshold(),
            "target": panel.target_label.GetLabel(),
        }

    def _handle_deck_baseline_root(self, deck_key: str | None = None) -> dict[str, Any]:
        """The deck's root commit, and whether it is an archetype baseline."""
        from services.archetype_baseline_service import get_archetype_baseline_service

        history = getattr(self.frame, "deck_history_panel", None)
        if deck_key is None:
            if history is None:
                return {"error": "History panel not built"}
            deck_key = history.current_deck_key()

        service = get_archetype_baseline_service()
        sha = service.root_sha(str(deck_key))
        if sha is None:
            return {"deck_key": deck_key, "root": None, "is_baseline_root": False}
        return {
            "deck_key": deck_key,
            "root": sha,
            "is_baseline_root": service.has_baseline_root(str(deck_key)),
            "text": service.vcs_repo.read_commit_text(str(deck_key), sha),
        }

    def _handle_deck_baseline_pin_root(self) -> dict[str, Any]:
        """Pin the History tab's diff baseline to the deck's root commit."""
        from services.archetype_baseline_service import get_archetype_baseline_service

        history = getattr(self.frame, "deck_history_panel", None)
        if history is None:
            return {"error": "History panel not built"}

        deck_key = history.current_deck_key()
        sha = get_archetype_baseline_service().root_sha(deck_key)
        if sha is None:
            return {"pinned": False, "error": f"No version history for {deck_key!r}"}

        history.set_baseline(sha)
        return {"pinned": True, "deck_key": deck_key, "root": sha}

    def _handle_deck_baseline_save_deck(
        self,
        name: str,
        archetype: str | None = None,
        format_name: str | None = None,
    ) -> dict[str, Any]:
        """Save the loaded decklist as a new deck, bypassing the Save dialogs.

        The real Save flow opens a details dialog and then a Save As dialog, and
        a modal starves the automation socket (see ``automation/README.md``), so
        this goes through the same ``controller.save_deck`` call those dialogs
        end at -- which is the call that roots a brand-new deck at its archetype
        baseline. Driving the record_save path directly (``deck_history_save``)
        would skip that and prove nothing about it.
        """
        from pathlib import Path

        controller = self.frame.controller
        deck_content = controller.build_deck_text(self.frame.zone_cards).strip()
        if not deck_content:
            return {"saved": False, "error": "No deck loaded"}

        file_path = Path(controller.deck_save_dir) / f"{name}.txt"
        resolved_format = format_name or controller.current_format
        try:
            saved_path, deck_id = controller.save_deck(
                deck_name=name,
                deck_content=deck_content,
                format_name=resolved_format,
                deck=controller.deck_repo.get_current_deck(),
                file_path=file_path,
                archetype=archetype,
            )
        except Exception as exc:  # noqa: BLE001 - report it rather than dying
            return {"saved": False, "error": str(exc)}

        from services.archetype_baseline_service import get_archetype_baseline_service
        from services.deck_vcs_service import deck_key_for

        deck_key = deck_key_for(None, saved_path)
        service = get_archetype_baseline_service()
        return {
            "saved": True,
            "path": str(saved_path),
            "deck_id": deck_id,
            "deck_key": deck_key,
            "archetype": archetype,
            "format": resolved_format,
            "root": service.root_sha(deck_key),
            "is_baseline_root": service.has_baseline_root(deck_key),
        }

    def _handle_deck_baseline_load_file(self, path: str) -> dict[str, Any]:
        """Load a saved deck file, bypassing the Load Deck dialog.

        Mirrors ``AppFrame.on_load_deck_clicked`` after its ``wx.FileDialog``
        returns -- a modal starves the automation socket, so the dialog is the
        one part skipped. This matters for the baseline flow because saving a
        scraped deck under a new name deliberately leaves the *scraped* deck
        loaded (see the real save handler), so the History tab keeps showing
        that deck's history until the new file is opened.
        """
        from pathlib import Path

        from utils.deck import sanitize_filename

        file_ref = Path(path)
        if not file_ref.exists():
            return {"loaded": False, "error": f"No such deck file: {path}"}

        deck_key = sanitize_filename(file_ref.stem, fallback="manual").lower()
        deck_record: dict[str, Any] = {
            "href": deck_key,
            "name": file_ref.stem,
            "path": str(file_ref),
            "source": "file",
        }
        controller = self.frame.controller
        controller.deck_repo.set_current_deck(deck_record)

        deck_text = file_ref.read_text(encoding="utf-8")
        saved = controller.find_saved_deck(file_ref, deck_text)
        for field in ("format", "archetype"):
            if saved and saved.get(field):
                deck_record[field] = saved[field]

        self.frame._on_deck_content_ready(deck_text, source="file")
        self.frame.refresh_deck_history()
        return {
            "loaded": True,
            "path": str(file_ref),
            "deck_key": deck_key,
            "format": deck_record.get("format"),
            "archetype": deck_record.get("archetype"),
        }
