# Handoff — Collapsible side-panel "third state" rendering artifact

**Date:** 2026-06-20
**Branch:** `feat/782-sb-guide-record`
**Status:** Symptom captured & characterized with hard evidence. **Root cause NOT
proven** — two plausible fixes were tested and *both refuted*. No new fix applied.
**This is the 3rd attempt at this issue; read the "Refuted hypotheses" section so
you don't repeat them.**

---

## 1. What the artifact is (CONFIRMED, evidence-backed)

When a collapsible side panel is toggled (left "research & builder" sidebar via
`left_toggle`, or the right card-inspector via `inspector_toggle`), the window
spends a visible interval in a **third visual state** that is neither the
*expanded* nor the *collapsed* rest layout.

In that third state the central **deck workspace** has not yet expanded to fill
the reclaimed width, so a band of the **parent panel background shows through**
where the workspace will eventually be.

### Pixel-level proof (this is the key fact)
The colour of the "void" band during the transition is **RGB (20, 22, 27)**.
That is exactly `DARK_BG` (`utils/.../colors.py`), the background colour of
`right_panel` set at `widgets/frames/app_frame/frame/__init__.py:238`.

It is **not**:
- `DARK_PANEL` (34, 39, 46) — the deck workspace / grid background, and
- **not** pure black (0, 0, 0).

Because the band shows the **parent's** `DARK_BG` rather than the grid's
`DARK_PANEL`, the deck-workspace subtree's painted pixels are simply absent
there during the transition; the parent background is what we are seeing.

Sampled with PIL (`(20,22,27)` at a void point through the transition, flipping
to `(34,39,46)` only once settled):

| frame (left collapse) | t (ms) | pixel @ (1050,400) | meaning |
|---|---|---|---|
| 07 | 227 | `(35,28,21)` (card art / pre-layout) | EXPANDED rest |
| 09 | 300 | `(20,22,27)` = DARK_BG | THIRD STATE (void) |
| 20 | 678 | `(20,22,27)` = DARK_BG | THIRD STATE (still) |
| 28 | 993 | `(34,39,46)` = DARK_PANEL | COLLAPSED rest |

### Timing (CONFIRMED, per-toggle)
Captured at ~29 fps (screen method). The third state persists, per toggle:

| session | interval | duration |
|---|---|---|
| left collapse  (rep0) | 263 → 962 ms | ~698 ms |
| left expand    (rep0) | 302 → 643 ms | ~340 ms |
| inspector collapse (rep0) | 268 → 537 ms | ~269 ms |
| inspector expand (rep0) | 272 → 539 ms | ~267 ms |
| left collapse  (rep1) | 252 → 688 ms | ~435 ms |
| left expand    (rep1) | 253 → 522 ms | ~269 ms |
| inspector collapse (rep1) | — | **none captured** |
| inspector expand (rep1) | 261 → 566 ms | ~305 ms |

The duration is **variable (0–700 ms) and intermittent** — one of eight toggles
showed no persistent void at all. This non-determinism is itself a clue: the
artifact is timing/scheduling-dependent, not a fixed-length animation.

Evidence screenshots are in `evidence/` (filenames carry the timestamps):
- `01..05_left_collapse_*` — the full pre → void → settled sequence.
- `06_inspector_collapse_third_state_234ms.png` — same artifact on the right panel.
- `07_left_collapse_PRINTWINDOW_no_void.png` — see §2.
- `report_screen.json`, `report_printwindow.json` — machine-readable per-frame data.

---

## 2. Why prior verification missed it (CONFIRMED — important)

The existing automation screenshot tool and the previous fix's verification use
**Win32 `PrintWindow(PW_RENDERFULLCONTENT)`** (`automation/server/screenshot.py`).
`PrintWindow` sends `WM_PRINT`, which makes the app **re-render its current
widget tree from scratch** into the capture DC. That re-render is itself the
kind of repaint that resolves the artifact, so the capture shows the *settled*
layout and the void is invisible.

Proof: re-running the exact same toggles with `--method printwindow` produced
**0 third-state frames across all sessions**, versus **7/8** with on-screen
capture (`report_printwindow.json` vs `report_screen.json`).

> **Corollary for the cause:** because `PrintWindow`'s WM_PRINT renders the
> widget tree at its *current HWND geometry* and shows the correct full-width
> layout, the **logical layout/geometry is already correct** shortly after the
> toggle. The defect is in getting those pixels **onto the screen**, not in the
> sizer math.

> **Action for whoever fixes this:** verify any fix with the **screen** capture
> method, never with a normal screenshot / PrintWindow — the latter is blind to
> this class of artifact. See §4 for the exact command.

---

## 3. Refuted hypotheses (do NOT repeat — already tested this session)

Both were applied to `_relayout_after_toggle()` in
`widgets/frames/app_frame/handlers/app_frame.py:357`, app restarted, and
re-captured with the screen method. **Both left the artifact fully intact
(7/8 sessions still showed the persistent void), and both were reverted.**

1. **Recursively `Refresh()` every descendant window + `Update()`** after the
   toggle. Rationale was that a top-level `Refresh()` does not invalidate native
   child HWNDs. Result: **no effect.**

