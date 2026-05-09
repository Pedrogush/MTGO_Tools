"""English (United States) locale strings."""

from utils.i18n._en_us.app import MESSAGES as _APP
from utils.i18n._en_us.builder import MESSAGES as _BUILDER
from utils.i18n._en_us.bulk import MESSAGES as _BULK
from utils.i18n._en_us.card_panel import MESSAGES as _CARD_PANEL
from utils.i18n._en_us.deck_actions import MESSAGES as _DECK_ACTIONS
from utils.i18n._en_us.deck_results import MESSAGES as _DECK_RESULTS
from utils.i18n._en_us.guide import MESSAGES as _GUIDE
from utils.i18n._en_us.match import MESSAGES as _MATCH
from utils.i18n._en_us.metagame import MESSAGES as _METAGAME
from utils.i18n._en_us.notes import MESSAGES as _NOTES
from utils.i18n._en_us.radar import MESSAGES as _RADAR
from utils.i18n._en_us.research import MESSAGES as _RESEARCH
from utils.i18n._en_us.tabs import MESSAGES as _TABS
from utils.i18n._en_us.timer import MESSAGES as _TIMER
from utils.i18n._en_us.toolbar import MESSAGES as _TOOLBAR
from utils.i18n._en_us.top_cards import MESSAGES as _TOP_CARDS
from utils.i18n._en_us.tracker import MESSAGES as _TRACKER
from utils.i18n._en_us.tutorial import MESSAGES as _TUTORIAL
from utils.i18n._en_us.window import MESSAGES as _WINDOW

MESSAGES: dict[str, str] = {
    **_APP,
    **_BUILDER,
    **_BULK,
    **_CARD_PANEL,
    **_DECK_ACTIONS,
    **_DECK_RESULTS,
    **_GUIDE,
    **_MATCH,
    **_METAGAME,
    **_NOTES,
    **_RADAR,
    **_RESEARCH,
    **_TABS,
    **_TIMER,
    **_TOOLBAR,
    **_TOP_CARDS,
    **_TRACKER,
    **_TUTORIAL,
    **_WINDOW,
}
