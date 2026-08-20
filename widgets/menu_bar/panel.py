"""The app's menu bar — an app-drawn strip of titles over native ``wx.Menu`` popups.

Why this is not a ``wx.MenuBar``
-------------------------------
A native menu bar was built and measured first (phase 3b). Under
:func:`widgets.native_dark.enable_app_dark_mode` the **popups** come out dark —
that is what ``FlushMenuThemes()`` buys — but the **bar** does not: it renders at
``#FFFFFF`` with a ``#F0F0F0`` rule under it, in the real app as well as in an
isolated probe. Windows draws the bar in the non-client area from
``COLOR_MENUBAR``; ``SetMenuInfo(MIM_BACKGROUND)`` does not reach it (it returns
0), and the only known fix is to subclass the frame's ``WNDPROC`` and own-draw
the bar through the undocumented ``WM_UAH*`` messages — every window message for
the busiest window in the app round-tripping through a ctypes callback. That was
judged too much risk for a styling phase, so the bar is drawn by the app and only
the popups are native. See :mod:`widgets.menu_bar.spec` for why the menus are
data rather than widgets.
"""

from __future__ import annotations

from collections.abc import Sequence

import wx

from utils.constants import SPACE_XS
from widgets.menu_bar.spec import MenuEntry, MenuSpec
from widgets.stylize import stylize_button

#: Surface the strip sits on. It spans the window above every panel, so it is on
#: the window's own base surface rather than a panel's.
_SURFACE = "base"


