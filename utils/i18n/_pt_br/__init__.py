"""Portuguese (Brazil) locale strings."""

from utils.i18n._pt_br.app import MESSAGES as _APP
from utils.i18n._pt_br.builder import MESSAGES as _BUILDER
from utils.i18n._pt_br.bulk import MESSAGES as _BULK
from utils.i18n._pt_br.card_panel import MESSAGES as _CARD_PANEL
from utils.i18n._pt_br.deck_actions import MESSAGES as _DECK_ACTIONS
from utils.i18n._pt_br.deck_results import MESSAGES as _DECK_RESULTS
from utils.i18n._pt_br.guide import MESSAGES as _GUIDE
from utils.i18n._pt_br.match import MESSAGES as _MATCH
from utils.i18n._pt_br.metagame import MESSAGES as _METAGAME
from utils.i18n._pt_br.notes import MESSAGES as _NOTES
from utils.i18n._pt_br.radar import MESSAGES as _RADAR
from utils.i18n._pt_br.research import MESSAGES as _RESEARCH
from utils.i18n._pt_br.tabs import MESSAGES as _TABS
from utils.i18n._pt_br.timer import MESSAGES as _TIMER
from utils.i18n._pt_br.toolbar import MESSAGES as _TOOLBAR
from utils.i18n._pt_br.top_cards import MESSAGES as _TOP_CARDS
from utils.i18n._pt_br.tracker import MESSAGES as _TRACKER
from utils.i18n._pt_br.tutorial import MESSAGES as _TUTORIAL
from utils.i18n._pt_br.window import MESSAGES as _WINDOW

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
