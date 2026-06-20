"""Semi-automated sideboard-guide recording (issue #782).

A fast alternative to the per-entry :class:`GuideEntryDialog` flow: the user
picks an ordered list of matchups, then walks them one at a time. For each
matchup they drag cards between the mainboard and sideboard (using the #781
split view) to express the plan and click *Save & Next*; the app diffs the
current board against the base 75 snapshot, stores that diff as the matchup's
guide entry, resets the board to the base, and advances. Matchups the user
doesn't change record as "no changes".

The recorded entries reuse the existing guide data model and persistence
(``sideboard_guide_entries`` + ``_persist_guide_for_current``), so they show up
in the guide list, export to CSV, and remain editable in the existing dialog.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class _GuideRecordBar(wx.MiniFrame):
    """Small floating bar that drives the record walk without blocking the deck.

    It floats over the main window (it doesn't steal focus) so the user can keep
    dragging cards between zones while it shows progress and the step controls.
    """

    def __init__(
        self,
        parent: wx.Window,
        *,
        t: Callable[..., str],
        on_next: Callable[[], None],
        on_skip: Callable[[], None],
        on_finish: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        super().__init__(
            parent,
            title=t("guide.record.bar_title"),
            style=wx.CAPTION | wx.FRAME_FLOAT_ON_PARENT | wx.FRAME_TOOL_WINDOW,
        )
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        self.progress_label = wx.StaticText(panel, label="")
        font = self.progress_label.GetFont()
        font.MakeBold()
        self.progress_label.SetFont(font)
        sizer.Add(self.progress_label, 0, wx.ALL, 8)

        instructions = wx.StaticText(panel, label=t("guide.record.instructions"))
        sizer.Add(instructions, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in (
            ("guide.record.next", on_next),
            ("guide.record.skip", on_skip),
            ("guide.record.finish", on_finish),
            ("guide.record.cancel", on_cancel),
        ):
            btn = wx.Button(panel, label=t(label))
            btn.Bind(wx.EVT_BUTTON, lambda _evt, h=handler: h())
            row.Add(btn, 0, wx.RIGHT, 6)
        sizer.Add(row, 0, wx.ALL, 8)

        panel.Fit()
        self.Fit()
        # The window-close [x] cancels the walk.
        self.Bind(wx.EVT_CLOSE, lambda _evt: on_cancel())

    def set_progress(self, text: str) -> None:
        self.progress_label.SetLabel(text)


class SideboardGuideRecordHandlers(_Base):
    """Record-mode workflow for building a sideboard guide from drag diffs."""

    # ----- entry point (wired to the guide panel's Record button) -----
    def _on_record_guide(self: AppFrame) -> None:
        if getattr(self, "_guide_record", None):
            return  # already recording
        if not self.zone_cards.get("main"):
            wx.MessageBox(
                self._t("guide.record.no_deck"),
                self._t("guide.record.mode_title"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        archetypes = self._record_choose_archetypes()
        if not archetypes:
            return
        self._record_start(archetypes)

    # ----- archetype-list selection -----
    def _record_choose_archetypes(self: AppFrame) -> list[str] | None:
        title = self._t("guide.record.mode_title")
        dlg = wx.SingleChoiceDialog(
            self,
            self._t("guide.record.mode_prompt"),
            title,
            [self._t("guide.record.mode_curated"), self._t("guide.record.mode_coverage")],
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            mode = dlg.GetSelection()
        finally:
            dlg.Destroy()
        return self._record_curated_list() if mode == 0 else self._record_coverage_list()

    def _record_curated_list(self: AppFrame) -> list[str] | None:
        names = [a.get("name", "") for a in getattr(self, "archetypes", []) if a.get("name")]
        if not names:
            wx.MessageBox(
                self._t("guide.record.no_archetypes"),
                self._t("guide.record.mode_title"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return None
        dlg = wx.MultiChoiceDialog(
            self,
            self._t("guide.record.curated_prompt"),
            self._t("guide.record.curated_title"),
            names,
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            chosen = [names[i] for i in dlg.GetSelections()]
        finally:
            dlg.Destroy()
        if not chosen:
            wx.MessageBox(
                self._t("guide.record.no_selection"),
                self._t("guide.record.mode_title"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return None
        return chosen

    def _record_coverage_list(self: AppFrame) -> list[str] | None:
        dlg = wx.TextEntryDialog(
            self,
            self._t("guide.record.coverage_prompt"),
            self._t("guide.record.coverage_title"),
            "95",
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            raw = dlg.GetValue()
        finally:
            dlg.Destroy()
        try:
            pct = float(raw)
        except (TypeError, ValueError):
            pct = 95.0
        pct = max(1.0, min(100.0, pct))
        counts = self._record_metagame_counts()
        if not counts:
            wx.MessageBox(
                self._t("guide.record.no_archetypes"),
                self._t("guide.record.coverage_title"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return None
        return self._record_coverage_select(counts, pct)

    def _record_metagame_counts(self: AppFrame) -> dict[str, int]:
        """Per-archetype play counts for the current format, however the stats
        store nests them (keyed by format, or already this format's dict)."""
        fmt = self.controller.current_format
        try:
            raw = self.controller.metagame_service.get_stats_for_format(fmt) or {}
        except Exception:
            return {}
        sources: list[dict[str, Any]] = []
        nested = raw.get(fmt) if isinstance(raw, dict) else None
        if isinstance(nested, dict):
            sources.append(nested)
        if isinstance(raw, dict):
            sources.append(raw)
        for source in sources:
            counts: dict[str, int] = {}
            for name, data in source.items():
                if name == "timestamp" or not isinstance(data, dict):
                    continue
                results = data.get("results")
                if not isinstance(results, dict):
                    continue
                total = sum(v for v in results.values() if isinstance(v, (int, float)))
                if total > 0:
                    counts[name] = int(total)
            if counts:
                return counts
        return {}

    @staticmethod
    def _record_coverage_select(counts: dict[str, int], pct: float) -> list[str]:
        """Top archetypes by share whose cumulative share first reaches ``pct``."""
        grand = sum(counts.values())
        if grand <= 0:
            return []
        ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        selected: list[str] = []
        cumulative = 0.0
        for name, count in ordered:
            selected.append(name)
            cumulative += count / grand * 100
            if cumulative >= pct:
                break
        return selected

    # ----- record-mode lifecycle -----
    def _record_start(self: AppFrame, archetypes: list[str]) -> None:
        self._guide_record = {
            "archetypes": archetypes,
            "index": 0,
            "base_main": [dict(c) for c in self.zone_cards.get("main", [])],
            "base_side": [dict(c) for c in self.zone_cards.get("side", [])],
        }
        self._guide_record_bar = _GuideRecordBar(
            self,
            t=self._t,
            on_next=lambda: self._record_advance(skip=False),
            on_skip=lambda: self._record_advance(skip=True),
            on_finish=self._record_finish,
            on_cancel=self._record_cancel,
        )
        self._update_record_bar()
        # Park the bar at the top-right of the window, clear of the deck zones.
        frame_rect = self.GetScreenRect()
        bar_size = self._guide_record_bar.GetSize()
        self._guide_record_bar.SetPosition(
            wx.Point(frame_rect.GetRight() - bar_size.GetWidth() - 24, frame_rect.GetTop() + 80)
        )
        self._guide_record_bar.Show()

    def _record_advance(self: AppFrame, skip: bool) -> None:
        rec = getattr(self, "_guide_record", None)
        if not rec:
            return
        archetype = rec["archetypes"][rec["index"]]
        if skip:
            play_out, play_in = {}, {}
        else:
            play_out, play_in = self._record_diff(rec["base_main"], self.zone_cards.get("main", []))
        self._record_store_entry(archetype, play_out, play_in)
        self._persist_guide_for_current()
        self._refresh_guide_view()
        rec["index"] += 1
        if rec["index"] >= len(rec["archetypes"]):
            self._record_finish()
            return
        self._record_reset_zones()
        self._update_record_bar()

    def _record_finish(self: AppFrame) -> None:
        rec = getattr(self, "_guide_record", None)
        if not rec:
            self._record_teardown()
            return
        # Matchups the user never reached count as "no sideboard changes".
        for name in rec["archetypes"][rec["index"] :]:
            self._record_store_entry(name, {}, {})
        self._persist_guide_for_current()
        self._refresh_guide_view()
        self._record_reset_zones()
        total = len(rec["archetypes"])
        self._record_teardown()
        self._set_status("guide.record.done", count=total)

    def _record_cancel(self: AppFrame) -> None:
        if not getattr(self, "_guide_record", None):
            self._record_teardown()
            return
        self._record_reset_zones()
        self._record_teardown()

    def _record_teardown(self: AppFrame) -> None:
        bar = getattr(self, "_guide_record_bar", None)
        self._guide_record_bar = None
        self._guide_record = None
        if bar:
            bar.Destroy()

    # ----- helpers -----
    def _record_reset_zones(self: AppFrame) -> None:
        rec = getattr(self, "_guide_record", None)
        if not rec:
            return
        self.zone_cards["main"] = [dict(c) for c in rec["base_main"]]
        self.zone_cards["side"] = [dict(c) for c in rec["base_side"]]
        self._after_zone_change("main")
        self._after_zone_change("side")

    def _update_record_bar(self: AppFrame) -> None:
        rec = getattr(self, "_guide_record", None)
        bar = getattr(self, "_guide_record_bar", None)
        if not rec or not bar:
            return
        bar.set_progress(
            self._t(
                "guide.record.progress",
                archetype=rec["archetypes"][rec["index"]],
                current=rec["index"] + 1,
                total=len(rec["archetypes"]),
            )
        )

    @staticmethod
    def _record_diff(
        base_main: list[dict[str, Any]], current_main: list[dict[str, Any]]
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Diff the mainboard against the base 75.

        Returns ``(out, in)`` where ``out`` are cards whose mainboard count
        dropped (sided out) and ``in`` are cards whose count rose (sided in).
        Cross-zone moves are main<->side, so the mainboard delta captures both
        directions of the plan.
        """

        def _counts(cards: list[dict[str, Any]]) -> dict[str, int]:
            counts: dict[str, int] = {}
            for card in cards:
                try:
                    counts[card["name"]] = counts.get(card["name"], 0) + int(card.get("qty", 0))
                except (TypeError, ValueError):
                    continue
            return counts

        base = _counts(base_main)
        current = _counts(current_main)
        out: dict[str, int] = {}
        cards_in: dict[str, int] = {}
        for name in set(base) | set(current):
            delta = current.get(name, 0) - base.get(name, 0)
            if delta < 0:
                out[name] = -delta
            elif delta > 0:
                cards_in[name] = delta
        return out, cards_in

    def _record_store_entry(
        self: AppFrame, archetype: str, play_out: dict[str, int], play_in: dict[str, int]
    ) -> None:
        """Store/replace ``archetype``'s entry (play == draw by default, #782)."""
        entry = {
            "archetype": archetype,
            "play_out": play_out,
            "play_in": play_in,
            "draw_out": dict(play_out),
            "draw_in": dict(play_in),
            "notes": "",
        }
        for index, existing in enumerate(self.sideboard_guide_entries):
            if existing.get("archetype") == archetype:
                self.sideboard_guide_entries[index] = entry
                return
        self.sideboard_guide_entries.append(entry)
