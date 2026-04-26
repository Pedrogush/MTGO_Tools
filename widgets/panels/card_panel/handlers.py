"""Public API and UI populators for :class:`CardPanel`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from services.format_card_pool_service import (
    FormatCardPoolService,
    get_format_card_pool_service,
)
from widgets.panels.card_panel.html_renderer import build_card_html

if TYPE_CHECKING:
    from widgets.panels.card_panel.protocol import CardPanelProto

    _Base = CardPanelProto
else:
    _Base = object


class CardPanelHandlersMixin(_Base):
    """Public API: ``update_card``, ``update_format``, ``update_archetype``,
    ``update_radar``, and ``clear``.
    """

    def update_card(
        self,
        meta: Any,
        printing: dict[str, Any] | None = None,
    ) -> None:
        # ``meta`` may be a dict or a ``CardEntry`` (msgspec.Struct) — both
        # expose ``.get(key)`` / ``__getitem__``, which is all the renderer
        # uses, so store the reference as-is.
        self._current_meta = meta
        self._current_printing = dict(printing) if printing else None
        self._refresh_oracle_tab()
        self._refresh_stats_tab()

    def update_printing(self, printing: dict[str, Any] | None) -> None:
        self._current_printing = dict(printing) if printing else None
        self._refresh_oracle_tab()

    def update_format(self, format_name: str | None) -> None:
        format_name = (format_name or "").strip() or None
        if format_name == self._current_format:
            return
        self._current_format = format_name
        self._refresh_stats_tab()

    def update_archetype(
        self,
        archetype: dict[str, Any] | None,
        radar_data: Any | None = None,
    ) -> None:
        self._current_archetype = dict(archetype) if archetype else None
        self._current_radar = radar_data
        self._refresh_stats_tab()

    def update_radar(self, radar_data: Any | None) -> None:
        self._current_radar = radar_data
        self._refresh_stats_tab()

    def clear(self) -> None:
        self._current_meta = None
        self._current_printing = None
        self._refresh_oracle_tab()
        self._refresh_stats_tab()

    # ============= Private =============

    def _refresh_oracle_tab(self) -> None:
        empty_text = self._t("card_panel.empty")
        try:
            html = build_card_html(
                self._current_meta,
                self._current_printing,
                self._png_resolver,
                empty_text=empty_text,
            )
        except Exception as exc:
            logger.exception(f"Failed to build card HTML: {exc}")
            html = f'<html><body bgcolor="#22272E" text="#E6EDF3"><p>{empty_text}</p></body></html>'
        self.oracle_html.SetPage(html)

    def _png_resolver(self, token: str) -> Any:
        try:
            return self.mana_icons.png_path_for_symbol(token, height=14)
        except Exception:
            logger.debug(f"Could not resolve PNG for mana symbol '{token}'")
            return None

    def _refresh_stats_tab(self) -> None:
        meta = self._current_meta
        if not meta:
            self.stats_card_label.SetLabel(self._t("card_panel.stats.no_card"))
            self._set_format_stats(None, None)
            self._set_archetype_stats(None)
            return

        card_name = str(meta.get("name") or "")
        self.stats_card_label.SetLabel(card_name)
        self._set_format_stats(self._current_format, card_name)
        self._set_archetype_stats(card_name)

    def _set_format_stats(self, format_name: str | None, card_name: str | None) -> None:
        if not format_name:
            self.stats_format_header.SetLabel(self._t("card_panel.stats.no_format"))
            self.stats_format_total.SetLabel("")
            self.stats_format_avg.SetLabel("")
            return

        self.stats_format_header.SetLabel(
            self._t("card_panel.stats.format_header", format=format_name)
        )

        if not card_name:
            self.stats_format_total.SetLabel("")
            self.stats_format_avg.SetLabel("")
            return

        try:
            service: FormatCardPoolService = get_format_card_pool_service()
            total = service.get_card_total(format_name, card_name)
            summary = service.get_summary(format_name)
        except Exception as exc:
            logger.warning(f"Failed to fetch format stats: {exc}")
            total = 0
            summary = None

        self.stats_format_total.SetLabel(
            self._t("card_panel.stats.total_copies", value=self._format_number(total))
        )
        if summary and summary.total_decks_analyzed > 0:
            avg = total / summary.total_decks_analyzed
            self.stats_format_avg.SetLabel(
                self._t("card_panel.stats.avg_per_deck", value=self._format_average(avg))
            )
        else:
            self.stats_format_avg.SetLabel(self._t("card_panel.stats.no_data"))

    def _set_archetype_stats(self, card_name: str | None) -> None:
        archetype_name = self._archetype_name()
        if not archetype_name:
            self.stats_archetype_header.SetLabel(self._t("card_panel.stats.no_archetype"))
            self._clear_main_side_labels()
            return

        self.stats_archetype_header.SetLabel(
            self._t("card_panel.stats.archetype_header", archetype=archetype_name)
        )

        if not card_name:
            self._clear_main_side_labels()
            return

        if self._current_radar is None:
            self._clear_main_side_labels(message=self._t("card_panel.stats.archetype_loading"))
            return

        main_freq = self._lookup_main_freq(card_name)
        side_freq = self._lookup_side_freq(card_name)
        self._populate_freq_labels(
            main_freq,
            self.stats_main_total,
            self.stats_main_avg,
            self.stats_main_karsten,
            self.stats_main_inclusion,
        )
        self._populate_freq_labels(
            side_freq,
            self.stats_side_total,
            self.stats_side_avg,
            self.stats_side_karsten,
            self.stats_side_inclusion,
        )

    def _populate_freq_labels(self, freq, total_w, avg_w, karsten_w, inc_w) -> None:
        if freq is None:
            total_w.SetLabel(self._t("card_panel.stats.total_copies", value="0"))
            avg_w.SetLabel(self._t("card_panel.stats.avg_per_deck", value="0.00"))
            karsten_w.SetLabel(self._t("card_panel.stats.avg_when_present", value="—"))
            inc_w.SetLabel(self._t("card_panel.stats.inclusion_rate", value="0.00"))
            return
        total_w.SetLabel(
            self._t("card_panel.stats.total_copies", value=self._format_number(freq.total_copies))
        )
        avg_w.SetLabel(
            self._t(
                "card_panel.stats.avg_per_deck",
                value=self._format_average(freq.expected_copies),
            )
        )
        karsten_w.SetLabel(
            self._t(
                "card_panel.stats.avg_when_present",
                value=self._format_average(freq.avg_copies),
            )
        )
        inc_w.SetLabel(
            self._t(
                "card_panel.stats.inclusion_rate",
                value=self._format_average(freq.inclusion_rate),
            )
        )

    def _clear_main_side_labels(self, message: str = "") -> None:
        for w in (
            self.stats_main_total,
            self.stats_main_avg,
            self.stats_main_karsten,
            self.stats_main_inclusion,
            self.stats_side_total,
            self.stats_side_avg,
            self.stats_side_karsten,
            self.stats_side_inclusion,
        ):
            w.SetLabel(message)