2. **`self.SendSizeEvent()` + `self.Update()`** after the toggle (this is what
   `screenshot.py:143` does before capturing, to force a full synchronous size
   cascade). Result: **no effect.**

Conclusion: forcing synchronous invalidation **and** a synchronous size-event
cascade *inside the toggle handler* does not help. The deferred on-screen
repaint therefore happens **after the handler returns**, driven by some
mechanism that re-dirties / re-lays-out the workspace later — it is not a single
missing `Refresh`/`Layout`/size-event call at the toggle site.

---

## 4. Tooling built this session (the automation video suite)

New, committed under `automation/` — reusable for verifying the eventual fix.

- `automation/server/video_capture.py`
  - `grab_window_screen_bgra(hwnd)` — pure-Win32 **screen-DC `BitBlt`** grab of
    the literal on-screen pixels. Captures the artifact. Runs on any thread.
  - `grab_window_bgra(hwnd)` — `PrintWindow` grab (re-renders; blind to the
    artifact — kept for parity/contrast).
  - `VideoRecorder` — background thread that grabs frames as fast as it can
    (~29 fps on this machine) into memory with monotonic timestamps. The
    background thread is essential: toggle handlers run on the wx main thread,
    so a main-thread-dispatched screenshot can only ever see the settled state.
- `automation/server/video.py` — `start_video` / `stop_video` command handlers.
  `stop_video` writes each frame to `frame_<idx>_<t_ms>ms.png` + `manifest.json`
  and returns a compact summary (the transport does a single 64 KB `recv`, so
  the per-frame list must live on disk, not in the response).
- `automation/client.py`, `automation/cli.py` — `start-video` / `stop-video`
  CLI commands (with `--method screen|printwindow`, `--max-frames`, `--interval-ms`).
- `automation/capture_panel_transition.py` — orchestration + analysis. For each
  toggle it records a short session and flags any frame whose downscaled-grayscale
  distance to **both** the pre-toggle and post-toggle rest frames exceeds a
  threshold (a "third state"), grouping consecutive flagged frames into
  *persistent runs*. Writes a `report.json` and collects representative
  third-state screenshots.

### Reproduce / verify a fix
```bash
# 1. launch the app (Windows venv, from WSL):
nohup /init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe main.py --automation --automation-port 19847" >/tmp/app.log 2>&1 &
# wait for: env\Scripts\python.exe -m automation.cli ping  -> {"status":"ok"}

# 2. capture + analyze the transitions (SCREEN method — the one that sees it):
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.capture_panel_transition --out-dir transition_capture --reps 2 --pre-ms 250 --post-ms 900 --method screen"
# A correct fix => "persistent-third-state-runs=0".
```
(`transition_capture*` output dirs are scratch — not committed.)

---

## 5. Grounded leads for the next session (UNCONFIRMED — verify before trusting)

These follow from the evidence but were **not** proven; treat as starting points,
not answers.

- The deck grid canvas uses `SetBackgroundStyle(wx.BG_STYLE_PAINT)`
  (`widgets/panels/card_table_panel/grid_view.py:181`), which **suppresses
  automatic background erase** — so whenever the grid's `EVT_PAINT` lags, stale
  pixels (here the parent `DARK_BG`) remain on screen with nothing erasing them.
  This explains *why a lagging paint is visible* but not *why the paint lags*.
- The workspace is deeply nested: `right_panel → content_split → deck_workspace`
  (StaticBox) `→ deck_tabs` (**AGW `FlatNotebook`**) `→ deck_split`
  (**`wx.SplitterWindow`**, `SP_LIVE_UPDATE`) `→ main_table/side_table`
  (`CardTablePanel`). `FlatNotebook` and `SplitterWindow` manage their children's
  sizes via their **own** `EVT_SIZE`, which is queued, not run during the
  toggle's `root_panel.Layout()`. Since experiment 2 (`SendSizeEvent`) did not
  help, the deferral likely re-occurs *after* the handler — instrument it rather
  than assume.
- **Suggested first diagnostic:** add timestamped logging to
  `DeckGridView._on_size` and `DeckGridView._on_paint`
  (`grid_view.py:693` and `:482`) and to `_on_deck_split_size`
  (`center_panel.py`), toggle once, and read the log to see the actual ordering
  and the real wall-clock gap between the grid being resized and its first paint
  into the new area. That timeline will identify the deferring component — which
  neither static reading nor the two attempted fixes could pin down.
- Watch for `wx.CallAfter`/`CallLater`/idle-driven relayout in `FlatNotebook`
  (AGW) and in `CardTablePanel`/`grid_view` image-load callbacks
  (`grid_view.py` `_image_loaded` → `_patch_card_on_canvas`).

---

## 6. State left behind
- Production code: **unchanged** (both experiments reverted; `git diff` touches
  only `automation/`).
- New automation tooling: committed.
- This report + `evidence/` screenshots: committed under
  `docs/sb_panel_third_state/`.
- Scratch capture dirs (`transition_capture*`) left on disk, untracked — delete
  freely.
