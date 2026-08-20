# What wxMSW actually honours

Measured on wxWidgets 3.2.8 / wxPython 4.2.4 by screenshotting a probe
frame, not assumed. These are the constraints every part of the app inherits.

This is the most reused artefact of the UI redesign (issue #962). It accumulated
over that redesign's nine phases and every entry is a **measurement** -- a probe
frame screenshotted and its pixels read -- not a reading of the wxWidgets
documentation. Several entries exist precisely because the documentation says the
opposite of what the pixels do.

It lived in `widgets/stylize.py`'s module docstring until phase 9, by which point
it was 404 lines of a 1294-line module -- 31% of a file whose actual subject is the
app's styling API. It moved here because it is **reference material about the
toolkit**, not API documentation for that module: nobody looking up
`stylize_button`'s signature wants 400 lines about `SysHeader32` first, and
somebody asking "can I colour a `wx.Gauge`?" should not have to open a source file
to find out. `widgets/stylize.py` keeps a pointer to this file.

Phase 9 also merged a duplicate: there were two `wx.StaticText` rows, one of them
a strict subset of the other.

**The house rule that produced every entry below**: *never set a colour, font or
flag and assume it applied.* Eleven separately documented calls in this app
silently did nothing, and one of them was shipping. Screenshot the result and read
the pixels; then write down what you measured -- including the routes that did
**not** work, because the next person will otherwise try them again.

---

## Contents

- [client edge](#client-edge)
- [`FlatNotebook`](#flatnotebook)
- [scrollbars](#scrollbars)
- [`wx.Bitmap` alpha](#wxbitmap-alpha)
- [`wx.BoxSizer`](#wxboxsizer)
- [`wx.Button`](#wxbutton)
- [`wx.CheckBox`](#wxcheckbox)
- [`wx.Choice`](#wxchoice)
- [`wx.ComboBox`](#wxcombobox)
- [`wx.dataview`](#wxdataview)
- [`wx.Gauge`](#wxgauge)
- [`wx.grid.Grid`](#wxgridgrid)
- [`wx.html.HtmlWindow`](#wxhtmlhtmlwindow)
- [`wx.html2.WebView`](#wxhtml2webview)
- [`wx.ListBox`](#wxlistbox)
- [`wx.ListCtrl`](#wxlistctrl)
- [`wx.Notebook`](#wxnotebook)
- [`wx.Panel`](#wxpanel)
- [`wx.ScrolledWindow`](#wxscrolledwindow)
- [`wx.Simplebook`](#wxsimplebook)
- [`wx.SpinCtrl`](#wxspinctrl)
- [`wx.SplitterWindow`](#wxsplitterwindow)
- [`wx.StaticBox`](#wxstaticbox)
- [`wx.StaticLine`](#wxstaticline)
- [`wx.StaticText`](#wxstatictext)
- [`wx.StatusBar`](#wxstatusbar)
- [`wx.TextCtrl`](#wxtextctrl)
- [`wx.ToggleButton`](#wxtogglebutton)

---

## Widgets and controls

### client edge

`wx.TextCtrl`, `wx.ListBox` and `wx.dataview`'s controls default to a sunken border
Windows draws at **`#FFFFFF`** with a `#828790` outer line, untouched by process dark
mode, by `SetBackgroundColour` or by `SetWindowTheme`. `wx.BORDER_NONE` deletes it, from
the constructor **and** post-construction via `SetWindowStyleFlag`, but on a composite
it must be applied to the window that owns the edge (`TreeListCtrl` wraps a
`DataViewCtrl`; the wrapper is not it). **Correction from phase 6b:** phase 6 recorded
that stripping a `wx.TextCtrl`'s edge leaves the dark-mode edit border rather than
nothing. Measured on the running builder, it leaves **nothing** -- the field renders as
`SURFACE_ALT` straight onto its parent, which on `SURFACE_PANEL` is 1.10:1. The edge
itself is a `#FFFFFF` line over `#7A7A7A`, i.e. ~21:1, so removing it is still right.
**Phase 6c answered what replaces it**: an own-drawn `BORDER_STRONG` ring painted by the
field's parent, since the boundary is the sole marker of the control and phase 0 puts
that case at >= 3:1. See `widgets.input_frame`; every `wx.TextCtrl` in the app is built
through it and `tests/test_widget_audit.py` fails on one that is not

### `FlatNotebook`

the generic replacement, and generic is not the same as reachable. Three colours have no
setter and no `SystemSettings` route: the tab strip's bottom edge is a **2px `#FFFFFF`**
band from `DrawTabsLine`, whose `GetSingleLineBorderColour()` is a hard-coded `wx.WHITE`
for every style except `FNB_FANCY_TABS`; the active tab's outline and the inactive tabs'
separators are `COLOR_BTNSHADOW`, set on the DC by `DrawTabs`. A renderer subclass
installed on the notebook's own `FNBRendererMgr` reaches all three. Separately,
`DrawTabs` strokes the strip's outline in the **tab container's** background -- a
different window from the notebook, defaulting to `#F0F0F0` -- so
`notebook._pages.SetBackgroundColour` is required on top of `SetTabAreaColour`. Tab
labels are measured and drawn with `SYS_DEFAULT_GUI_FONT` in **three** methods --
`CalcTabWidth`, `CalcTabHeight` and `DrawTabs` -- each of which builds the font inside
its own body, so there is nothing to pass in and all three have to be overridden
together or the strip measures itself with one font and draws with another. Phase 6b did
that; see `widgets.notebook`

**Tabs that do not fit are dropped, not clipped and not scrolled** -- and with
`FNB_NO_NAV_BUTTONS` (this app's default, chosen for the chrome) there is then no
arrow, chevron or menu, so the page has no route to it at all and no sign it
exists. The strip width needed is the sum of `CalcTabWidth` plus about 20px:
measured on the deck workspace's four tabs at **384px (en-US)** and **434px
(pt-BR)** against `CalcTabWidth` sums of 358 and 419. Below that the last tab
silently disappears. Nothing in a sizer sweep can see this -- the notebook does
not overflow its sizer, it reports a size that fits and shows less.

The three members that would tell you about it are only partly usable.
`GetNumOfVisibleTabs()` is correct. `IsTabVisible(i)` and `GetLastVisibleTab()`
are **wrong for the last tab**: with four tabs plainly drawn in an 884px strip
they still answer `IsTabVisible(3) is False` and `GetLastVisibleTab() == 2`. All
three are side effects of `DrawTabs`, so they report "nothing is visible" until
the strip has painted at least once -- an offscreen frame that has been
`Show()`n, `Layout()`d and yielded is not enough; it needs `Update()`. See
`tests/ui/test_notebook_tabs_fit.py`.

### scrollbars

not reachable from wx at all; dark process-wide via
`widgets.native_dark.enable_app_dark_mode()` -- **except a control that owns its
own scrollbar rather than being scrolled by a `wxScrolled` parent**, which also
needs a per-window theme class. Found in phase 9b while censusing the timer
alert: the status box's vertical bar is a `17x76` `#F0F0F0` block, **1292 light
pixels -- more than all six spin-control arrow pairs put together** -- and it had
been there since the box was written. Measured across five classes on a
scrolling `wx.TextCtrl`: `DarkMode_Explorer` and `Explorer` render it dark;
`DarkMode_CFD` (which is what an input otherwise wants) and `DarkMode` do not.
`stylize_textctrl` now applies `DarkMode_Explorer` when the field carries
`wx.TE_MULTILINE`, which reaches all four multiline fields in the tree.

### `wx.Bitmap` alpha

a bitmap carrying an alpha channel (built via `wx.Image.SetAlpha`) is alpha-blended
correctly by `wx.DC.DrawBitmap(bmp, x, y, True)` **onto an `AutoBufferedPaintDC`** --
the working route for an overlay gradient. `wx.GraphicsContext.Create(dc)` also works
but inherits whatever transform `PrepareDC` left on the DC, so "draw this at the bottom
of the client" becomes a transform question rather than a measurement; the bitmap needs
no such reasoning and caches. Either way `SetBackgroundStyle(wx.BG_STYLE_PAINT)` is the
precondition (see the `wx.*BufferedPaintDC` note): without it wxMSW's erase-background
pass owns the client and everything drawn into the buffer is silently discarded

### `wx.BoxSizer`

not a widget, but the row-overflow rule belongs with the other silent failures. When a
horizontal row's minimum widths exceed the client, wxSizer does **not** shrink the items
proportionally and does not clip the row as a whole: every item keeps its full minimum
except the **last**, which absorbs the entire deficit. Measured on the deck-workspace
header in pt-BR at the window's 1200px floor -- the row wanted 551px in a 506px panel,
the first seven controls rendered at exactly their minimums, and the printing button was
painted 14px wide against a 59px minimum. So "does this row fit" cannot be answered by
looking at any control except the last one, and a row of fixed-width controls needs one
deliberately flexible member (proportion 1 plus a floor) rather than an
`AddStretchSpacer`, which yields nothing back once the slack is gone. The **vertical**
case is worse, and phase 8 measured it on the deck builder: when the fixed items alone
exceed the client, the proportional item's share goes *negative* and is clamped to 0 --
so the one item that was meant to absorb the slack disappears entirely -- and every item
after it is still laid out, below the pane's bottom edge, with no scrollbar and no
clipping to say so. The results list rendered at exactly 0px and "Showing N cards." was
simply not on screen. There is no BoxSizer expression of "shrink this one first"; the
fix is a `wxScrolled` parent, which lays out to `max(client, virtual)`

### `wx.Button`

background + foreground honoured. The border is a **2px light-grey frame** (`#ADADAD`
outside, `#E1E1E1` inside) drawn by the theme, identical for every background and
unreachable from wx — but `wx.BORDER_NONE` deletes it, and the flag can be set *after*
construction with `SetWindowStyleFlag`. See `strip_native_button_frame()`. A
**disabled** button keeps its background at full saturation; only the label greys, so a
disabled state has to repaint the fill

### `wx.CheckBox`

label + surround honoured; the box **glyph** is drawn by `wxRendererNative` from the
light `BUTTON` theme class and is not reachable at all. `wx.lib.checkbox.GenCheckBox` is
**not** a way out: it builds its bitmaps from the same `wxRendererNative.DrawCheckBox`
and renders the identical white square. Replaced by the own-drawn
`widgets.checkbox.DarkCheckBox`

### `wx.Choice`

**both silently ignored** while the control is visual-styled; dark via Windows' dark
mode, or via `disable_native_theme()` as a fallback

### `wx.ComboBox`

same as `wx.Choice`

### `wx.dataview`

`DataViewListCtrl` draws its own alternate-row bands from the light theme, so half the
rows come back light grey on a dark surface. Not a way out of the ListCtrl selection
problem

`align=` on `AppendTextColumn` **is** honoured, for the data cells and the header
alike -- measured in phase 9 on a three-row probe, where `wx.ALIGN_RIGHT` put
`100.0 / 7.5 / 12.5` on a shared digit edge under a right-aligned heading. That
is worth stating because so much else on this control is not reachable: the radar
window's four numeric columns had been left at the left-aligned default since they
were written, and the fix really is the one argument.

### `wx.Gauge`

**both silently ignored**, and Windows' own dark mode does **not** reach it -- so unlike
`wx.Choice` there is no OS route. Measured across six variants: untouched, bg+fg,
`DarkMode_Explorer`, `DarkMode_Explorer::PROGRESS` and `wx.BORDER_NONE` all render the
identical `#E0E0E0` trough with the Windows green fill. Dropping it out of visual styles
is the only thing that works, and then both colours land -- see `stylize_gauge()`

### `wx.grid.Grid`

cell and label colours honoured. The **selection** is only half ours: with focus wxGrid
fills with `SetSelectionBackground`, without focus it draws `COLOR_BTNSHADOW`
(`#A0A0A0`) and ignores the colour entirely. A cell renderer that paints its own
background wins in both states, because wxGrid hands the whole cell to the renderer --
that is how the deck table view has always got a dark selection, and what
`widgets.grids.data_grid` generalises. `SetColLabelAlignment` is **grid-wide** (so it
cannot right-align a numeric column's header alone) and **overriding `DrawColLabel` from
Python does nothing** -- a subclass counting its own calls records zero after a full
paint. Per-column header alignment therefore needs an own-drawn header window.
`GetBestSize()` is the grid's **entire scrollable content** -- every column's width and
every row's height -- which is not a minimum in any useful sense for a scrolling control
and propagates straight up through whatever contains it. Measured in phase 8: visiting
the deck workspace's table view once with a 60-card deck took the *frame's* enforced
minimum height from 882 to **1461px**, after which the window could not be made smaller
again. Pin `SetMinSize` on the grid itself

### `wx.html.HtmlWindow`

renders roughly HTML 3.2 and is **not** a viable chart fallback: it ignores `bgcolor` on
a `<table>`, collapses a cell with no text in it, and ignores `height` on `<td>`. A bar
chart emitted into it draws every label and **no bars at all** -- verified by
screenshot, which is the only way this shows up. Own-draw instead (see
`widgets.charts.painter`)

### `wx.html2.WebView`

needs the Edge WebView2 runtime; `WebView.New` raises (or returns `None`) without it, so
every construction site needs a fallback. It also takes a light 1px client edge unless
constructed with `wx.BORDER_NONE`

### `wx.ListBox`

rows honoured; it takes the same near-white sunken client edge as `wx.TextCtrl` -- see
the `client edge` row

### `wx.ListCtrl`

rows honoured; the header is a native `SysHeader32` and ignores everything wx can set.
`SetHeaderAttr` returns `True` and applies only the *foreground*, which makes the white
header worse, not better. Dark only via Windows' own dark mode. The **selected row** is
OS-owned and `SetItemBackgroundColour` on it is overpainted in every state: with focus
it is the system accent (`#0078D7`, 3.34:1 on `SURFACE_PANEL`), without focus it is
`#F0F0F0` -- a near-white band, 13.2:1. Both are measured under Windows dark mode; the
review's "~1.1:1 tint" was the pre-dark-mode rendering and no longer describes it.
Neither is reachable, so a list that needs the app's selection token needs a different
control -- see `widgets.grids.data_grid`

### `wx.Notebook`

both ignored, **and Windows' dark mode does not reach it either** — migration to
`FlatNotebook` is the only fix (see `widgets.notebook`)

### `wx.Panel`

two traps, both found in phase 6c and both silent. (1) `wx.Panel`'s default style is
`wxTAB_TRAVERSAL`, and a `style=` argument **replaces** it rather than adding to it --
so `wx.Panel(parent, style=wx.BORDER_NONE)`, an idiom already in the tree, is a
traversal dead end. (2) `AcceptsFocusFromKeyboard()` answers "have I any focusable
children" from the children's `AcceptsFocus`, which is `True` for a read-only or
disabled `wx.TextCtrl` even though their `CanAcceptFocusFromKeyboard` is `False`. A
panel wrapping one therefore becomes a **tab stop itself**: focus lands on a bare panel
with no visible indicator. Override `AcceptsFocusFromKeyboard` to delegate to the child;
overriding `AcceptsFocus` as well is wrong and was measured -- traversal then stops
descending into the panel at all and skips the child even when it is focusable

### `wx.ScrolledWindow`

reports `1x1` as its best size when it has no child window (the deck grid and pile
views, which draw themselves), and its child's best size when it has one -- which is how
the table view's grid escaped. With a sizer it lays out to `max(client, virtual)` after
`FitInside`, which is the one wx idiom that expresses "shrink this region before the
ones around it". Four more, all measured in phase 8 while snapping the card views to row
boundaries. (1) At a **1px scroll rate** the scrollbar's *arrow buttons* move one pixel,
so on a view whose rows are 232px they are effectively dead; they have to be handled
rather than left to wx. (2) A custom-drawn one **takes focus when clicked** on wxMSW
with no `SetFocus` anywhere in the tree, so wx's keyboard scrolling
(Page/arrow/Home/End) is live on it whether or not anything asked for it -- verified
with real Win32 keystrokes. (3) **Physical scrolling does not strand viewport-fixed
chrome.** wx scrolls by blitting and invalidating only the exposed strip, which should
leave anything painted relative to the *viewport* (an edge fade) stale outside that
strip. Measured on both card views at scroll deltas from 3px to 232px: the scroll path
renders **byte-identical** to a full `Refresh`, so wxMSW is invalidating the whole
client for these windows. Worth re-measuring rather than assuming for any window that
gains children. (4) A synthetic `WM_VSCROLL` **cannot drive a thumb drag**: wxMSW reads
the position from `GetScrollInfo`, not from the message's `HIWORD`, so
`SB_THUMBPOSITION` sent from another process scrolls to wherever the real thumb happens
to be (0). `SB_LINE*` and `SB_PAGE*` do work. Automating a thumb drag needs real mouse
input

### `wx.Simplebook`

and every other `wxBookCtrlBase`: its own best size is the max over **all** its pages,
hidden ones included, and it asks each page for `GetBestSize()` -- never for
`GetEffectiveMinSize()`. So a hidden page sets the book's minimum, and `SetMinSize` **on
a page does not bound the book**; both were measured in phase 8 while chasing the
wx.grid row above. The floor has to go one level further down, on a child of the page,
because a window that owns a sizer *does* take its best size from that sizer's CalcMin
and CalcMin does consult each item's effective minimum

### `wx.SpinCtrl`

honoured on the edit field; the arrows are a separate `msctls_updown32` HWND that stays
light under every theme tried, Windows dark mode included. **Two HWNDs, and wx hands
back the wrong one**: `GetHandle()` returns the up-down, so `wx.BORDER_NONE` and
`strip_native_client_edge()` land on the arrows -- which never had a client edge -- and
the `#FFFFFF` hairline around the *field* survives, unchanged, pixel for pixel. The
field is the up-down's **buddy**, reachable only via `UDM_GETBUDDY`; see
`widgets.native_dark.strip_spin_buddy_client_edge()`, which is what
`stylize_spinctrl` still does for any `wx.SpinCtrl` that is not the app's own

Phase 9 put numbers on what that costs, off the captures: the arrow pair renders
`#ECECEC` (**12.6:1** on `SURFACE_PANEL`) in the opponent tracker and `#F0F0F0`
(**13.2:1**) in the timer alert, six controls across two windows. (Phase 9 read
that first colour as `#EBEBEB`; it is `#ECECEC`, i.e. `TEXT_PRIMARY`'s value.)
It was the brightest chrome left in the app and the last open half of "no light
native widget on a dark surface".

**Phase 9b closed it, and re-measured the "unreachable" claim first.** An
eight-variant probe on the up-down HWND itself -- untouched, `DarkMode_CFD`,
`DarkMode_Explorer`, `DarkMode_Explorer::SPIN`, `DarkMode::SPIN`,
`DarkMode_CFD::SPIN`, `ItemsView` and no visual style at all, each preceded by
`AllowDarkModeForWindow` and followed by `WM_THEMECHANGED` -- renders
**pixel-identical light arrows in all eight**. In the same probe the `Edit` half
*does* pick up dark mode, which is what makes the split easy to miss. So the
route out is the one phase 6c took for the text-input border: own-draw. See
`widgets.spin_ctrl.DarkSpinCtrl` -- an `InputFrame` hosting a real `wx.TextCtrl`
plus one own-drawn arrow window -- and `tests/test_widget_audit.py`, which now
fails on any `wx.SpinCtrl`, `wx.SpinCtrlDouble` or `wx.SpinButton` in `widgets/`.
`wx.SpinButton` is not a way out and neither is `wx.lib.agw.floatspin`: both are
the same `msctls_updown32`.

What replacing it costs, measured against the live native control with real
Win32 input before it was removed (`mouse_event`/`keybd_event` against the
HWNDs, values read back with `WM_GETTEXT`) -- these are the behaviours an
own-drawn spin has to reproduce, and the ones a rewrite loses silently:

| behaviour | native, measured |
|---|---|
| click an arrow | +/-1 |
| press and hold | +1 at once, first repeat at **576ms**, then a tick every **79-200ms** (mean ~120) |
| hold acceleration | step 1, **5 from t=2.33s**, 20 from t=5s -- comctl32's default `UDACCEL` |
| Up / Down | +/-1 |
| PageUp / PageDown | **nothing** |
| mouse wheel over the field | +/-1 per notch |
| typing | digits only, letters rejected at the keystroke |
| out-of-range typed value | shown as typed, clamped on kill-focus (`999` -> `250`) |
| emptied field | clamps to `min` on kill-focus |
| tab order | the field is a tab stop, the arrows are not |

A ``wx.TextCtrl``'s best **height** carries its border reserve on wxMSW: 25px
with a border, **17px** with `wx.BORDER_NONE`. A native `wx.SpinCtrl` is 25.
So a replacement built on `InputFrame` must *not* pass `BORDER_NONE` to its
field -- the `#FFFFFF` client edge comes off at the Win32 level
(`WS_EX_CLIENTEDGE`), which does not touch the wx style bits the best size is
computed from, and the control then lands on 25 with no magic number.

One dead binding surfaced while measuring: **wxMSW does not deliver
`wx.EVT_TEXT_ENTER` from a `wx.SpinCtrl` unless the control was constructed with
`wx.TE_PROCESS_ENTER`**, and none of the six sites passed it. The opponent
tracker has bound Enter on all four calculator fields since before this
redesign; pressing Enter left the result label empty while `Calculate` filled
it. The own-drawn control passes the style, so the binding now works.

### `wx.SplitterWindow`

the **sash** is drawn by `wxRendererNative` and is unreachable: `SetBackgroundColour`,
`disable_native_theme()` and every `SP_*` flag combination leave it light. With
`SP_3DSASH` it is 7px of `#F0F0F0` around a `#FFFFFF` centre line; without the 3-D flags
it is 4px and still light. `SetSashInvisible(True)` *is* dark and is a trap -- it also
sets `GetSashSize()` to 0, and the drag hit test comes from that size, so the split
silently stops being draggable. Own-drawn via `EVT_PAINT` (uniquely safe on a splitter:
the panes are child windows, so the only pixels the handler owns are the gutter). See
`widgets.splitter`

### `wx.StaticBox`

`SetForegroundColour` recolours **only the label**; `SetBackgroundColour` fills the
interior. The etched groove itself is drawn by the theme at **`#DCDCDC`** (10.96:1 on
`SURFACE_PANEL`) and is not reachable at all, and neither is the label's position on it.
Every one of the ten sites in the tree set both colours and every one still had a
near-white frame. `wx.StaticBoxSizer` does **not** reparent what is added to it on this
toolchain (probed on 4.2.4 / 3.2.8): a child parented to the box's parent keeps that
parent and still renders inside the box, which is why the ten sites used three different
conventions. Replaced by `widgets.section.SectionPanel`

### `wx.StaticLine`

**neither honoured**, and a `wx.LI_VERTICAL` one draws in the native *etched* colour,
which on `SURFACE_PANEL` comes out near-white — brighter than any other chrome on that
surface. The two horizontal StaticLines already in the tree read as dark and made this
look safe; a vertical rule beside text does not get lost the way a horizontal one does.
Use `create_divider()` (a 1px `wx.Panel`, whose background *is* honoured) for any rule
that has to match the theme

### `wx.StaticText`

background + foreground honoured. Two traps: `wx.ST_ELLIPSIZE_*` is only picked up from
the **constructor**, not from a later `SetWindowStyleFlag`; and without
`wx.ST_NO_AUTORESIZE` a `SetLabel` **resizes the control to fit the new text**, which
silently defeats both `wx.ALIGN_RIGHT` (the box hugs the string, so there is nothing to
align within) and ellipsization (a control that resized to its own text always fits).
See `create_status_label()`

### `wx.StatusBar`

background honoured, **foreground silently ignored** — hence `widgets.status_bar`

### `wx.TextCtrl`

background + foreground honoured **while enabled**. A **disabled** one discards them:
`Enable(False)` makes wxMSW paint the client area `#F0F0F0` and nothing gets it back --
setting the colour after `Disable()`, `disable_native_theme()` and Windows' own dark
mode were all measured and all leave the same near-white block. `SetEditable(False)`
*does* keep the dark fill, which is what `widgets.input_frame.InputFrame.EnableInput()`
uses to render a disabled field. Read-only is also the one state wxMSW drops out of
**tab order**: `CanAcceptFocusFromKeyboard()` is `False` for a `wx.TE_READONLY` field
and for a disabled one. The border is non-client area and unreachable -- see the `client
edge` row and `widgets.input_frame`

### `wx.ToggleButton`

background + foreground honoured; the *checked* state adds a 1px ring in the **system**
accent colour, which is a user setting rather than ours. Unused: the app's toggles are
plain buttons re-stylized on state change

Anything marked "via Windows' own dark mode" goes through `widgets.native_dark`,
which is enabled once at startup.

---

## Verifying with real Win32 input

Several phases verify behaviour with `keybd_event`/`mouse_event` rather than
synthesised wx events, because wx events cannot prove a native control still
works. One trap, found in phase 9b and costly because it looks exactly like a
regression: **`keybd_event(VK_UP)` without `KEYEVENTF_EXTENDEDKEY` arrives in wx
as `WXK_NUMPAD_UP` (377), not `WXK_UP` (315)** -- it is the numeric keypad's
scancode. A handler that binds only `WXK_UP` therefore does nothing under such a
harness while working perfectly for a real keyboard, and a harness that omits
the flag is testing the numpad. Send the flag for the arrow/navigation block
(`VK_LEFT`/`UP`/`RIGHT`/`DOWN`, `VK_PRIOR`/`NEXT`/`END`/`HOME`,
`VK_INSERT`/`DELETE`), and handle both key codes: the native controls answer
both, so a replacement that answers only one *is* a regression -- with NumLock
off, the keypad's 8 and 2 send the non-extended form.

## Nested modal loops and widget lifetime

Measured in the #962 menu-bar fix with real Win32 input, because the automation
harness deliberately never pops a menu (`widgets/menu_bar/spec.py` explains why).

* **A popup menu item's handler runs before `PopupMenu` returns.** wxMSW drains
  the `WM_COMMAND` itself inside `DoPopupMenu`, after `TrackPopupMenu` has already
  torn the menu down. So the statement after `PopupMenu(...)` is *not* the next
  thing to run once the user clicks -- the whole handler is, and so is anything
  that handler opens.
* **A `ShowModal` opened from that handler nests inside the popup**, and a third
  loop nests inside that (a `wx.MessageBox` from a dialog's own handler). The
  app's `File > Preferences...` is exactly this shape: a `ShowModal` two loops
  deep, with `EVT_CHOICE` firing apply-on-change while both are still live.
* **`wx.CallAfter` is not a way to defer work past a popup.** Queued from a popup
  item's handler it fires *inside* the nested `ShowModal`'s event loop -- still
  inside `PopupMenu`. It escapes the popup only when there is no inner loop to
  catch it, because `DoPopupMenu`'s own drain filters `WM_COMMAND` and nothing
  else. A `wx.CallAfter` at the *destroying* call site therefore does **not**
  protect a reference the *caller* is holding across `PopupMenu`; this was tried
  first and measured not to work.
* **Destroying a child window happens immediately.**
  `sizer.Clear(delete_windows=True)` and `child.Destroy()` free the C++ object on
  the spot: the Python wrapper goes falsy and the child is out of
  `GetChildren()` before the call returns. **Top-level windows are the
  exception** -- `frame.Close()`/`Destroy()` defers to idle, and a popup's
  `WM_COMMAND` drain never runs idle, so a frame closed from a menu item
  outlives the `PopupMenu` it was closed from (measured on `File > Exit`).
* **`bool(widget)` is a valid liveness test**, and the only one that does not
  itself raise: `False` iff the C++ object is gone. Hidden *and* disabled live
  windows stay truthy, so it cannot false-negative on a real widget.
  `GetChildren()` is the other safe route -- it can only ever hand back live
  windows.
* **An event queued for a window that is then destroyed is discarded**, not
  delivered. A handler bound *on* a widget therefore cannot fire after that
  widget dies, which is why the menu bar's `EVT_ENTER_WINDOW` /
  `EVT_LEAVE_WINDOW` lambdas capturing their own button are safe where
  `open_menu`'s stack reference was not.

The rule this leaves the app with: **a widget reference held across a modal call
must be re-resolved afterwards, never re-used.** `AppMenuBar.open_menu` looks its
title button up again after `PopupMenu` for exactly that reason -- see
`tests/ui/test_menu_bar_rebuild_during_open.py`, which fails with the reported
`RuntimeError: wrapped C/C++ object of type Button has been deleted` if it does
not.

## What wx will **not** tell you

`wx.Window.GetBackgroundColour()` is not an oracle for "what is this widget
painted". A child that has never had one set reports the *system* default
(`#F0F0F0`) whatever its parent is, and `InheritsBackgroundColour()` returns
`False` for it as well -- so there is no wx-level way to tell "explicitly
light" from "inherits a dark parent". Phase 6b tried to build a live-tree guard
on it and got 47 offenders, every one of them a widget that renders dark. Fonts
are the opposite: `GetFont()` *does* report the inherited value, which is why
`tests.ui.test_live_widget_audit` can check the type ladder on a running
window but not the palette.

## What `SetMinSize` actually does (measured in phase 8)

`GetEffectiveMinSize()` consults `GetBestSize()` **only for the components
of the min size left at `wxDefaultCoord`**, per axis. So `SetMinSize((-1,
240))` pins the height and lets content set the width -- which is how the card
inspector's minimum width came to depend on which card was loaded -- while
`SetMinSize((300, 240))` stops best size being consulted at all. If a widget's
content must not be allowed to set a dimension, that dimension has to carry a
real number, not -1.

## What wxMSW does with **fonts and sizes** (measured in phase 3)

* A child inherits its parent's font **at construction time only**, at every
  depth and across every widget class the app uses -- `StaticText`,
  `Button`, `TextCtrl`, `Choice`, `CheckBox`, `ListCtrl`,
  `SpinCtrl`, `StaticBox`, `ListBox` all reported the parent's 10pt.
* A widget that already exists when its parent's font changes keeps the old
  size, **and so does a widget created afterwards** if there is an intermediate
  panel: the panel captured its own font at *its* construction, and new children
  inherit the panel, not the frame. So the call really does have to be the first
  thing after `super().__init__()`, not merely "before the widget you care
  about".
* **Top-level windows never inherit.** `wx.Frame`, `wx.Dialog` and
  `wx.MiniFrame` constructed with a 10pt parent all reported the 9pt system
  default. Hence one `apply_base_font()` per top-level window (18 of them).
* `wx.BU_EXACTFIT` is the *only* way past that floor, and it overshoots in
  the other direction: it sizes a button to its text extent plus roughly 2px, so
  the deck workspace's `Grid`/`Table`/`Pile` toggles measured 30x18. A
  compact button therefore needs its size stated explicitly on top of the flag;
  see `size_compact_button()`.
* `wx.Button.GetBestSize()` has a **hard floor of 75x23 at 9pt and 75x25 at
  10pt, whatever the label** -- it is the Win32 default button size, not a
  text measurement. Any button given an explicit size under that reports a
  best-size deficit even when its label fits comfortably, so "best size >
  current size" is necessary but not sufficient evidence of clipping on a
  button; look at the pixels too. Button chrome around a label measures ~24px
  horizontally, which is the number to size a labelled button by.
* Text the app paints itself with `dc.SetFont()` is invisible to font
  inheritance. `type_font()` exists for exactly those surfaces.

## Own-drawn surfaces

Any window that paints itself with `wx.BufferedPaintDC` /
`wx.AutoBufferedPaintDC` must also call
`SetBackgroundStyle(wx.BG_STYLE_PAINT)`. Without it wxMSW leaves the backing
store alone, so a panel that draws nothing shows whatever was last blitted into
that screen region -- observed in phase 5 as a deck-list row appearing inside the
archetype summary box.
