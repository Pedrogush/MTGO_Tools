"""State accessors, pure data helpers, and HTML builders for the metagame analysis viewer."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from html import escape
from typing import Any

from utils.constants import DARK_ACCENT, DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.i18n import translate


class MetagameAnalysisPropertiesMixin:
    """Translations, aggregation, and HTML snippets for :class:`MetagameAnalysisFrame`.

    Kept as a mixin (no ``__init__``) so :class:`MetagameAnalysisFrame` remains
    the single source of truth for instance-state initialization.
    """

    _locale: str | None
    current_format: str
    stats_data: dict[str, Any]

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _aggregate_for_days(self, days: int, base_offset: int = 0) -> dict[str, int]:
        format_stats = self.stats_data.get(self.current_format, {})
        today = datetime.now().date()

        archetype_counts: Counter[str] = Counter()
        for archetype_name, archetype_data in format_stats.items():
            if archetype_name == "timestamp":
                continue

            results = archetype_data.get("results", {})
            for day_offset in range(base_offset, base_offset + days):
                date_str = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                count = results.get(date_str, 0)
                archetype_counts[archetype_name] += count

        return dict(archetype_counts)

    def _calculate_percentages(self, counts: dict[str, int]) -> dict[str, float]:
        total = sum(counts.values())
        if total == 0:
            return {}
        return {archetype: (count / total) * 100 for archetype, count in counts.items()}

    def _rgb_to_hex(self, rgb: tuple[int, int, int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _build_change_card(
        self, archetype: str, change: float, *, current_val: float, previous_val: float
    ) -> str:
        if change >= 2.0:
            arrow = "\u25b2\u25b2"
            direction_class = "up"
        elif change > 0:
            arrow = "\u25b2"
            direction_class = "up"
        elif change <= -2.0:
            arrow = "\u25bc\u25bc"
            direction_class = "down"
        else:
            arrow = "\u25bc"
            direction_class = "down"

        arrow_color = "#43d17b" if direction_class == "up" else "#ff6464"
        dark_panel = self._rgb_to_hex(DARK_PANEL)
        dark_accent = self._rgb_to_hex(DARK_ACCENT)
        light_text = self._rgb_to_hex(LIGHT_TEXT)
        subdued_text = self._rgb_to_hex(SUBDUED_TEXT)

        return f"""
<table cellspacing='0' cellpadding='0' width='100%'>
  <tr>
    <td align='center'>
      <table cellspacing='1' cellpadding='0' bgcolor='{dark_accent}' width='96%'>
        <tr>
          <td bgcolor='{dark_panel}'>
            <table cellspacing='0' cellpadding='4' width='100%'>
              <tr>
                <td><font color='{arrow_color}'><b>{arrow}</b></font></td>
                <td><font color='{light_text}'><b>{escape(archetype)}</b></font></td>
                <td align='right'><font color='{arrow_color}'><b>{change:+.1f}%</b></font></td>
              </tr>
              <tr>
                <td colspan='3'>
                  <font color='{subdued_text}' size='2'>
                    {escape(self._t('metagame.changes.now'))} {current_val:.1f}% | {escape(self._t('metagame.changes.previous'))} {previous_val:.1f}%
                  </font>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
"""

    def _build_changes_html(self, title: str, cards: list[str]) -> str:
        cards_html = "<br/>".join(cards)
        dark_alt = self._rgb_to_hex(DARK_ALT)
        subdued_text = self._rgb_to_hex(SUBDUED_TEXT)
        light_text = self._rgb_to_hex(LIGHT_TEXT)
        return f"""
<html>
<body bgcolor='{dark_alt}'>
<font face='Segoe UI, Arial, sans-serif' color='{subdued_text}'><b>{escape(title)}</b></font>
<br/><br/>
<font face='Segoe UI, Arial, sans-serif' color='{light_text}'>
{cards_html}
</font>
</body>
</html>
"""
