"""State helpers, i18n, and display formatting for the timer alert widget."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.i18n import translate

if TYPE_CHECKING:
    from widgets.frames.timer_alert.frame import ThresholdPanel


class TimerAlertPropertiesMixin:
    """Translation, status, threshold parsing, and display-formatting helpers.

    Kept as a mixin — state is initialized by :class:`TimerAlertFrame.__init__`.
    """

    _locale: str | None
    status_text: wx.TextCtrl
    threshold_panels: list[ThresholdPanel]
    challenge_text: wx.StaticText | None

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _set_status(self, key: str, **kwargs: object) -> None:
        self.status_text.ChangeValue(self._t(key, **kwargs))

    def _parse_thresholds(self) -> list[int]:
        thresholds: list[int] = []
        for panel in self.threshold_panels:
            seconds = panel.get_seconds()
            if seconds is not None and seconds > 0:
                thresholds.append(seconds)
            elif panel.time_input.GetValue().strip():
                logger.warning(f"Invalid threshold format: {panel.time_input.GetValue()}")
        thresholds.sort(reverse=True)
        return thresholds

    def _format_seconds(self, value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "—"
        total = max(0, int(round(value)))
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _update_challenge_display(self, snapshot: dict[str, Any]) -> None:
        if not self.challenge_text:
            return
        timers = snapshot.get("challengeTimers") or []
        if not timers:
            self.challenge_text.SetLabel(self._t("timer.no_challenge"))
            self.challenge_text.Wrap(self._challenge_wrap_width())
            return
        lines: list[str] = []
        for timer in timers:
            desc = timer.get("description") or timer.get("eventId") or "Challenge"
            state = timer.get("state") or "Unknown"
            remaining = timer.get("remainingSeconds")
            remaining_display = self._format_seconds(remaining)
            fmt = timer.get("format")
            line = desc
            if fmt and fmt.lower() != "no format found":
                line += f" • {fmt}"
            line += f" ({state}) — {remaining_display}"
            lines.append(line)
        self.challenge_text.SetLabel("\n".join(lines))
        self.challenge_text.Wrap(self._challenge_wrap_width())

    def _challenge_wrap_width(self) -> int:
        if not self.challenge_text:
            return 340
        parent = self.challenge_text.GetParent()
        width = parent.GetClientSize().width if parent else 0
        return max(240, width - 24)
