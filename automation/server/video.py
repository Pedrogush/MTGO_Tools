"""Video-capture command handlers (``start_video`` / ``stop_video``).

These exist to record the *transition* a window goes through while a layout
toggle runs — e.g. collapsing/expanding a side panel — which a single
screenshot cannot show.  See ``video_capture.VideoRecorder`` for why the grab
runs on a background thread.

``start_video`` spins up the recorder and returns immediately; the caller then
drives the UI (clicking a toggle) while frames accumulate, and finally calls
``stop_video`` to flush the captured frames to PNG files and a ``manifest.json``
on disk.  The stop response is deliberately compact (counts + the manifest
path, not the per-frame list) because the transport does a single 64 KB
``recv`` on both ends (see ``transport.BUFFER_SIZE``).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from automation.server.video_capture import VideoRecorder

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class VideoMixin(_Base):
    """Start/stop a background frame recorder over the main application window."""

    _video_recorder: VideoRecorder | None = None

    def _handle_start_video(
        self, max_frames: int = 240, interval_ms: float = 0.0, method: str = "screen"
    ) -> dict[str, Any]:
        """Begin recording frames of the main window on a background thread.

        ``max_frames`` caps memory use (each frame is a full-window 32bpp
        bitmap).  ``interval_ms`` throttles the grab loop; 0 means "as fast as
        possible", which maximises the chance of catching a short-lived
        transient frame.  ``method`` selects the grabber: ``"screen"`` (default)
        copies literal on-screen pixels so it catches ghost/transient artefacts;
        ``"printwindow"`` re-renders the widget tree (faithful to logical state,
        but hides on-screen-only artefacts).
        """
        if getattr(self, "_video_recorder", None) is not None:
            return {"recording": False, "error": "video already recording"}
        hwnd = self.frame.GetHandle()
        recorder = VideoRecorder(
            hwnd,
            max_frames=int(max_frames),
            interval_s=float(interval_ms) / 1000.0,
            method=method,
        )
        recorder.start()
        self._video_recorder = recorder
        return {"recording": True, "max_frames": int(max_frames), "method": method}

    def _handle_stop_video(self, out_dir: str | None = None) -> dict[str, Any]:
        """Stop recording, write frames to PNG + ``manifest.json`` under *out_dir*.

        Returns a compact summary: frame count, capture duration, effective fps,
        the output directory and the manifest path.  Per-frame detail lives in
        the manifest file on disk so the response stays under the transport's
        64 KB cap.
        """
        import json
        import tempfile
        from datetime import datetime

        recorder = getattr(self, "_video_recorder", None)
        if recorder is None:
            return {"error": "no video recording in progress"}

        frames = recorder.stop()
        self._video_recorder = None

        if out_dir is None:
            out_dir = os.path.join(
                tempfile.gettempdir(), f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
        os.makedirs(out_dir, exist_ok=True)

        manifest: list[dict[str, Any]] = []
        for index, (t, w, h, data) in enumerate(frames):
            t_ms = round(t * 1000.0, 1)
            name = f"frame_{index:04d}_{t_ms:09.1f}ms.png"
            path = os.path.join(out_dir, name)
            self._write_bgra_png(data, w, h, path)
            manifest.append({"index": index, "t_ms": t_ms, "path": path, "w": w, "h": h})

        duration_s = round(frames[-1][0], 3) if frames else 0.0
        fps = round(len(frames) / duration_s, 1) if duration_s > 0 else 0.0

        manifest_path = os.path.join(out_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(
                {"frames": manifest, "count": len(frames), "duration_s": duration_s, "fps": fps},
                fh,
                indent=2,
            )

        return {
            "count": len(frames),
            "duration_s": duration_s,
            "fps": fps,
            "dir": os.path.abspath(out_dir),
            "manifest": os.path.abspath(manifest_path),
        }

    @staticmethod
    def _write_bgra_png(data: bytes, w: int, h: int, path: str) -> None:
        """Encode top-down BGRA bytes to a PNG via Pillow."""
        from PIL import Image as PilImage

        # raw BGRA, top-down rows → PIL handles the channel swap with the
        # "BGRA" rawmode, so no per-pixel Python work.
        img = PilImage.frombuffer("RGBA", (w, h), data, "raw", "BGRA", 0, 1)
        img.save(path, format="PNG")