class AppMenuBar(wx.Panel):
    """A full-width strip of menu titles at the top of the main window."""

    def __init__(self, parent: wx.Window, menus: Sequence[MenuSpec]):
        super().__init__(parent)
        self._menus: dict[str, MenuSpec] = {}
        self._order: list[str] = []
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(row)
        self._build(menus)

    def _build(self, menus: Sequence[MenuSpec]) -> None:
        row = self.GetSizer()
        for spec in menus:
            # BU_EXACTFIT: a wx.Button's best size floors at 75px wide whatever
            # the label (phase 3), and four 75px chips would read as a button
            # row rather than a menu bar.
            button = wx.Button(self, label=spec.title, style=wx.BU_EXACTFIT)
            # kind="flat" until pointed at, then "ghost" -- a menu title is not a
            # chip sitting on the window, it is a word that lights up.
            stylize_button(button, kind="flat", surface=_SURFACE)
            button.Bind(wx.EVT_BUTTON, lambda _evt, t=spec.title: self.open_menu(t))
            button.Bind(wx.EVT_ENTER_WINDOW, lambda _evt, b=button: self._highlight(b, True))
            button.Bind(wx.EVT_LEAVE_WINDOW, lambda _evt, b=button: self._highlight(b, False))
            row.Add(button, 0, wx.RIGHT, SPACE_XS)
            self._menus[spec.title] = spec
            self._order.append(spec.title)
        row.AddStretchSpacer(1)

    # ============= Public API =============

    def titles(self) -> list[str]:
        return list(self._order)

    def set_menus(self, menus: Sequence[MenuSpec]) -> None:
        """Rebuild the bar — used when the language changes.

        The *entries* re-translate for free because they are rebuilt on every
        open, but the titles are button labels, fixed at construction. Without
        this the bar would read "File / Tools / Settings / Help" over menus whose
        contents had switched to Portuguese.
        """
        sizer = self.GetSizer()
        sizer.Clear(delete_windows=True)
        self._menus.clear()
        self._order.clear()
        self._build(menus)
        self.Layout()

    def entries(self, title: str) -> Sequence[MenuEntry]:
        """The *current* entries of one menu. Rebuilt on every call by design."""
        spec = self._menus.get(title)
        return spec.build() if spec else ()

    def open_menu(self, title: str) -> bool:
        """Pop the named menu up under its title button."""
        spec = self._menus.get(title)
        if spec is None:
            return False
        button = self._button_for(title)
        menu = build_menu(spec.build())
        anchor = button or self
        if button is not None:
            self._highlight(button, True)
        # PopupMenu runs a nested modal loop: nothing below this line executes
        # until the menu closes, including anything the automation server wants
        # to do. That is why the harness drives the *spec*, not the widget.
        anchor.PopupMenu(menu, wx.Point(0, anchor.GetSize().GetHeight()))
        menu.Destroy()
        # Re-resolve rather than re-using the `button` we opened with. The chosen
        # item's handler runs *inside* the loop above -- measured, see
        # docs/WXMSW_BEHAVIOUR.md -- and `File > Preferences... > Language` calls
        # set_menus from in there, which destroys every title button including
        # this one. Reaching for the stale reference is how #962 crashed with
        # "wrapped C/C++ object of type Button has been deleted".
        #
        # After a rebuild this correctly finds nothing: the titles are now
        # translated, so no child matches, and there is genuinely nothing to
        # un-highlight because _build stylizes the new buttons "flat" already.
        # The asymmetry is the point -- the highlight belongs to a button, not to
        # a title, and when that button is gone so is its highlight.
        #
        # `anchor` is deliberately left alone: it is PopupMenu's receiver, and
        # wxMSW's DoPopupMenu touches only the menu and its own locals after
        # dispatching the item, never the window's members. Popping the menu on
        # the bar instead of the button would avoid the dead receiver but move
        # the popup by however much the button is inset, for no measured gain.
        button = self._button_for(title)
        if button is not None:
            self._highlight(button, False)
        return True

    # ============= Helpers =============

    def _highlight(self, button: wx.Button, on: bool) -> None:
        stylize_button(button, kind="ghost" if on else "flat", surface=_SURFACE)
        button.Refresh()
        # Update(), not just Refresh(): open_menu highlights the title and then
        # blocks in PopupMenu's modal loop, so a merely-invalidated button would
        # not repaint until the menu had already closed.
        button.Update()

    def _button_for(self, title: str) -> wx.Button | None:
        """The live title button labelled ``title``, or ``None``.

        Matching on ``GetLabel()`` over ``GetChildren()`` rather than on a cached
        list is deliberate, and is what makes open_menu's post-popup re-resolve
        safe: a destroyed child leaves ``GetChildren()`` the instant it is
        destroyed (measured), so this can only ever hand back a *live* button of
        the *current* bar. A cached list would keep handing back dead wrappers.

        One title per bar is already required by ``self._menus`` being a dict;
        this shares that constraint rather than adding one.
        """
        for child in self.GetChildren():
            if isinstance(child, wx.Button) and child.GetLabel() == title:
                return child
        return None


def build_menu(entries: Sequence[MenuEntry]) -> wx.Menu:
    """Render a spec into a live ``wx.Menu``, handlers bound."""
    menu = wx.Menu()
    for entry in entries:
        if entry.kind == "separator":
            menu.AppendSeparator()
        elif entry.kind == "check":
            item = menu.AppendCheckItem(wx.ID_ANY, entry.label)
            item.Check(entry.checked)
            if entry.on_toggle is not None:
                menu.Bind(wx.EVT_MENU, lambda evt, cb=entry.on_toggle: cb(evt.IsChecked()), item)
        elif entry.kind == "radio":
            submenu = wx.Menu()
            for value, label in entry.options:
                item = submenu.AppendRadioItem(wx.ID_ANY, label)
                item.Check(value == entry.current)
                if entry.on_select is not None:
                    submenu.Bind(
                        wx.EVT_MENU,
                        lambda _evt, selected=value, cb=entry.on_select: cb(selected),
                        item,
                    )
            menu.AppendSubMenu(submenu, entry.label)
        else:
            item = menu.Append(wx.ID_ANY, entry.label, entry.help)
            if entry.on_activate is not None:
                menu.Bind(wx.EVT_MENU, lambda _evt, cb=entry.on_activate: cb(), item)
    return menu


__all__ = ["AppMenuBar", "build_menu"]
