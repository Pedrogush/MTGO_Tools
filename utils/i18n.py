"""Localization helpers for lightweight UI string translation."""

from __future__ import annotations

from typing import Final, Literal

LocaleCode = Literal["en-US", "pt-BR"]

DEFAULT_LOCALE: Final[LocaleCode] = "en-US"
SUPPORTED_LOCALES: Final[tuple[LocaleCode, ...]] = ("en-US", "pt-BR")

LOCALE_LABELS: Final[dict[LocaleCode, str]] = {
    "en-US": "English",
    "pt-BR": "Português (Brasil)",
}

MESSAGES: Final[dict[LocaleCode, dict[str, str]]] = {
    "en-US": {
        "app.status.ready": "Ready",
        "app.status.language_changed": "Language changed. Restart app to fully apply it.",
        "app.status.selected_language": "Selected language: {language}",
        "app.title.main_frame": "MTGO Deck Research & Builder",
        "app.label.deck_data_source": "Deck data source:",
        "app.label.language": "Language:",
        "app.menu.deck_data_source": "Deck data source",
        "app.menu.language": "Language",
        "app.choice.source.both": "Both",
        "app.choice.source.mtggoldfish": "MTGGoldfish",
        "app.choice.source.mtgo": "MTGO.com",
        "toolbar.opponent_tracker": "Opponent Tracker",
        "toolbar.timer_alert": "Timer Alert",
        "toolbar.match_history": "Match History",
        "toolbar.metagame_analysis": "Metagame Analysis",
        "toolbar.settings": "Settings",
        "toolbar.load_collection": "Load Collection",
        "toolbar.download_card_images": "Download Card Images",
        "toolbar.update_card_database": "Update Card Database",
        "toolbar.export_diagnostics": "Export Diagnostics",
        "toolbar.show_tutorial": "Show Tutorial",
        "deck_actions.daily_average": "Today's Average",
        "deck_actions.copy": "Copy",
        "deck_actions.load_deck": "Load Deck",
        "deck_actions.save_deck": "Save Deck",
        "research.format": "Format",
        "research.search_hint": "Search archetypes...",
        "research.reload_archetypes": "Reload Archetypes",
        "research.loading_archetypes": "Loading...",
        "research.failed_archetypes": "Failed to load archetypes.",
        "research.no_archetypes": "No archetypes found.",
    },
    "pt-BR": {
        "app.status.ready": "Pronto",
        "app.status.language_changed": "Idioma alterado. Reinicie o app para aplicar por completo.",
        "app.status.selected_language": "Idioma selecionado: {language}",
        "app.title.main_frame": "Pesquisa e Montagem de Deck MTGO",
        "app.label.deck_data_source": "Fonte de decks:",
        "app.label.language": "Idioma:",
        "app.menu.deck_data_source": "Fonte de decks",
        "app.menu.language": "Idioma",
        "app.choice.source.both": "Ambos",
        "app.choice.source.mtggoldfish": "MTGGoldfish",
        "app.choice.source.mtgo": "MTGO.com",
        "toolbar.opponent_tracker": "Rastreador de Oponente",
        "toolbar.timer_alert": "Alerta de Tempo",
        "toolbar.match_history": "Histórico de Partidas",
        "toolbar.metagame_analysis": "Análise de Metagame",
        "toolbar.settings": "Configurações",
        "toolbar.load_collection": "Carregar Coleção",
        "toolbar.download_card_images": "Baixar Imagens de Cartas",
        "toolbar.update_card_database": "Atualizar Banco de Cartas",
        "toolbar.export_diagnostics": "Exportar Diagnóstico",
        "toolbar.show_tutorial": "Mostrar Tutorial",
        "deck_actions.daily_average": "Média de Hoje",
        "deck_actions.copy": "Copiar",
        "deck_actions.load_deck": "Carregar Deck",
        "deck_actions.save_deck": "Salvar Deck",
        "research.format": "Formato",
        "research.search_hint": "Buscar arquétipos...",
        "research.reload_archetypes": "Recarregar Arquétipos",
        "research.loading_archetypes": "Carregando...",
        "research.failed_archetypes": "Falha ao carregar arquétipos.",
        "research.no_archetypes": "Nenhum arquétipo encontrado.",
    },
}


def normalize_locale(locale: str | None) -> LocaleCode:
    """Normalize locale values to the supported locale set."""
    if locale in SUPPORTED_LOCALES:
        return locale
    return DEFAULT_LOCALE


def translate(locale: str | None, key: str, **kwargs: object) -> str:
    """Return a translated string with fallback to default locale and key text."""
    normalized = normalize_locale(locale)
    template = MESSAGES.get(normalized, {}).get(key) or MESSAGES[DEFAULT_LOCALE].get(key)
    if template is None:
        return key
    if not kwargs:
        return template
    return template.format(**kwargs)
