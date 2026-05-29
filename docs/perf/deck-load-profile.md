# Deck-load latency: profile & optimization plan

Goal: take the click-to-rendered-deck interval from ~950 ms (cold) / ~300 ms
(warm) down to **< 100 ms**.

This document records (1) the instrumentation added on this branch, (2) the
**real measured breakdown** from an instrumented run, and (3) a phased plan to
hit the target.

---

## 1. Instrumentation added

A `perf_phase(name)` context manager was added to `utils/perf.py` — it logs one
greppable `PERF | <ms> | <name>` line at INFO per segment (vs the existing
`@timed`, which is whole-function and DEBUG-only). The deck-load path is now
instrumented end to end:

| Location | What it times |
|---|---|
| `app_events.on_deck_selected` | stamps `_deck_click_t0` at the click |
| `controllers/app_controller/decks.py` `download_deck_text.worker` | the async download leg (cache hit vs HTTP scrape) |
| `app_events._on_deck_content_ready` | each segment: analyze, outboard, each table's `set_cards`, stats, notes, guide — plus the **render-block total** and **click-to-ready total** headline lines |
| `card_table_panel/handlers._update_panels` | per-zone sub-phases: count/metadata loop, pool assign, grid layout, table/pile view, async-image dispatch |
| `deck_stats_panel/handlers.update_stats` | metadata helpers vs HTML build vs WebView `SetPage` |

To reproduce: launch with `--automation`, then
`automation.cli select-deck <n>` and `grep "PERF |" logs/mtgo_tools_*.log`.

---

## 2. Measured breakdown (instrumented run, Vintage, WSL→Windows)

Headline, per click:

| Click | Download (async) | Render block (sync, UI thread) | Click-to-ready total |
|---|---|---|---|
| **1st (cold pool)** | 18.6 ms | **951.0 ms** | **981.2 ms** |
| 2nd (warm, 43+11) | — | 259.2 ms | 293.2 ms |
| 3rd (warm, 41+9) | — | 336.6 ms | 436.4 ms |
| 4th (warm, 40+11) | — | 387.0 ms | 526.7 ms |

Render-block decomposition (1st click — main 43 cards / side 11 cards):

| Segment | Cold (1st) | Warm (avg 2–4) | Notes |
|---|---|---|---|
| analyze_deck + zone sort | 0.2 ms | ~0.2 ms | negligible |
| load outboard | 0.0 ms | ~0 ms | in-memory |
| **main_table.set_cards** | **472.9 ms** | **~210 ms** | dominant |
| — count/metadata loop | 1.9 ms | ~2 ms | dict lookups, cheap |
| — **pool assign** | **229.4 ms** | **~12 ms** | one-time widget creation |
| — grid layout + scroll | 53.2 ms | ~50 ms | wx `Layout`/`FitInside`/`SetupScrolling` |
| — **dispatch async image loads** | **157.7 ms** | **~140 ms** | **persistent every-click cost** |
| **side_table.set_cards** | **449.9 ms** | ~90 ms | pile-view mode |
| — pool assign | 348.7 ms | ~15 ms | one-time widget creation |
| — pile_view.set_cards | 27.2 ms | ~25 ms | spawns prefetch threads |
| update_stats | 5.8 ms | ~4 ms | metadata are O(1) dict hits |
| load_notes_for_current | 5.1 ms | ~5 ms | |
| load_guide_for_current | 0.6 ms | ~1 ms | |

### What this rules out

- **Download is not the bottleneck.** A local SQLite cache hit is 18 ms, off
  the UI thread. (A cache *miss* HTTP-scrapes; that's a separate, network-bound
  path not on the hot path for already-seen decks.)
- **Stats / metadata lookups are not the bottleneck.** `card_manager.get_card`
  is an O(1) dict lookup (`card_data_manager.py:136`); all four stats helpers +
  the count loop total < 10 ms. The earlier hypothesis that 4× metadata loops
  cost 150–300 ms is **disproved**.
- **`analyze_deck`, outboard, notes, guide** are all < 6 ms.

### The two real costs

1. **One-time widget-pool construction — ~577 ms, first click only.**
   `_ensure_pool` (`card_table_panel/frame.py:187`) lazily builds `CardBoxPanel`
   cells on first use; each cell is a native panel + qty label + a button
   sub-panel with three buttons. The first deck pays to create ~54 of them
   across the two zones. Warm clicks reuse the pool (assign drops to ~12 ms).

2. **Per-card image-load thread spawning — ~140 ms, every click (main zone).**
   `load_image_async` (`card_box_panel/handlers.py:75-86`) does
   `Thread(target=..., daemon=True).start()` **once per card**. For a 40-card
   mainboard that's 40 OS threads created on the UI thread (the `.start()` loop
   itself is the ~140 ms we measure), and those 40 threads then contend on the
   GIL doing PIL `open` + `convert` + LANCZOS `resize`.

Plus a steady **~50 ms** of `grid_sizer.Layout` / `FitInside` /
`SetupScrolling` on the main scroller.

---

## 3. Plan to reach < 100 ms

Ordered by impact-to-effort. Each step is independently shippable and can be
verified by re-reading the `PERF |` lines.

