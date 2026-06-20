"""Capture and analyse the collapsible-side-panel collapse/expand transition.

Background
----------
The app's left sidebar and right inspector each collapse/expand via a gutter
button (``left_toggle`` / ``inspector_toggle``).  A toggle should move the
window between exactly two visual states: *expanded* and *collapsed*.  This
script records the window on a background thread *while* a toggle runs and then
flags any captured frame that matches **neither** the pre-toggle rest state nor
the post-toggle rest state — i.e. a transient "third state".

How it works
------------
For each toggle it runs one short capture *session*:

1. ``start_video`` (background recorder begins grabbing frames).
2. wait ``--pre-ms`` so the recorder banks the *pre-toggle* rest frame.
3. ``click`` the toggle (runs synchronously on the wx main thread).
4. wait ``--post-ms`` so the recorder banks the transient + the settled
   *post-toggle* rest frame.
5. ``stop_video`` flushes frames to PNG + ``manifest.json``.

Analysis is endpoint-relative and self-contained per session: the first frame
is the pre-toggle rest state, the last frame is the post-toggle rest state, and
any frame whose downscaled-grayscale distance to *both* endpoints exceeds
``--threshold`` is a third-state frame.  Runs of >= 2 consecutive third-state
frames are reported as *persistent* (a coherent third layout that was on screen
for an interval), distinguishing them from a single half-painted grab.

Run it on the Windows venv against an already-running ``--automation`` app:

    env\\Scripts\\python.exe automation/capture_panel_transition.py --out-dir transition_capture
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from typing import Any

from automation.client import AutomationClient

# Downscale every frame to this size before diffing — kills sub-pixel PrintWindow
# noise while preserving any real layout change (a panel appearing/disappearing
# is a large-area change that survives the downscale).
_SIG_W, _SIG_H = 240, 135


def _load_signature(path: str):
    """Return (grayscale PIL image at _SIG_W x _SIG_H, original_w, original_h)."""
    from PIL import Image as PilImage

    with PilImage.open(path) as im:
        ow, oh = im.size
        sig = im.convert("L").resize((_SIG_W, _SIG_H))
    return sig, ow, oh


def _mean_abs_diff(a, b) -> float:
    """Mean absolute per-pixel difference (0..255) between two grayscale sigs."""
    from PIL import ImageChops, ImageStat

    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def _analyze_session(session_dir: str, threshold: float) -> dict[str, Any]:
    """Flag frames differing from both endpoints; return a summary dict."""
    with open(os.path.join(session_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    frames = manifest["frames"]
    if len(frames) < 3:
        return {"session": os.path.basename(session_dir), "frames": len(frames), "third_state": []}

    sigs = [_load_signature(f["path"]) for f in frames]
    start_sig = sigs[0][0]
    end_sig = sigs[-1][0]
    start_dim = (sigs[0][1], sigs[0][2])
    end_dim = (sigs[-1][1], sigs[-1][2])

    flagged: list[dict[str, Any]] = []
    for f, (sig, w, h) in zip(frames, sigs):
        d_start = _mean_abs_diff(sig, start_sig)
        d_end = _mean_abs_diff(sig, end_sig)
        if min(d_start, d_end) > threshold:
            flagged.append(
                {
                    "index": f["index"],
                    "t_ms": f["t_ms"],
                    "path": f["path"],
                    "size": [w, h],
                    "d_start": round(d_start, 2),
                    "d_end": round(d_end, 2),
                    "min_d": round(min(d_start, d_end), 2),
                }
            )

    # Group flagged frames into runs of consecutive indices (persistence).
    runs: list[list[dict[str, Any]]] = []
    for item in flagged:
        if runs and item["index"] == runs[-1][-1]["index"] + 1:
            runs[-1].append(item)
        else:
            runs.append([item])

    return {
        "session": os.path.basename(session_dir),
        "frames": len(frames),
        "duration_s": manifest.get("duration_s"),
        "fps": manifest.get("fps"),
        "start_size": list(start_dim),
        "end_size": list(end_dim),
        "size_changed_endpoints": start_dim != end_dim,
        "third_state": flagged,
        "persistent_runs": [
            {
                "len": len(run),
                "t_start_ms": run[0]["t_ms"],
                "t_end_ms": run[-1]["t_ms"],
                "peak": max(run, key=lambda x: x["min_d"]),
            }
            for run in runs
            if len(run) >= 2
        ],
    }


def _run_session(
    client: AutomationClient,
    widget: str,
    label: str,
    out_root: str,
    *,
    max_frames: int,
    pre_ms: int,
    post_ms: int,
    threshold: float,
    method: str,
) -> dict[str, Any]:
    session_dir = os.path.join(out_root, label)
    print(f"[{label}] start_video ...", flush=True)
    client.start_video(max_frames=max_frames, interval_ms=0.0, method=method)
    time.sleep(pre_ms / 1000.0)
    print(f"[{label}] click {widget}", flush=True)
    client.click(widget)
    time.sleep(post_ms / 1000.0)
    summary = client.stop_video(out_dir=session_dir)
    print(f"[{label}] captured {summary.get('count')} frames @ {summary.get('fps')} fps", flush=True)

    analysis = _analyze_session(session_dir, threshold)
    analysis["capture"] = summary
    n_flag = len(analysis["third_state"])
    n_runs = len(analysis["persistent_runs"])
    print(
        f"[{label}] third-state frames: {n_flag}  persistent runs: {n_runs}"
        f"  endpoint-size-change: {analysis['size_changed_endpoints']}",
        flush=True,
    )
    return analysis


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=19847)
    ap.add_argument("--out-dir", default="transition_capture")
    ap.add_argument("--reps", type=int, default=2, help="Cycles per panel (default 2)")
    ap.add_argument("--max-frames", type=int, default=120)
    ap.add_argument("--pre-ms", type=int, default=140, help="Settle before the toggle click")
    ap.add_argument("--post-ms", type=int, default=550, help="Capture window after the click")
    ap.add_argument(
        "--threshold",
        type=float,
        default=6.0,
        help="Mean-abs-diff (0..255) over both endpoints to flag a third state",
    )
    ap.add_argument(
        "--method",
        choices=["screen", "printwindow"],
        default="screen",
        help="screen = on-screen pixels (catches ghosts); printwindow = re-render",
    )
    args = ap.parse_args()

    out_root = os.path.abspath(args.out_dir)
    if os.path.isdir(out_root):
        shutil.rmtree(out_root)
    os.makedirs(out_root, exist_ok=True)

    client = AutomationClient(port=args.port, timeout=60.0)
    info = client.get_window_info()
    print(f"window: {info.get('size')} maximized-ish; title={info.get('title')!r}", flush=True)

    # Reference rest screenshots for the handoff doc.
    client.screenshot(path=os.path.join(out_root, "ref_initial.png"))

    sessions: list[dict[str, Any]] = []
    for rep in range(args.reps):
        for widget, base in (("left_toggle", "left"), ("inspector_toggle", "inspector")):
            for direction in ("a", "b"):  # a = first toggle, b = toggle back
                label = f"{base}_{rep}_{direction}"
                sessions.append(
                    _run_session(
                        client,
                        widget,
                        label,
                        out_root,
                        max_frames=args.max_frames,
                        pre_ms=args.pre_ms,
                        post_ms=args.post_ms,
                        threshold=args.threshold,
                        method=args.method,
                    )
                )
                time.sleep(0.2)

    # Collect representative third-state screenshots into one folder.
    flagged_dir = os.path.join(out_root, "_third_state")
    os.makedirs(flagged_dir, exist_ok=True)
    collected = 0
    for s in sessions:
        for run in s["persistent_runs"]:
            peak = run["peak"]
            dst = os.path.join(
                flagged_dir,
                f"{s['session']}_t{peak['t_ms']}ms_mind{peak['min_d']}.png",
            )
            shutil.copyfile(peak["path"], dst)
            collected += 1

    report = {
        "window": info.get("size"),
        "method": args.method,
        "threshold": args.threshold,
        "sessions": sessions,
        "third_state_screenshots": collected,
    }
    with open(os.path.join(out_root, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    total_persistent = sum(len(s["persistent_runs"]) for s in sessions)
    print(
        f"\nDONE. sessions={len(sessions)} persistent-third-state-runs={total_persistent}"
        f" representative-screenshots={collected}\n  report: {os.path.join(out_root, 'report.json')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
