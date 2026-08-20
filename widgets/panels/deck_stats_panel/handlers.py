"""Public state setters and UI populators for the deck stats panel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.perf import perf_phase
from widgets.panels.deck_stats_panel.stats_chart_html import (
    _EMPTY_HTML,
    _build_html,
    build_sections,
)

if TYPE_CHECKING:
    from repositories.card_repository import CardDataManager
    from widgets.panels.deck_stats_panel.protocol import DeckStatsPanelProto

    _Base = DeckStatsPanelProto
else:
    _Base = object


class DeckStatsPanelHandlersMixin(_Base):
    """Public API methods that read state and drive the embedded WebView for :class:`DeckStatsPanel`."""

    def update_stats(self, deck_text: str, zone_cards: dict[str, list[dict[str, Any]]]) -> None:
        self.zone_cards = zone_cards

        if not deck_text.strip():
            self.summary_label.SetLabel(self._t("tabs.stats.no_deck"))
            self.render_empty()
            return

        with perf_phase("stats: analyze + metadata item helpers"):
            stats = self.deck_service.analyze_deck(deck_text)
            land_count, mdfc_count = self._count_lands()
            total_land_count = land_count + mdfc_count

            land_label = f"{land_count} land{'s' if land_count != 1 else ''}"
            if mdfc_count:
                land_label += f" + {mdfc_count} MDFC{'s' if mdfc_count != 1 else ''}"
            summary = (
                f"Mainboard: {stats['mainboard_count']} cards ({stats['unique_mainboard']} unique)"
                f"  |  Sideboard: {stats['sideboard_count']} cards ({stats['unique_sideboard']} unique)"
                f"  |  Lands: {land_label}"
            )

            self.summary_label.SetLabel(summary)

            curve_items = self._curve_items()
            color_items = self._color_items()
            type_items = self._type_items()
            hand_items = self._hand_items(stats["mainboard_count"], total_land_count)

        # Only the backend in use is built. The two renderings walk the same
        # tuples, so building both would double the work on every deck load for
        # a view nobody is looking at.
        titles = self._chart_titles()
        if self.uses_webview:
            with perf_phase("stats: build HTML"):
                html = _build_html(
                    summary, curve_items, color_items, type_items, hand_items, titles
                )
            with perf_phase("stats: WebView SetPage"):
                self._set_webview_page(html)
        elif self._painted is not None:
            with perf_phase("stats: build sections"):
                sections = build_sections(curve_items, color_items, type_items, hand_items, titles)
            self._painted.set_sections("", summary, sections, self._t("tabs.stats.no_data"))

    def _chart_titles(self) -> tuple[str, str, str, str]:
        return (
            self._t("tabs.stats.curve"),
            self._t("tabs.stats.colors"),
            self._t("tabs.stats.types"),
            self._t("tabs.stats.hand"),
        )

    def set_card_manager(self, card_manager: CardDataManager) -> None:
        self.card_manager = card_manager

    def clear(self) -> None:
        self.summary_label.SetLabel(self._t("tabs.stats.no_deck"))
        self.render_empty()

    def render_empty(self) -> None:
        """Show the no-deck state on whichever backend this panel got."""
        if self.uses_webview:
            self._set_webview_page(_EMPTY_HTML)
        elif self._painted is not None:
            self._painted.set_sections("", "", [], self._t("tabs.stats.no_deck"))

    def _set_webview_page(self, html: str) -> None:
        """Stash the page and push it if there is a WebView to push it to.

        It is stashed even without one so a test can read back what *would* have
        rendered, and so a WebView created later starts on the current page.
        """
        self._webview_html = html
        if self._webview is not None:
            self._webview.SetPage(html, "")
