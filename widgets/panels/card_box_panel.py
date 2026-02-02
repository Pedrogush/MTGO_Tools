from collections.abc import Callable
from typing import Any

import wx

from utils.card_images import get_card_image
from utils.constants import (
    DARK_ACCENT,
    DARK_ALT,
    DECK_CARD_BADGE_PADDING,
    DECK_CARD_BUTTON_MARGIN,
    DECK_CARD_CORNER_RADIUS,
    DECK_CARD_HEIGHT,
    DECK_CARD_WIDTH,
    LIGHT_TEXT,
)
from utils.mana_icon_factory import ManaIconFactory


class CardBoxPanel(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        card: dict[str, Any],
        icon_factory: ManaIconFactory,
        get_metadata: Callable[[str], dict[str, Any] | None],
        owned_status: Callable[[str, int], tuple[str, tuple[int, int, int]]],
        on_delta: Callable[[str, str, int], None],
        on_remove: Callable[[str, str], None],
        on_select: Callable[[str, dict[str, Any], "CardBoxPanel"], None],
        on_hover: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.zone = zone
        self.card = card
        self._icon_factory = icon_factory
        self._get_metadata = get_metadata
        self._owned_status = owned_status
        self._on_delta = on_delta
        self._on_remove = on_remove
        self._on_select = on_select
        self._on_hover = on_hover
        self._active = False
        self._mana_cost = ""
        self._card_color = ManaIconFactory.FALLBACK_COLORS["c"]
        self._mana_cost_bitmap: wx.Bitmap | None = None
        self._template_bitmap: wx.Bitmap | None = None
        self._card_bitmap: wx.Bitmap | None = None
        self._image_available = False
        self._image_attempted = False

        self.SetBackgroundColour(DARK_ALT)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((DECK_CARD_WIDTH, DECK_CARD_HEIGHT))
        self.SetMaxSize((DECK_CARD_WIDTH, DECK_CARD_HEIGHT))
        self.Bind(wx.EVT_PAINT, self._on_paint)

        layout = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(layout)

        base_font = wx.Font(11, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)

        # Quantity label
        badge_row = wx.BoxSizer(wx.HORIZONTAL)
        self.qty_label = wx.StaticText(self, label=str(card["qty"]))
        self.qty_label.SetForegroundColour(LIGHT_TEXT)
        self.qty_label.SetFont(base_font)
        self.qty_label.SetBackgroundColour(DARK_ALT)
        badge_row.Add(self.qty_label, 0, wx.ALL, DECK_CARD_BADGE_PADDING)
        badge_row.AddStretchSpacer(1)
        layout.Add(badge_row, 0, wx.EXPAND)

        layout.AddStretchSpacer(1)

        # Button panel
        self.button_panel = wx.Panel(self)
        self.button_panel.SetBackgroundColour(DARK_ALT)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.button_panel.SetSizer(btn_sizer)
        add_btn = wx.Button(self.button_panel, label="+")
        self._style_action_button(add_btn)
        add_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_delta(zone, card["name"], 1))
        btn_sizer.Add(add_btn, 0)
        sub_btn = wx.Button(self.button_panel, label="−")
        self._style_action_button(sub_btn)
        sub_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_delta(zone, card["name"], -1))
        btn_sizer.Add(sub_btn, 0, wx.LEFT, 2)
        rem_btn = wx.Button(self.button_panel, label="×")
        self._style_action_button(rem_btn)
        rem_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_remove(zone, card["name"]))
        btn_sizer.Add(rem_btn, 0, wx.LEFT, 2)
        buttons_row = wx.BoxSizer(wx.HORIZONTAL)
        buttons_row.Add(self.button_panel, 0, wx.LEFT | wx.BOTTOM, DECK_CARD_BUTTON_MARGIN)
        buttons_row.AddStretchSpacer(1)
        layout.Add(buttons_row, 0, wx.EXPAND)
        self.button_panel.Hide()

        self._update_card_state(card)

        # Bind click events to all widgets so clicks anywhere on the card work
        self._bind_click_targets([self, self.qty_label])
        self._bind_hover_targets([self, self.qty_label, self.button_panel])

    def update_quantity(
        self, qty: int | float, owned_text: str, owned_colour: tuple[int, int, int]
    ) -> None:
        self.qty_label.SetLabel(str(qty))
        self.qty_label.SetForegroundColour(wx.Colour(*owned_colour))
        self.Layout()
        self.Refresh()

    def refresh_image(self) -> None:
        self._image_attempted = False
        self._image_available = False
        self._card_bitmap = None
        self.Refresh()

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self.button_panel.Show(active)
        self.button_panel.Enable(active)
        self.button_panel.SetBackgroundColour(DARK_ACCENT if active else DARK_ALT)
        self.qty_label.SetBackgroundColour(DARK_ACCENT if active else DARK_ALT)
        self.SetBackgroundColour(DARK_ACCENT if active else DARK_ALT)
        self.Refresh()
        self.Layout()

    def _bind_click_targets(self, targets: list[wx.Window]) -> None:
        for target in targets:
            target.Bind(wx.EVT_LEFT_DOWN, self._handle_click)
            for child in target.GetChildren():
                child.Bind(wx.EVT_LEFT_DOWN, self._handle_click)

    def _bind_hover_targets(self, targets: list[wx.Window]) -> None:
        if self._on_hover is None:
            return
        for target in targets:
            target.Bind(wx.EVT_ENTER_WINDOW, self._handle_hover)
            for child in target.GetChildren():
                child.Bind(wx.EVT_ENTER_WINDOW, self._handle_hover)

    def _handle_click(self, _event: wx.MouseEvent) -> None:
        self._on_select(self.zone, self.card, self)

    def _handle_hover(self, _event: wx.MouseEvent) -> None:
        if self._on_hover:
            self._on_hover(self.zone, self.card)

    def _style_action_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_ACCENT)
        button.SetForegroundColour(wx.Colour(12, 14, 18))
        button.SetWindowStyleFlag(wx.BORDER_NONE)
        button.SetMinSize((28, 28))
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _update_card_state(self, card: dict[str, Any]) -> None:
        meta = self._get_metadata(card["name"]) or {}
        self._mana_cost = meta.get("mana_cost", "") or ""
        self._mana_cost_bitmap = None
        self._card_color = self._resolve_card_color(meta)
        self._template_bitmap = self._build_template_bitmap()
        self._image_attempted = False
        self._image_available = False
        self._card_bitmap = None

        qty_value = card["qty"]
        qty_for_check = int(qty_value) if isinstance(qty_value, float) else qty_value
        _, owned_colour_rgb = self._owned_status(card["name"], qty_for_check)
        self.qty_label.SetForegroundColour(wx.Colour(*owned_colour_rgb))

    def _resolve_card_color(self, meta: dict[str, Any]) -> tuple[int, int, int]:
        identity = meta.get("color_identity") or meta.get("colors") or []
        normalized = [str(c).lower() for c in identity if c]
        if not normalized:
            return ManaIconFactory.FALLBACK_COLORS["c"]
        if len(normalized) == 1:
            return ManaIconFactory.FALLBACK_COLORS.get(
                normalized[0], ManaIconFactory.FALLBACK_COLORS["c"]
            )
        return ManaIconFactory.FALLBACK_COLORS["multicolor"]

    def _get_mana_cost_bitmap(self) -> wx.Bitmap | None:
        if self._mana_cost_bitmap is None:
            self._mana_cost_bitmap = self._icon_factory.bitmap_for_cost(self._mana_cost)
        return self._mana_cost_bitmap

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        rect = self.GetClientRect()
        dc.SetBackground(wx.Brush(wx.Colour(*self._card_color)))
        dc.Clear()

        if not self._image_attempted:
            self._refresh_card_bitmap()

        if self._image_available and self._card_bitmap:
            dc.DrawBitmap(self._card_bitmap, rect.x, rect.y, True)
        elif self._template_bitmap:
            dc.DrawBitmap(self._template_bitmap, rect.x, rect.y, True)

        if self._active:
            dc.SetPen(wx.Pen(wx.Colour(*DARK_ACCENT), 3))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)

    def _refresh_card_bitmap(self) -> None:
        self._image_attempted = True
        image_path = get_card_image(self.card["name"], "normal")
        if image_path and image_path.exists():
            try:
                img = wx.Image(str(image_path), wx.BITMAP_TYPE_ANY)
            except Exception:
                self._image_available = False
                self._card_bitmap = None
                return
            if img.IsOk():
                scaled = self._scale_image_to_card(img)
                self._card_bitmap = self._render_bitmap_with_image(scaled)
                self._image_available = True
                return
        self._image_available = False
        self._card_bitmap = None

    def _scale_image_to_card(self, image: wx.Image) -> wx.Image:
        img_width = image.GetWidth()
        img_height = image.GetHeight()
        if img_width <= 0 or img_height <= 0:
            return image
        scale = min(DECK_CARD_WIDTH / img_width, DECK_CARD_HEIGHT / img_height)
        new_width = max(1, int(img_width * scale))
        new_height = max(1, int(img_height * scale))
        return image.Scale(new_width, new_height, wx.IMAGE_QUALITY_HIGH)

    def _render_bitmap_with_image(self, image: wx.Image) -> wx.Bitmap:
        bitmap = wx.Bitmap(DECK_CARD_WIDTH, DECK_CARD_HEIGHT)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0)))
        dc.Clear()
        x = (DECK_CARD_WIDTH - image.GetWidth()) // 2
        y = (DECK_CARD_HEIGHT - image.GetHeight()) // 2
        dc.DrawBitmap(wx.Bitmap(image), x, y, True)
        dc.SelectObject(wx.NullBitmap)
        return bitmap

    def _build_template_bitmap(self) -> wx.Bitmap:
        bitmap = wx.Bitmap(DECK_CARD_WIDTH, DECK_CARD_HEIGHT)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.Colour(*self._card_color)))
        dc.Clear()
        rect = wx.Rect(0, 0, DECK_CARD_WIDTH, DECK_CARD_HEIGHT)
        dc.SetPen(wx.Pen(wx.Colour(0, 0, 0, 120), 2))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRoundedRectangle(rect, DECK_CARD_CORNER_RADIUS)
        self._draw_placeholder_details(dc, rect)
        dc.SelectObject(wx.NullBitmap)
        return bitmap

    def _draw_placeholder_details(self, dc: wx.DC, rect: wx.Rect) -> None:
        cost_bitmap = self._get_mana_cost_bitmap()
        if cost_bitmap:
            cost_x = rect.x + rect.width - cost_bitmap.GetWidth() - DECK_CARD_BADGE_PADDING
            cost_y = rect.y + DECK_CARD_BADGE_PADDING
            dc.DrawBitmap(cost_bitmap, cost_x, cost_y, True)
        elif self._mana_cost:
            dc.SetTextForeground(LIGHT_TEXT)
            dc.DrawText(
                self._mana_cost,
                rect.x + rect.width - (DECK_CARD_BADGE_PADDING * 6),
                rect.y + DECK_CARD_BADGE_PADDING,
            )

        dc.SetTextForeground(wx.Colour(0, 0, 0))
        name_font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        dc.SetFont(name_font)
        name_lines = self._wrap_text(
            dc, self.card["name"], rect.width - (DECK_CARD_BADGE_PADDING * 2)
        )
        line_height = dc.GetTextExtent("Ag")[1]
        total_height = line_height * len(name_lines)
        start_y = rect.y + (rect.height - total_height) // 2
        for line in name_lines:
            text_width = dc.GetTextExtent(line)[0]
            text_x = rect.x + (rect.width - text_width) // 2
            dc.DrawText(line, text_x, start_y)
            start_y += line_height

    def _wrap_text(self, dc: wx.DC, text: str, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return [text]
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if dc.GetTextExtent(test)[0] <= max_width or not current:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines
