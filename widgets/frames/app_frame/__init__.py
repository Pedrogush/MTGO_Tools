"""Main application frame package."""

from __future__ import annotations

from widgets.frames.app_frame.frame import AppFrame


def make_app_frame():
    """Construct the singleton AppController, attach the frame, and return it.

    Lives in the widgets layer so the composition root (``main.py``) can wire
    up the application without importing from ``controllers`` directly.
    """
    from controllers.app_controller import get_deck_selector_controller

    controller = get_deck_selector_controller()
    controller.attach_frame(AppFrame(controller=controller))
    return controller.frame


__all__ = ["AppFrame", "make_app_frame"]