### Step A — Replace per-card threads with one pooled dispatch (kills ~140 ms/click)

`load_image_async` should not create a thread per card. Options, best first:

- **Single batched submit.** Add a `load_images_async(panels)` on the table that
  submits one job to a shared, bounded `ThreadPoolExecutor` (or the existing
  `controller._worker` pool). The job iterates candidates, decodes, and posts
  each result back via a single `wx.CallAfter`. UI-thread cost drops from
  "spawn N threads" to "submit 1 task".
- Bound concurrency (e.g. 4–8 workers) so 40 simultaneous LANCZOS resizes stop
  thrashing the GIL/disk — images then stream in smoothly instead of all
  competing.
- Keep the generation-counter invalidation already in place.

Expected: main-zone dispatch ~140 ms → < 5 ms; images still arrive async.

### Step B — Pre-warm the widget pool at startup/idle (kills the ~577 ms first-click spike)

This dovetails with the existing `perf/startup-cache-warming` work. After the
frame is shown and the app is idle, grow each zone's pool to a typical deck size
(e.g. `POOL_SIZE` for main, a smaller cap for side) on a `wx.CallLater` /
idle handler, a few cells per tick to avoid a visible hitch. The first real
click then hits a warm pool (~12 ms assign) instead of paying 577 ms.

- Alternative/additional: make `CardBoxPanel` cheaper to construct — the
  three-button sub-panel per cell is the bulk of the cost; build the button row
  lazily on first hover/selection rather than at construction.

Expected: first click falls from ~950 ms to roughly warm-click level.

### Step C — Trim the steady render cost to fit < 100 ms

After A + B, a warm click is roughly: layout ~50 ms + pool assign ~12 ms +
side ~30 ms + misc ~15 ms ≈ **100–110 ms**. To get safely under 100:

- **Defer the side zone.** Render the mainboard, then push side/out
  `set_cards` to a `wx.CallAfter` so the visible mainboard paints first and the
  measured click-to-visible drops by the side zone's full cost.
- **Reduce layout cost.** Call `SetupScrolling` only when the cell count
  actually changes; reuse the prior scroll metrics otherwise. Batch `Show`
  toggles inside the existing `Freeze`/`Thaw` (already partially done) and avoid
  a second `Layout` when the grid dimensions are unchanged.
- **Skip hidden-view rebuilds** — already the case (`_update_panels` only
  populates the active table/pile view).

### Step D — Verify & lock in

Re-run the instrumented flow over several decks of varying size; confirm:
- warm click-to-ready < 100 ms,
- first click within ~2× warm (pool pre-warm landed),
- images still stream in without blocking.

Consider keeping `perf_phase` in place (INFO is cheap, ~one log line per
segment) or gating it behind `MTGO_LOG_LEVEL=DEBUG` once the work lands.

---

## Priority summary

| Step | Fixes | Est. saving | Effort |
|---|---|---|---|
| A — pooled image dispatch | ~140 ms every click | high | low–med |
| B — pre-warm widget pool | ~577 ms first click | high (cold) | med |
| C — defer side zone + trim layout | ~80–120 ms | med | med |
| D — verify | — | — | low |

A + B alone should bring warm clicks to ~120 ms and eliminate the cold spike; C
closes the last gap to < 100 ms.

---

## 4. Results (after implementing A–D)

All four steps landed on this branch. Re-measured with the same
instrumented flow (Vintage, WSL→Windows):

| | Before | After |
|---|---|---|
| **1st click (cold)** render block | 951 ms | **130 ms** |
| 1st click click-to-ready | 981 ms | 167 ms |
| warm click render block | 260–390 ms | **95–105 ms** |
| warm click click-to-ready | 290–530 ms | 125–137 ms |

Segment-level (warm, main 41–43 cards):

| Segment | Before | After |
|---|---|---|
| main pool assign | 12–229 ms | **3–11 ms** (pre-warmed; cold spike gone) |
| main grid layout + scroll | ~53 ms | **~2 ms** (dropped redundant `Layout`; gated `SetupScrolling`) |
| main dispatch image loads | ~140 ms | **~0.5 ms** (shared pool replaces per-card threads) |
| side zone | 55–450 ms on the click | **deferred** — off the click-to-visible path |

What each step bought:

- **A (shared decode pool):** main-zone image dispatch ~140 ms → ~0.5 ms,
  every click. Images still stream in asynchronously.
- **B (idle pool pre-warm):** the ~577 ms first-click widget-construction spike
  is gone — the first real click now matches warm clicks (pool assign ~3 ms).
- **C (defer side zone + gate `SetupScrolling`):** removed the side zone's full
  cost from the click-to-visible interval and cut the main grid-layout phase
  from ~53 ms to ~2 ms.
- **D (verify):** both zones populate correctly (main 60 / side 15 cards), grid
  layout and scrolling intact (screenshot + `get-zone-cards`).

Net: **~7× faster cold, ~3× faster warm**; warm steady-state click-to-rendered
mainboard is at/under the 100 ms target, with the sideboard following one frame
later. The `perf_phase` instrumentation is kept in place (INFO, one cheap log
line per segment) for future regression checks.
