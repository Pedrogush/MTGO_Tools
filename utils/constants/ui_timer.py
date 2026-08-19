"""Timer alert UI constants."""

# Height raised from 400 in phase 3. 400 never fitted the content: the panel's
# best height measured 491px before this phase, so ~90px -- the whole threshold
# list, which is the point of the window -- was already below the bottom edge
# and the "Active Challenge Timer" box was the first thing to go when the 4px
# spacing scale added 32px. Sized to the measured best height plus the frame's
# own chrome rather than to a round number.
TIMER_ALERT_FRAME_SIZE = (420, 580)
TIMER_ALERT_THRESHOLD_INPUT_SIZE = (80, -1)
TIMER_ALERT_REMOVE_BUTTON_SIZE = (30, -1)
TIMER_ALERT_STATUS_MIN_HEIGHT = 80
TIMER_ALERT_CHALLENGE_WRAP_WIDTH = 340
TIMER_ALERT_SCROLL_RATE_Y = 20

TIMER_ALERT_WATCH_INTERVAL_MS = 750
TIMER_ALERT_POLL_INTERVAL_MS = 1000
TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_MS = 30000
TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_SECONDS = 30

TIMER_ALERT_POLL_INTERVAL_MIN_MS = 250
TIMER_ALERT_POLL_INTERVAL_MAX_MS = 5000
TIMER_ALERT_REPEAT_INTERVAL_MIN_SECONDS = 5
TIMER_ALERT_REPEAT_INTERVAL_MAX_SECONDS = 300

TIMER_ALERT_DEFAULT_THRESHOLD_VALUE = "05:00"
