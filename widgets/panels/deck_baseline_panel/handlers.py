"""Computing and rendering the Baseline tab.

The computation reads a pool of decklists out of the text cache and counts
cards, which is fast but not instant on a large archetype, so it runs on the
app's background worker with the same stale-token guard the Patterns tab uses.

What the tree shows is ordered by how much of the deck is already decided:
staples first, then the partial staples with their floor, then the ranked flex
candidates. The summary line leads with the flex slot count, because that is
the number the whole analysis exists to produce -- "these 55 slots are the
archetype, the other 5 are yours" is the useful sentence, and a decklist alone
cannot say it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from services.archetype_baseline_service import ArchetypeBaseline, CardRole

if TYPE_CHECKING:
    from widgets.panels.deck_baseline_panel.protocol import DeckBaselinePanelProto

    _Base = DeckBaselinePanelProto
else:
    _Base = object


class DeckBaselinePanelHandlersMixin(_Base):
    """Compute/render behaviour for :class:`DeckBaselinePanel`.

    Kept as a mixin with no ``__init__`` so the panel remains the single source
    of truth for instance-state initialization.
    """

    # ------------------------------------------------------------------ selection ------------------------------------------------------------------
    def current_archetype(self) -> dict[str, Any] | None:
        if self._archetype_provider is None:
            return None
        try:
            return self._archetype_provider()
        except Exception as exc:  # noqa: BLE001 - a panel must not die on this
            logger.debug(f"Baseline tab could not read the selected archetype: {exc}")
            return None

    def current_format(self) -> str:
        if self._format_provider is None:
            return ""
        try:
            return self._format_provider() or ""
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Baseline tab could not read the current format: {exc}")
            return ""

    # ------------------------------------------------------------------ events ------------------------------------------------------------------
    def on_shown(self) -> None:
        """Tab became visible, or the selection under it changed.

        Nothing here waits for a click: if the archetype on screen has no
        baseline yet, computing it starts now, on the background worker.
        """
        self.refresh_target()
        if self._pending:
            return
        archetype = self.current_archetype()
        if not archetype or not self.current_format():
            return
        target = (str(archetype.get("name") or ""), self.current_format())
        if self._baseline is not None and target == self._computed_for:
            return
        self.compute()

    def refresh_target(self) -> None:
        """Update the "baseline for …" line and load any stored baseline."""
        archetype = self.current_archetype()
        mtg_format = self.current_format()
        name = str(archetype.get("name")) if archetype else ""

        if not name:
            self.target_label.SetLabel(self._t("baseline.target.none"))
            return

        self.target_label.SetLabel(
            self._t("baseline.target", archetype=name, format=mtg_format or "?")
        )

        if self._baseline is None and mtg_format:
            stored = self.baseline_service.stored(name, mtg_format)
            if stored is not None:
                self._baseline = stored
                self._computed_for = (name, mtg_format)
                self.render()

    # ------------------------------------------------------------------ compute ------------------------------------------------------------------
    def compute(self) -> None:
        """Kick off a baseline computation for the selected archetype."""
        archetype = self.current_archetype()
        mtg_format = self.current_format()
        if not archetype or not mtg_format:
            self.status_label.SetLabel(self._t("baseline.status.no_archetype"))
            return

        self._run_token += 1
        token = self._run_token
        self._pending = True
        self.status_label.SetLabel(self._t("baseline.status.computing"))

        self._computed_for = (str(archetype.get("name") or ""), mtg_format)
        service = self.baseline_service

        def work() -> ArchetypeBaseline | None:
            return service.compute(archetype, mtg_format=mtg_format)

        def done(result: ArchetypeBaseline | None) -> None:
            if token != self._run_token:
                return  # a newer run has started; this answer is stale
            self._pending = False
            self._baseline = result
            if result is None:
                self.tree.DeleteAllItems()
                self.status_label.SetLabel(self._t("baseline.status.pool_too_small"))
                return
            self.render()
            self._status("app.status.baseline_computed", pool=result.pool_size)

        def failed(exc: Exception) -> None:
            if token != self._run_token:
                return
            logger.warning(f"Baseline computation failed: {exc}")
            self._pending = False
            self._baseline = None
            self.tree.DeleteAllItems()
            self.status_label.SetLabel(self._t("baseline.status.failed"))

        if self.worker is None:
            # No worker (tests, or a standalone panel): run inline.
            try:
                done(work())
            except Exception as exc:  # noqa: BLE001
                failed(exc)
            return

        self.worker.submit(work, on_success=done, on_error=failed)

    # ------------------------------------------------------------------ render ------------------------------------------------------------------
    def render(self) -> None:
        """Draw the staple / partial-staple / flex breakdown."""
        self.tree.DeleteAllItems()
        baseline = self._baseline
        if baseline is None:
            self.status_label.SetLabel(
                self._t("baseline.status.computing")
                if self._pending
                else self._t("baseline.status.none")
            )
            return

        root = self.tree.AddRoot("baseline")

        staples = baseline.by_role(CardRole.STAPLE)
        partials = baseline.by_role(CardRole.PARTIAL_STAPLE)

        staple_node = self.tree.AppendItem(
            root, self._t("baseline.group.staples", count=len(staples))
        )
        for card in staples:
            self.tree.AppendItem(staple_node, self._card_label(card))
        self.tree.Expand(staple_node)

        partial_node = self.tree.AppendItem(
            root, self._t("baseline.group.partial", count=len(partials))
        )
        for card in partials:
            self.tree.AppendItem(partial_node, self._partial_label(card))
        self.tree.Expand(partial_node)

        flex_node = self.tree.AppendItem(
            root,
            self._t("baseline.group.flex", count=len(baseline.flex_candidates)),
        )
        for candidate in baseline.flex_candidates:
            self.tree.AppendItem(flex_node, self._candidate_label(candidate))
        self.tree.Expand(flex_node)

        # Rejecting a deck changes every number above it, so the rejections are
        # shown rather than logged. Collapsed by default: it is evidence for the
        # answer, not part of it.
        membership = baseline.membership
        if membership.filtered_anything:
            excluded_node = self.tree.AppendItem(
                root,
                self._t(
                    "baseline.group.excluded",
                    count=membership.excluded_count,
                    threshold=_render_percent(membership.threshold),
                ),
            )
            for deck in membership.excluded:
                self.tree.AppendItem(excluded_node, self._excluded_label(deck))

        # Expanding the flex group (often 40+ rows) scrolls it into view, which
        # pushes the staples off the top -- so the tab would open on its least
        # important group every time. Put the first group back on screen.
        self.tree.EnsureVisible(staple_node)
        self.tree.ScrollTo(staple_node)

        fixed = _render_number(baseline.main.fixed + baseline.sideboard.fixed)
        flex = _render_number(baseline.flex_slots)
        if membership.filtered_anything:
            self.status_label.SetLabel(
                self._t(
                    "baseline.status.summary_filtered",
                    pool=baseline.pool_size,
                    examined=membership.examined,
                    excluded=membership.excluded_count,
                    flex=flex,
                    fixed=fixed,
                )
            )
        else:
            self.status_label.SetLabel(
                self._t(
                    "baseline.status.summary",
                    pool=baseline.pool_size,
                    flex=flex,
                    fixed=fixed,
                )
            )

    def _card_label(self, card: Any) -> str:
        return self._t(
            "baseline.card.staple",
            count=_render_number(card.fixed_count),
            name=card.name,
            zone=self._zone_name(card.is_sideboard),
        )

    def _partial_label(self, card: Any) -> str:
        return self._t(
            "baseline.card.partial",
            floor=_render_number(card.fixed_count),
            max=_render_number(card.frequency.max_count),
            name=card.name,
            zone=self._zone_name(card.is_sideboard),
        )

    def _candidate_label(self, candidate: Any) -> str:
        key = "baseline.card.flex_above" if candidate.above_floor else "baseline.card.flex"
        return self._t(
            key,
            name=candidate.name,
            rate=f"{candidate.play_rate * 100:.0f}%",
            average=f"{candidate.average_count:.1f}",
            zone=self._zone_name(candidate.is_sideboard),
        )

    def _excluded_label(self, deck: Any) -> str:
        return self._t(
            "baseline.card.excluded",
            source=deck.source,
            similarity=_render_percent(deck.similarity),
        )

    def _zone_name(self, is_sideboard: bool) -> str:
        return self._t("baseline.zone.sideboard" if is_sideboard else "baseline.zone.main")

    def _status(self, key: str, **kwargs: object) -> None:
        if self._on_status_update is not None:
            self._on_status_update(key, **kwargs)


def _render_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _render_percent(value: float) -> str:
    return f"{value * 100:.0f}%"
