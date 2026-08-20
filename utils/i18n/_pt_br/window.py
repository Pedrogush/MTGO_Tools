"""Window title UI strings. (Portuguese (Brazil))

See the en-US catalogue for why the ``MTGO`` token is gone; in pt-BR it was a
suffix rather than a prefix, on the same three windows.

Phase 9 added the six below. Seven of the app's eighteen top-level windows
carried hard-coded English titles (found by phase 4); the seventh, the
comp-rules popup, reuses ``window.title.rules_browser`` because it opens showing
the same thing the rules browser does. None of the seven is handed a locale --
they are opened from wherever the user happens to be, and the splash frame
exists before a controller does -- so they read the ambient locale via
``utils.i18n.t``. ``tests/test_window_titles.py`` fails on a new literal title.
"""

MESSAGES: dict[str, str] = {
    "window.title.opponent_tracker": "Rastreador de Oponente",
    "window.title.match_history": "Histórico de Partidas",
    "window.title.timer_alert": "Alerta de Tempo",
    "window.title.metagame_analysis": "Análise de Metagame",
    "window.title.top_cards": "Top Cartas",
    "window.title.radar": "Radar do Arquétipo — {format}",
    "window.title.diagnostics": "Exportar Diagnósticos",
    "window.title.guide_entry": "Entrada do Guia de Sideboard",
    "window.title.guide_import_options": "Opções de Importação",
    "window.title.offline_images": "Modo de Imagens Offline",
    "window.title.mana_keyboard": "Teclado de Mana",
    "window.title.splash": "Carregando MTGO Tools",
    "window.title.rules_browser": "Regras Compreensivas",
}
