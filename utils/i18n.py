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
        # App-level
        "app.status.ready": "Ready",
        "app.status.language_changed": "Language changed. Restart app to fully apply it.",
        "app.status.selected_language": "Selected language: {language}",
        "app.title.main_frame": "MTGO Deck Research & Builder",
        "app.label.deck_data_source": "Deck data source:",
        "app.label.language": "Language:",
        "app.choice.source.both": "Both",
        "app.choice.source.mtggoldfish": "MTGGoldfish",
        "app.choice.source.mtgo": "MTGO.com",
        # Toolbar buttons
        "toolbar.opponent_tracker": "Opponent Tracker",
        "toolbar.timer_alert": "Timer Alert",
        "toolbar.match_history": "Match History",
        "toolbar.metagame_analysis": "Metagame Analysis",
        "toolbar.load_collection": "Load Collection",
        "toolbar.download_card_images": "Download Card Images",
        "toolbar.update_card_database": "Update Card Database",
        # Deck action buttons
        "deck_actions.daily_average": "Today's Average",
        "deck_actions.copy": "Copy",
        "deck_actions.save_deck": "Save Deck",
        # Research panel
        "research.format": "Format",
        "research.search_hint": "Search archetypes...",
        "research.reload_archetypes": "Reload Archetypes",
        "research.loading_archetypes": "Loading...",
        "research.failed_archetypes": "Failed to load archetypes.",
        "research.no_archetypes": "No archetypes found.",
        # Panel / static box labels
        "panel.deck_results": "Deck Results",
        "panel.card_inspector": "Card Inspector",
        "panel.deck_workspace": "Deck Workspace",
        # Notebook / tab labels
        "tab.research": "Research",
        "tab.builder": "Builder",
        "tab.deck_tables": "Deck Tables",
        "tab.mainboard": "Mainboard",
        "tab.sideboard": "Sideboard",
        "tab.stats": "Stats",
        "tab.sideboard_guide": "Sideboard Guide",
        "tab.deck_notes": "Deck Notes",
        # Simple status messages
        "status.collection_not_loaded": "Collection inventory not loaded.",
        "status.select_archetype": "Select an archetype to view decks.",
        "status.loading_card_db_restore": "Loading card database to restore saved deck...",
        "status.deck_copied": "Deck copied to clipboard.",
        "status.deck_saved": "Deck saved successfully.",
        "status.loading": "Loading\u2026",
        "status.loading_card_data_search": "Loading card data\u2026 (search will run automatically)",
        "status.downloading_decks": "Downloading decks\u2026",
        "status.card_db_downloaded": "Card image database downloaded, indexing printings\u2026",
        # Parametric status messages
        "status.archetypes_loaded": "Loaded {count} archetypes for {format}.",
        "status.error": "Error: {error}",
        "status.no_decks_for_archetype": "No decks for {archetype}.",
        "status.loading_deck": "Loading deck {deck_name}\u2026",
        "status.decks_loaded": "Loaded {count} decks for {archetype}. Click a deck to load it.",
        "status.deck_ready": "Deck ready ({source}).",
        "status.error_loading_decks": "Error loading decks: {error}",
        "status.deck_download_failed": "Deck download failed: {error}",
        "status.daily_average_failed": "Daily average failed: {error}",
        # Dialog titles
        "dialog.copy_deck": "Copy Deck",
        "dialog.save_deck": "Save Deck",
        "dialog.deck_saved": "Deck Saved",
        "dialog.archetype_error": "Archetype Error",
        "dialog.deck_error": "Deck Error",
        "dialog.deck_download": "Deck Download",
        "dialog.card_data_error": "Card Data Error",
        "dialog.daily_average": "Daily Average",
        # Dialog prompts and message box text
        "msg.no_deck_to_copy": "No deck to copy.",
        "msg.clipboard_error": "Could not access clipboard.",
        "msg.load_deck_first": "Load a deck first.",
        "msg.deck_name_prompt": "Deck name:",
        "msg.deck_write_failed": "Failed to write deck file:\n{error}",
        "msg.deck_saved_path": "Deck saved to {path}",
        "msg.deck_saved_db_id": "\nDatabase ID: {deck_id}",
        "msg.no_decks_found": "No decks found.",
        "msg.failed_load_decks": "Failed to load decks.",
        "msg.mana_value_numeric": "Mana value must be numeric.",
        "msg.archetypes_load_failed": "Unable to load archetypes:\n{error}",
        "msg.deck_id_missing": "Deck identifier missing.",
        "msg.deck_download_failed": "Failed to download deck:\n{error}",
        "msg.card_data_load_failed": "Failed to load card database:\n{error}",
        "msg.daily_average_failed_body": "Failed to build daily average:\n{error}",
        "msg.no_deck_data": "{archetype}\n\nNo deck data available.",
        "msg.archetypes_loaded_hint": "Select an archetype to view decks.\nLoaded {count} archetypes.",
        "msg.fetching_decks": "{archetype}\n\nFetching deck results\u2026",
        "msg.total_decks_loaded": "Total decks loaded: {count}",
        "msg.recent_activity": "Recent activity:",
        "msg.no_recent_activity": "No recent deck activity.",
        "msg.progress_decks": "Processed {current}/{total} decks\u2026",
        "msg.collection_loaded": "Collection: {filename} ({count} entries)",
        "msg.collection_load_failed": "Collection load failed: {error}",
        "msg.collection_fetch_failed": "Collection fetch failed: {error}",
        "msg.deck_lists_load_failed": "Failed to load deck lists:\n{error}",
        # Deck stats panel
        "stats.no_deck": "No deck loaded.",
        "stats.col_cmc": "CMC",
        "stats.col_count": "Count",
        "stats.col_color": "Color",
        "stats.col_share": "Share",
        # Sideboard guide panel labels and buttons
        "guide.col_archetype": "Archetype",
        "guide.col_play_out": "Play: Out",
        "guide.col_play_in": "Play: In",
        "guide.col_draw_out": "Draw: Out",
        "guide.col_draw_in": "Draw: In",
        "guide.col_notes": "Notes",
        "guide.btn_add": "Add Entry",
        "guide.btn_edit": "Edit Entry",
        "guide.btn_remove": "Remove Entry",
        "guide.btn_exclusions": "Exclude Archetypes",
        "guide.btn_export": "Export CSV",
        "guide.btn_import": "Import CSV",
        "guide.exclusions_none": "Exclusions: \u2014",
        "guide.exclusions": "Exclusions: {exclusions}",
        # Sideboard guide handler dialogs and status messages
        "guide.dialog_title": "Sideboard Guide",
        "guide.select_edit": "Select an entry to edit.",
        "guide.select_remove": "Select an entry to remove.",
        "guide.exclude_prompt": "Select archetypes to exclude from the printed guide.",
        "guide.no_entries_export": "No guide entries to export.",
        "guide.export_success": "Sideboard guide exported successfully.",
        "guide.export_error": "Error exporting sideboard guide to CSV.",
        "guide.no_entries_import": "No valid guide entries found in CSV.",
        "guide.import_success": "Successfully imported {count} guide entries.",
        "guide.import_error": "Error importing sideboard guide from CSV.",
        "guide.export_dialog": "Export Sideboard Guide",
        "guide.import_dialog": "Import Sideboard Guide",
        "guide.import_options_title": "Import Options",
        "guide.enable_double_entries": "Enable double entries",
        "guide.btn_import_action": "Import",
        # Deck notes panel
        "notes.btn_save": "Save Notes",
        "notes.saved": "Deck notes saved.",
    },
    "pt-BR": {
        # App-level
        "app.status.ready": "Pronto",
        "app.status.language_changed": "Idioma alterado. Reinicie o app para aplicar por completo.",
        "app.status.selected_language": "Idioma selecionado: {language}",
        "app.title.main_frame": "Pesquisa e Montagem de Deck MTGO",
        "app.label.deck_data_source": "Fonte de decks:",
        "app.label.language": "Idioma:",
        "app.choice.source.both": "Ambos",
        "app.choice.source.mtggoldfish": "MTGGoldfish",
        "app.choice.source.mtgo": "MTGO.com",
        # Toolbar buttons
        "toolbar.opponent_tracker": "Rastreador de Oponente",
        "toolbar.timer_alert": "Alerta de Tempo",
        "toolbar.match_history": "Hist\u00f3rico de Partidas",
        "toolbar.metagame_analysis": "An\u00e1lise de Metagame",
        "toolbar.load_collection": "Carregar Cole\u00e7\u00e3o",
        "toolbar.download_card_images": "Baixar Imagens de Cartas",
        "toolbar.update_card_database": "Atualizar Banco de Cartas",
        # Deck action buttons
        "deck_actions.daily_average": "M\u00e9dia de Hoje",
        "deck_actions.copy": "Copiar",
        "deck_actions.save_deck": "Salvar Deck",
        # Research panel
        "research.format": "Formato",
        "research.search_hint": "Buscar arqu\u00e9tipos...",
        "research.reload_archetypes": "Recarregar Arqu\u00e9tipos",
        "research.loading_archetypes": "Carregando...",
        "research.failed_archetypes": "Falha ao carregar arqu\u00e9tipos.",
        "research.no_archetypes": "Nenhum arqu\u00e9tipo encontrado.",
        # Panel / static box labels
        "panel.deck_results": "Resultados de Deck",
        "panel.card_inspector": "Inspetor de Carta",
        "panel.deck_workspace": "\u00c1rea de Trabalho",
        # Notebook / tab labels
        "tab.research": "Pesquisa",
        "tab.builder": "Montagem",
        "tab.deck_tables": "Tabelas de Deck",
        "tab.mainboard": "Maindeck",
        "tab.sideboard": "Sideboard",
        "tab.stats": "Estat\u00edsticas",
        "tab.sideboard_guide": "Guia de Sideboard",
        "tab.deck_notes": "Notas de Deck",
        # Simple status messages
        "status.collection_not_loaded": "Invent\u00e1rio da cole\u00e7\u00e3o n\u00e3o carregado.",
        "status.select_archetype": "Selecione um arqu\u00e9tipo para ver os decks.",
        "status.loading_card_db_restore": "Carregando banco de cartas para restaurar deck salvo...",
        "status.deck_copied": "Deck copiado para a \u00e1rea de transfer\u00eancia.",
        "status.deck_saved": "Deck salvo com sucesso.",
        "status.loading": "Carregando\u2026",
        "status.loading_card_data_search": "Carregando dados de cartas\u2026 (busca ser\u00e1 executada automaticamente)",
        "status.downloading_decks": "Baixando decks\u2026",
        "status.card_db_downloaded": "Banco de imagens baixado, indexando impress\u00f5es\u2026",
        # Parametric status messages
        "status.archetypes_loaded": "Carregados {count} arqu\u00e9tipos para {format}.",
        "status.error": "Erro: {error}",
        "status.no_decks_for_archetype": "Nenhum deck para {archetype}.",
        "status.loading_deck": "Carregando deck {deck_name}\u2026",
        "status.decks_loaded": "Carregados {count} decks para {archetype}. Clique em um deck para carregar.",
        "status.deck_ready": "Deck pronto ({source}).",
        "status.error_loading_decks": "Erro ao carregar decks: {error}",
        "status.deck_download_failed": "Falha no download do deck: {error}",
        "status.daily_average_failed": "Falha na m\u00e9dia di\u00e1ria: {error}",
        # Dialog titles
        "dialog.copy_deck": "Copiar Deck",
        "dialog.save_deck": "Salvar Deck",
        "dialog.deck_saved": "Deck Salvo",
        "dialog.archetype_error": "Erro de Arqu\u00e9tipo",
        "dialog.deck_error": "Erro de Deck",
        "dialog.deck_download": "Download de Deck",
        "dialog.card_data_error": "Erro de Dados de Carta",
        "dialog.daily_average": "M\u00e9dia Di\u00e1ria",
        # Dialog prompts and message box text
        "msg.no_deck_to_copy": "Nenhum deck para copiar.",
        "msg.clipboard_error": "N\u00e3o foi poss\u00edvel acessar a \u00e1rea de transfer\u00eancia.",
        "msg.load_deck_first": "Carregue um deck primeiro.",
        "msg.deck_name_prompt": "Nome do deck:",
        "msg.deck_write_failed": "Falha ao salvar arquivo de deck:\n{error}",
        "msg.deck_saved_path": "Deck salvo em {path}",
        "msg.deck_saved_db_id": "\nID no banco de dados: {deck_id}",
        "msg.no_decks_found": "Nenhum deck encontrado.",
        "msg.failed_load_decks": "Falha ao carregar decks.",
        "msg.mana_value_numeric": "O valor de mana deve ser num\u00e9rico.",
        "msg.archetypes_load_failed": "N\u00e3o foi poss\u00edvel carregar arqu\u00e9tipos:\n{error}",
        "msg.deck_id_missing": "Identificador de deck ausente.",
        "msg.deck_download_failed": "Falha ao baixar deck:\n{error}",
        "msg.card_data_load_failed": "Falha ao carregar banco de cartas:\n{error}",
        "msg.daily_average_failed_body": "Falha ao calcular m\u00e9dia di\u00e1ria:\n{error}",
        "msg.no_deck_data": "{archetype}\n\nSem dados de deck dispon\u00edveis.",
        "msg.archetypes_loaded_hint": "Selecione um arqu\u00e9tipo para ver os decks.\nCarregados {count} arqu\u00e9tipos.",
        "msg.fetching_decks": "{archetype}\n\nBuscando resultados de deck\u2026",
        "msg.total_decks_loaded": "Total de decks carregados: {count}",
        "msg.recent_activity": "Atividade recente:",
        "msg.no_recent_activity": "Nenhuma atividade de deck recente.",
        "msg.progress_decks": "Processados {current}/{total} decks\u2026",
        "msg.collection_loaded": "Cole\u00e7\u00e3o: {filename} ({count} entradas)",
        "msg.collection_load_failed": "Falha ao carregar cole\u00e7\u00e3o: {error}",
        "msg.collection_fetch_failed": "Falha ao buscar cole\u00e7\u00e3o: {error}",
        "msg.deck_lists_load_failed": "Falha ao carregar listas de deck:\n{error}",
        # Deck stats panel
        "stats.no_deck": "Nenhum deck carregado.",
        "stats.col_cmc": "CMC",
        "stats.col_count": "Qtd",
        "stats.col_color": "Cor",
        "stats.col_share": "Participa\u00e7\u00e3o",
        # Sideboard guide panel labels and buttons
        "guide.col_archetype": "Arqu\u00e9tipo",
        "guide.col_play_out": "Joga: Sai",
        "guide.col_play_in": "Joga: Entra",
        "guide.col_draw_out": "Compra: Sai",
        "guide.col_draw_in": "Compra: Entra",
        "guide.col_notes": "Notas",
        "guide.btn_add": "Adicionar",
        "guide.btn_edit": "Editar",
        "guide.btn_remove": "Remover",
        "guide.btn_exclusions": "Excluir Arqu\u00e9tipos",
        "guide.btn_export": "Exportar CSV",
        "guide.btn_import": "Importar CSV",
        "guide.exclusions_none": "Exclus\u00f5es: \u2014",
        "guide.exclusions": "Exclus\u00f5es: {exclusions}",
        # Sideboard guide handler dialogs and status messages
        "guide.dialog_title": "Guia de Sideboard",
        "guide.select_edit": "Selecione uma entrada para editar.",
        "guide.select_remove": "Selecione uma entrada para remover.",
        "guide.exclude_prompt": "Selecione os arqu\u00e9tipos a excluir do guia impresso.",
        "guide.no_entries_export": "Nenhuma entrada para exportar.",
        "guide.export_success": "Guia de sideboard exportado com sucesso.",
        "guide.export_error": "Erro ao exportar guia de sideboard para CSV.",
        "guide.no_entries_import": "Nenhuma entrada v\u00e1lida encontrada no CSV.",
        "guide.import_success": "Importadas {count} entradas com sucesso.",
        "guide.import_error": "Erro ao importar guia de sideboard do CSV.",
        "guide.export_dialog": "Exportar Guia de Sideboard",
        "guide.import_dialog": "Importar Guia de Sideboard",
        "guide.import_options_title": "Op\u00e7\u00f5es de Importa\u00e7\u00e3o",
        "guide.enable_double_entries": "Permitir entradas duplicadas",
        "guide.btn_import_action": "Importar",
        # Deck notes panel
        "notes.btn_save": "Salvar Notas",
        "notes.saved": "Notas do deck salvas.",
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
