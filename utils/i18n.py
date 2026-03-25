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
        "toolbar.help": "Help (F1)",
        "toolbar.tooltip.opponent_tracker": "Detect your current MTGO opponent and look up their most-played archetypes",
        "toolbar.tooltip.timer_alert": "Set a countdown timer alert to warn you before round time runs out",
        "toolbar.tooltip.match_history": "Parse your MTGO GameLog files and view recent match results",
        "toolbar.tooltip.metagame_analysis": "Browse the format metagame breakdown and archetype share data",
        "deck_actions.daily_average": "Today's Average",
        "deck_actions.copy": "Copy",
        "deck_actions.load_deck": "Load Deck",
        "deck_actions.save_deck": "Save Deck",
        "deck_actions.tooltip.daily_average": "Build an averaged deck from today's tournament results",
        "deck_actions.tooltip.copy": "Copy the current deck list to your clipboard",
        "deck_actions.tooltip.load_deck": "Load a saved deck from file or database",
        "deck_actions.tooltip.save_deck": "Save the current deck",
        "research.format": "Format",
        "research.search_hint": "Search archetypes...",
        "research.reload_archetypes": "Reload Archetypes",
        "research.loading_archetypes": "Loading...",
        "research.failed_archetypes": "Failed to load archetypes.",
        "research.no_archetypes": "No archetypes found.",
        "research.switch_to_builder": "Deck Builder",
        "research.tooltip.format": "Select the format to research",
        "research.tooltip.search": "Filter the archetype list by name",
        "research.tooltip.archetypes": "Click an archetype to load its decklists",
        "research.tooltip.reload": "Refresh archetype data from MTGGoldfish",
        "tabs.mainboard": "Mainboard",
        "tabs.sideboard": "Sideboard",
        "tabs.sideboard_guide": "Sideboard Guide",
        "tabs.deck_notes": "Deck Notes",
        "tabs.tooltip.mainboard": "Your main deck (typically 60 cards)",
        "tabs.tooltip.sideboard": "Your sideboard (up to 15 cards)",
        "tabs.tooltip.sideboard_guide": "Matchup-by-matchup sideboard plan and notes",
        "tabs.tooltip.deck_notes": "Free-form notes attached to this deck",
        "app.label.deck_workspace": "Deck Workspace",
        "app.label.deck_results": "Deck Results",
        "app.label.card_inspector": "Card Inspector",
        "app.label.left_panel.research": "Research",
        "app.label.left_panel.builder": "Builder",
        "app.status.collection_not_loaded": "Collection inventory not loaded.",
        "app.status.select_archetype": "Select an archetype to view decks.",
        "deck_results.status.loaded_decks": "Loaded {count} decks for {archetype}. Click a deck to load it.",
        "deck_results.total_loaded": "Total decks loaded: {count}",
        "deck_results.recent_activity": "Recent activity:",
        "deck_results.no_activity": "No recent deck activity.",
        "deck_results.no_decks": "No decks found.",
        "deck_results.no_decks_for": "No decks for {archetype}.",
        "deck_results.failed_load": "Failed to load decks.",
        "app.status.card_db_loading": "Loading card database...",
        "app.status.card_db_loaded": "Card database loaded",
        "app.status.card_db_failed": "Card database load failed",
        "app.collection.not_found": "No collection found. Click \u2018Refresh Collection\u2019 to fetch from MTGO.",
        "app.research.archetypes_loaded": "Loaded {count} archetypes for {format}.",
        "app.research.select_archetype_loaded": "Select an archetype to view decks.\nLoaded {count} archetypes.",
        "builder.back_button": "Deck Research",
        "builder.back_button.tooltip": "Switch back to Deck Research mode",
        "builder.info": "Deck Builder: search MTG cards by property.",
        "builder.field.card_name": "Card Name",
        "builder.field.type_line": "Type Line",
        "builder.field.mana_cost": "Mana Cost",
        "builder.field.oracle_text": "Oracle Text",
        "builder.field.mana_value": "Mana Value Filter",
        "builder.filter.color_identity": "Color Identity Filter",
        "builder.filter.format": "Format",
        "builder.clear_filters": "Clear Filters",
        "builder.radar.use_filter": "Use Radar Filter",
        "builder.radar.open": "Open Radar...",
        "builder.add_to_main": "+ Mainboard",
        "builder.add_to_side": "+ Sideboard",
        "builder.status.results": "Results update automatically as you type.",
        "builder.col.name": "Name",
        "builder.col.mana_cost": "Mana Cost",
        "builder.hint.card_name": "e.g. Ragavan",
        "builder.hint.type_line": "Artifact Creature",
        "builder.hint.mana_cost": "Curly braces like {1}{G} or shorthand (e.g. GGG)",
        "builder.label.match": "Match",
        "builder.check.exact_symbols": "Exact symbols",
        "builder.btn.adv_filters_show": "+ Advanced Filters",
        "builder.btn.adv_filters_hide": "- Advanced Filters",
        "builder.hint.oracle_text": "Keywords or abilities",
        "builder.hint.mana_value": "e.g. 3",
        "builder.format.any": "Any",
        "guide.col.archetype": "Archetype",
        "guide.col.play_out": "Play: Out",
        "guide.col.play_in": "Play: In",
        "guide.col.draw_out": "Draw: Out",
        "guide.col.draw_in": "Draw: In",
        "guide.col.notes": "Notes",
        "guide.btn.add": "Add",
        "guide.btn.edit": "Edit",
        "guide.btn.delete": "Delete",
        "guide.btn.exclusions": "Exclusions",
        "guide.btn.export": "Export",
        "guide.btn.import": "Import",
        "guide.btn.flex_slots": "Flex Slots",
        "guide.btn.pin": "Pin for Tracker",
        "guide.btn.pinned": "Pinned \u2713",
        "guide.btn.cta": "Add your first matchup",
        "guide.empty": "No matchup notes yet.\nClick \u201cAdd\u201d to create a sideboard guide entry.",
        "guide.label.exclusions": "Exclusions",
        "guide.tooltip.flex_slots": (
            "Mark mainboard cards as flex slots. Flex slots are highlighted in the Out selectors "
            "when creating guide entries, making it easier to identify cards to side out."
        ),
        "guide.dialog.archetype_matchup": "Archetype/Matchup",
        "guide.dialog.cancel": "Cancel",
        "guide.dialog.on_the_play": "ON THE PLAY",
        "guide.dialog.on_the_draw": "ON THE DRAW",
        "guide.dialog.out_from_main": "Out (from Mainboard)",
        "guide.dialog.in_from_side": "In (from Sideboard)",
        "guide.dialog.notes_label": "Notes (Optional)",
        "guide.dialog.notes_hint": "Strategy notes for this matchup",
        "guide.dialog.double_entries": "Enable double entries",
        "guide.dialog.save_continue": "Save & Continue",
        "guide.selector.cards_selected": "{count} cards selected",
        "radar.label.no_radar": "No radar loaded.",
        "radar.btn.export": "Export as Decklist",
        "radar.btn.use_search": "Use for Search",
        "radar.box.mainboard": "Mainboard Radar",
        "radar.box.sideboard": "Sideboard Radar",
        "radar.col.card": "Card",
        "radar.col.inclusion": "Inclusion %",
        "radar.col.expected": "Expected Copies",
        "radar.col.avg": "Avg Copies",
        "radar.col.max": "Max",
        "radar.dialog.select_archetype": "Select Archetype:",
        "radar.dialog.generate": "Generate Radar",
        "radar.btn.cancel": "Cancel",
        "radar.btn.close": "Close",
        "notes.btn.add": "+ Add Note",
        "notes.btn.save": "Save Notes",
        "notes.empty": "No deck notes yet, click \u201cAdd\u201d to create a deck note entry.",
        "notes.saved": "Deck notes saved.",
        "notes.type.general": "General",
        "notes.type.matchup": "Matchup",
        "notes.type.sideboard_plan": "Sideboard Plan",
        "notes.type.custom": "Custom",
        "tracker.label.not_detected": "Opponent not detected",
        "tracker.label.watching": "Watching for MTGO match windows\u2026",
        "tracker.btn.refresh": "Refresh",
        "tracker.btn.calculator": "Calculator",
        "tracker.btn.guide": "Guide",
        "tracker.btn.close": "Close",
        "tracker.status.no_active_match": "No active match detected",
        "tracker.status.waiting": "Waiting for MTGO match window\u2026",
        "metagame.chart.no_data": "No data available for selected period",
        "metagame.label.format": "Format:",
        "metagame.label.time_window": "Time Window (days):",
        "metagame.label.starting_from": "Starting from day:",
        "metagame.label.changes": "Metagame Changes",
        "metagame.btn.refresh": "Refresh Data",
        "metagame.loaded": "Loaded {count} archetypes",
        "metagame.period.last_days": "Last {count} day(s)",
        "metagame.period.days_ago": "{count} day(s) ago",
        "metagame.period.range_days_ago": "{start}-{end} days ago",
        "metagame.changes.no_data": "No comparison data available",
        "metagame.changes.vs_period": "Changes vs {period}",
        "metagame.changes.none": "No significant changes",
        "metagame.status.fetching": "Fetching metagame data...",
        "metagame.status.error": "Unable to load metagame data:\n{message}",
        "match.metrics.title": "Win-Rate Metrics",
        "match.metrics.abs_match_rate": "Absolute Match Win Rate",
        "match.metrics.abs_game_rate": "Absolute Game Win Rate",
        "match.metrics.filtered_match_rate": "Match Win Rate (filtered)",
        "match.metrics.filtered_game_rate": "Game Win Rate (filtered)",
        "match.metrics.mulligan_rate": "Mulligan Rate",
        "match.metrics.avg_mulligans": "Avg Mulligans/Match",
        "match.metrics.opp_match_rate": "Vs. Opponent Match Win Rate",
        "match.metrics.opp_mull_rate": "Vs. Opponent Mull Rate",
        "match.filter.start": "Start (YYYY-MM-DD):",
        "match.filter.end": "End (YYYY-MM-DD):",
        "match.filter.apply": "Apply Date Filter",
        "match.col.players": "Players (Archetypes)",
        "match.col.result": "Result",
        "match.col.mulligans": "Mulligans",
        "match.col.date": "Date",
        "match.btn.refresh": "Refresh",
        "match.status.loading": "Loading all match history...",
        "match.status.parsing": "Parsing {current}/{total} matches...",
        "match.status.loaded": "Loaded {count} matches",
        "match.status.failed": "Failed to load match history.",
        "match.status.no_data": "No match data available.",
        "match.status.invalid_date": "Invalid date format",
        "match.result.won": "Won",
        "match.result.lost": "Lost",
        "timer.section.thresholds": "Alert Thresholds",
        "timer.section.challenge": "Active Challenge Timer",
        "timer.label.sound": "Alert Sound:",
        "timer.label.check_interval": "Check interval (ms):",
        "timer.label.repeat_interval": "Repeat interval (seconds):",
        "timer.check.start_alert": "Alert when timer starts counting down",
        "timer.check.repeat_alarm": "Repeat alarm at interval",
        "timer.btn.start": "Start Monitoring",
        "timer.btn.stop": "Stop",
        "timer.btn.test": "Test Alert",
        "timer.no_challenge": "No active challenge timer detected.",
        "timer.configure": "Configure thresholds and click Start to begin monitoring.",
        "tutorial.dialog_title": "MTGO Tools \u2014 Quick Tour",
        "tutorial.btn.skip": "Skip Tour",
        "tutorial.btn.back": "< Back",
        "tutorial.btn.next": "Next >",
        "tutorial.btn.finish": "Finish",
        "tutorial.step0.title": "Welcome to MTGO Tools",
        "tutorial.step0.body": (
            "MTGO Tools helps you research the competitive metagame, build and edit decks, "
            "track opponents, and manage your MTGO collection \u2014 all in one desktop app.\n\n"
            "This short tour covers the main features. You can revisit it any time from "
            "Settings \u2192 Show Tutorial."
        ),
        "tutorial.step1.title": "Metagame Research",
        "tutorial.step1.body": (
            "The left panel is your metagame research hub.\n\n"
            "\u2022  Choose a format (Modern, Legacy, \u2026) from the dropdown.\n"
            "\u2022  Type in the search box to filter archetypes by name.\n"
            "\u2022  Click an archetype to load its decklists in the Deck Results panel.\n"
            "\u2022  Use \u201cReload Archetypes\u201d to refresh data from MTGGoldfish."
        ),
        "tutorial.step2.title": "Deck Workspace",
        "tutorial.step2.body": (
            "The centre area shows the currently loaded deck.\n\n"
            "\u2022  Mainboard \u2014 your 60-card main deck.\n"
            "\u2022  Sideboard \u2014 your 15-card sideboard.\n"
            "\u2022  Hover over or click a card row to inspect it in the Card Inspector "
            "on the right.\n"
            "\u2022  Use the + / \u2212 controls to edit counts when building your own deck."
        ),
        "tutorial.step3.title": "Toolbar Tools",
        "tutorial.step3.body": (
            "The toolbar at the top of the right panel provides quick access to:\n\n"
            "\u2022  Opponent Tracker \u2014 detects the opponent from your MTGO window title "
            "and looks up their most-played archetypes.\n"
            "\u2022  Timer Alert \u2014 configurable countdown to warn you before time runs out "
            "in a round.\n"
            "\u2022  Match History \u2014 parses your MTGO GameLog files and shows recent results.\n"
            "\u2022  Metagame Analysis \u2014 a top-level breakdown of the current format."
        ),
        "tutorial.step4.title": "Deck Builder",
        "tutorial.step4.body": (
            "Switch the left panel to Builder mode to search for cards and craft your own deck.\n\n"
            "\u2022  Type a card name or keyword in the search box.\n"
            "\u2022  Click a result to preview it in the Card Inspector.\n"
            "\u2022  Use \u201cAdd to Main\u201d or \u201cAdd to Side\u201d to add it to your deck.\n"
            "\u2022  Open the Mana Keyboard for quick mana-cost symbol input.\n"
            "\u2022  Use \u201cCopy\u201d to copy the deck list to your clipboard."
        ),
        "tutorial.step5.title": "Sideboard Guide",
        "tutorial.step5.body": (
            "The Sideboard Guide tab lets you record matchup-by-matchup notes.\n\n"
            "\u2022  Add an entry for each archetype you face.\n"
            "\u2022  Record cards to bring IN and take OUT for each matchup.\n"
            "\u2022  Mark flex slots \u2014 cards whose count varies by matchup.\n"
            "\u2022  Pin the guide to keep it visible while reviewing other tabs.\n"
            "\u2022  Export or import as CSV to share guides with teammates."
        ),
        "tutorial.step6.title": "You\u2019re All Set!",
        "tutorial.step6.body": (
            "That\u2019s the quick tour of MTGO Tools.\n\n"
            "A few more tips:\n"
            "\u2022  Use the \u2699 Settings menu to load your MTGO collection, download card "
            "images, update the card database, or change the language.\n"
            "\u2022  Deck Notes let you keep free-form notes attached to any deck.\n"
            "\u2022  Session state (current deck, format, window size) is saved automatically.\n\n"
            "Good luck in your matches!"
        ),
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
        "toolbar.help": "Ajuda (F1)",
        "toolbar.tooltip.opponent_tracker": "Detecta seu oponente atual no MTGO e busca os arquétipos mais jogados por ele",
        "toolbar.tooltip.timer_alert": "Define um alerta de contagem regressiva antes do tempo da rodada acabar",
        "toolbar.tooltip.match_history": "Analisa seus arquivos GameLog do MTGO e exibe resultados recentes",
        "toolbar.tooltip.metagame_analysis": "Veja a distribuição do metagame e a participação de cada arquétipo no formato",
        "deck_actions.daily_average": "Média de Hoje",
        "deck_actions.copy": "Copiar",
        "deck_actions.load_deck": "Carregar Deck",
        "deck_actions.save_deck": "Salvar Deck",
        "deck_actions.tooltip.daily_average": "Monta um deck com a média dos torneios de hoje",
        "deck_actions.tooltip.copy": "Copia a lista do deck atual para a área de transferência",
        "deck_actions.tooltip.load_deck": "Carrega um deck salvo de arquivo ou banco de dados",
        "deck_actions.tooltip.save_deck": "Salva o deck atual",
        "research.format": "Formato",
        "research.search_hint": "Buscar arquétipos...",
        "research.reload_archetypes": "Recarregar Arquétipos",
        "research.loading_archetypes": "Carregando...",
        "research.failed_archetypes": "Falha ao carregar arquétipos.",
        "research.no_archetypes": "Nenhum arquétipo encontrado.",
        "research.switch_to_builder": "Montador de Deck",
        "research.tooltip.format": "Selecione o formato para pesquisar",
        "research.tooltip.search": "Filtre a lista de arquétipos por nome",
        "research.tooltip.archetypes": "Clique em um arquétipo para carregar seus decklists",
        "research.tooltip.reload": "Atualiza os dados de arquétipos do MTGGoldfish",
        "tabs.mainboard": "Principal",
        "tabs.sideboard": "Sideboard",
        "tabs.sideboard_guide": "Guia de Sideboard",
        "tabs.deck_notes": "Notas de Deck",
        "tabs.tooltip.mainboard": "Seu deck principal (geralmente 60 cartas)",
        "tabs.tooltip.sideboard": "Seu sideboard (até 15 cartas)",
        "tabs.tooltip.sideboard_guide": "Plano de sideboard e notas por matchup",
        "tabs.tooltip.deck_notes": "Notas em texto livre para este deck",
        "app.label.deck_workspace": "Área de Trabalho",
        "app.label.deck_results": "Resultados de Deck",
        "app.label.card_inspector": "Inspetor de Cartas",
        "app.label.left_panel.research": "Pesquisa",
        "app.label.left_panel.builder": "Montador",
        "app.status.collection_not_loaded": "Inventário de coleção não carregado.",
        "app.status.select_archetype": "Selecione um arquétipo para ver os decks.",
        "deck_results.status.loaded_decks": "Carregados {count} decks para {archetype}. Clique em um deck para carregá-lo.",
        "deck_results.total_loaded": "Total de decks carregados: {count}",
        "deck_results.recent_activity": "Atividade recente:",
        "deck_results.no_activity": "Nenhuma atividade recente de decks.",
        "deck_results.no_decks": "Nenhum deck encontrado.",
        "deck_results.no_decks_for": "Nenhum deck para {archetype}.",
        "deck_results.failed_load": "Falha ao carregar decks.",
        "app.status.card_db_loading": "Carregando banco de dados de cartas...",
        "app.status.card_db_loaded": "Banco de dados de cartas carregado",
        "app.status.card_db_failed": "Falha ao carregar banco de dados de cartas",
        "app.collection.not_found": "Nenhuma coleção encontrada. Clique em \u2018Atualizar Coleção\u2019 para buscar do MTGO.",
        "app.research.archetypes_loaded": "Carregados {count} arquétipos para {format}.",
        "app.research.select_archetype_loaded": "Selecione um arquétipo para ver os decks.\nCarregados {count} arquétipos.",
        "builder.back_button": "Pesquisa de Deck",
        "builder.back_button.tooltip": "Voltar ao modo de Pesquisa de Deck",
        "builder.info": "Montador de Deck",
        "builder.field.card_name": "Nome da Carta",
        "builder.field.type_line": "Tipo",
        "builder.field.mana_cost": "Custo de Mana",
        "builder.field.oracle_text": "Texto",
        "builder.field.mana_value": "Valor de Mana",
        "builder.filter.color_identity": "Identidade de Cor",
        "builder.filter.format": "Formato",
        "builder.clear_filters": "Limpar Filtros",
        "builder.radar.use_filter": "Usar Filtro de Radar",
        "builder.radar.open": "Abrir Radar...",
        "builder.add_to_main": "+ Principal",
        "builder.add_to_side": "+ Sideboard",
        "builder.status.results": "Os resultados atualizam automaticamente enquanto você digita.",
        "builder.col.name": "Nome",
        "builder.col.mana_cost": "Custo de Mana",
        "builder.hint.card_name": "ex.: Ragavan",
        "builder.hint.type_line": "Criatura Artefato",
        "builder.hint.mana_cost": "Chaves como {1}{V} ou atalho (ex.: VVV)",
        "builder.label.match": "Combinar",
        "builder.check.exact_symbols": "Símbolos exatos",
        "builder.btn.adv_filters_show": "+ Filtros Avançados",
        "builder.btn.adv_filters_hide": "- Filtros Avançados",
        "builder.hint.oracle_text": "Palavras-chave ou habilidades",
        "builder.hint.mana_value": "ex.: 3",
        "builder.format.any": "Qualquer",
        "guide.col.archetype": "Arquétipo",
        "guide.col.play_out": "Jogar: Sai",
        "guide.col.play_in": "Jogar: Entra",
        "guide.col.draw_out": "Comprar: Sai",
        "guide.col.draw_in": "Comprar: Entra",
        "guide.col.notes": "Notas",
        "guide.btn.add": "Adicionar",
        "guide.btn.edit": "Editar",
        "guide.btn.delete": "Excluir",
        "guide.btn.exclusions": "Exclusões",
        "guide.btn.export": "Exportar",
        "guide.btn.import": "Importar",
        "guide.btn.flex_slots": "Flex Slots",
        "guide.btn.pin": "Rastrear",
        "guide.btn.pinned": "Fixado \u2713",
        "guide.btn.cta": "Adicionar primeiro matchup",
        "guide.empty": "Nenhuma nota de matchup ainda.\nClique em \u201cAdicionar\u201d para criar uma entrada.",
        "guide.label.exclusions": "Exclusões",
        "guide.tooltip.flex_slots": (
            "Marque cartas do mainboard como flex slots. Flex slots são destacados nos seletores de saída "
            "ao criar entradas de guia, facilitando a identificação das cartas a serem tiradas."
        ),
        "guide.dialog.archetype_matchup": "Arquétipo/Matchup",
        "guide.dialog.cancel": "Cancelar",
        "guide.dialog.on_the_play": "NO PRIMEIRO TURNO",
        "guide.dialog.on_the_draw": "NO SEGUNDO TURNO",
        "guide.dialog.out_from_main": "Saindo (do Mainboard)",
        "guide.dialog.in_from_side": "Entrando (do Sideboard)",
        "guide.dialog.notes_label": "Notas (Opcional)",
        "guide.dialog.notes_hint": "Notas de estratégia para este matchup",
        "guide.dialog.double_entries": "Habilitar entradas duplas",
        "guide.dialog.save_continue": "Salvar e Continuar",
        "guide.selector.cards_selected": "{count} cartas selecionadas",
        "radar.label.no_radar": "Nenhum radar carregado.",
        "radar.btn.export": "Exportar como Decklist",
        "radar.btn.use_search": "Usar na Pesquisa",
        "radar.box.mainboard": "Radar do Mainboard",
        "radar.box.sideboard": "Radar do Sideboard",
        "radar.col.card": "Carta",
        "radar.col.inclusion": "% Inclusão",
        "radar.col.expected": "Cópias Esperadas",
        "radar.col.avg": "Cópias Médias",
        "radar.col.max": "Máx",
        "radar.dialog.select_archetype": "Selecionar Arquétipo:",
        "radar.dialog.generate": "Gerar Radar",
        "radar.btn.cancel": "Cancelar",
        "radar.btn.close": "Fechar",
        "notes.btn.add": "+ Adicionar Nota",
        "notes.btn.save": "Salvar Notas",
        "notes.empty": "Nenhuma nota de deck ainda, clique em \u201cAdicionar\u201d para criar uma nota.",
        "notes.saved": "Notas de deck salvas.",
        "notes.type.general": "Geral",
        "notes.type.matchup": "Matchup",
        "notes.type.sideboard_plan": "Plano de Sideboard",
        "notes.type.custom": "Personalizado",
        "tracker.label.not_detected": "Oponente não detectado",
        "tracker.label.watching": "Monitorando janelas de partida MTGO\u2026",
        "tracker.btn.refresh": "Atualizar",
        "tracker.btn.calculator": "Calculadora",
        "tracker.btn.guide": "Guia",
        "tracker.btn.close": "Fechar",
        "tracker.status.no_active_match": "Nenhuma partida ativa detectada",
        "tracker.status.waiting": "Aguardando janela de partida MTGO\u2026",
        "metagame.chart.no_data": "Sem dados disponíveis para o período selecionado",
        "metagame.label.format": "Formato:",
        "metagame.label.time_window": "Janela de Tempo (dias):",
        "metagame.label.starting_from": "A partir do dia:",
        "metagame.label.changes": "Mudanças de Metagame",
        "metagame.btn.refresh": "Atualizar Dados",
        "metagame.loaded": "Carregados {count} arquétipos",
        "metagame.period.last_days": "Últimos {count} dia(s)",
        "metagame.period.days_ago": "há {count} dia(s)",
        "metagame.period.range_days_ago": "há {start}-{end} dias",
        "metagame.changes.no_data": "Sem dados de comparação disponíveis",
        "metagame.changes.vs_period": "Mudanças em relação a {period}",
        "metagame.changes.none": "Nenhuma mudança significativa",
        "metagame.status.fetching": "Buscando dados de metagame...",
        "metagame.status.error": "Não foi possível carregar dados de metagame:\n{message}",
        "match.metrics.title": "Métricas de Taxa de Vitória",
        "match.metrics.abs_match_rate": "Taxa Absoluta de Vitórias em Partidas",
        "match.metrics.abs_game_rate": "Taxa Absoluta de Vitórias em Jogos",
        "match.metrics.filtered_match_rate": "Taxa de Vitórias em Partidas (filtrado)",
        "match.metrics.filtered_game_rate": "Taxa de Vitórias em Jogos (filtrado)",
        "match.metrics.mulligan_rate": "Taxa de Mulligans",
        "match.metrics.avg_mulligans": "Média de Mulligans/Partida",
        "match.metrics.opp_match_rate": "Taxa de Vitórias vs. Oponente",
        "match.metrics.opp_mull_rate": "Taxa de Mulligans vs. Oponente",
        "match.filter.start": "Início (AAAA-MM-DD):",
        "match.filter.end": "Fim (AAAA-MM-DD):",
        "match.filter.apply": "Aplicar Filtro de Data",
        "match.col.players": "Jogadores (Arquétipos)",
        "match.col.result": "Resultado",
        "match.col.mulligans": "Mulligans",
        "match.col.date": "Data",
        "match.btn.refresh": "Atualizar",
        "match.status.loading": "Carregando todo o histórico de partidas...",
        "match.status.parsing": "Processando {current}/{total} partidas...",
        "match.status.loaded": "Carregadas {count} partidas",
        "match.status.failed": "Falha ao carregar histórico de partidas.",
        "match.status.no_data": "Nenhum dado de partida disponível.",
        "match.status.invalid_date": "Formato de data inválido",
        "match.result.won": "Vitória",
        "match.result.lost": "Derrota",
        "timer.section.thresholds": "Limites de Alerta",
        "timer.section.challenge": "Cronômetro de Desafio Ativo",
        "timer.label.sound": "Som do Alerta:",
        "timer.label.check_interval": "Intervalo de verificação (ms):",
        "timer.label.repeat_interval": "Intervalo de repetição (segundos):",
        "timer.check.start_alert": "Alertar quando o cronômetro iniciar contagem regressiva",
        "timer.check.repeat_alarm": "Repetir alarme no intervalo",
        "timer.btn.start": "Iniciar Monitoramento",
        "timer.btn.stop": "Parar",
        "timer.btn.test": "Testar Alerta",
        "timer.no_challenge": "Nenhum cronômetro de desafio ativo detectado.",
        "timer.configure": "Configure os limites e clique em Iniciar para começar a monitorar.",
        "tutorial.dialog_title": "MTGO Tools \u2014 Tour R\u00e1pido",
        "tutorial.btn.skip": "Pular Tour",
        "tutorial.btn.back": "< Voltar",
        "tutorial.btn.next": "Pr\u00f3ximo >",
        "tutorial.btn.finish": "Concluir",
        "tutorial.step0.title": "Bem-vindo ao MTGO Tools",
        "tutorial.step0.body": (
            "O MTGO Tools ajuda voc\u00ea a pesquisar o metagame competitivo, montar e editar decks, "
            "rastrear oponentes e gerenciar sua cole\u00e7\u00e3o MTGO \u2014 tudo em um \u00fanico aplicativo de desktop.\n\n"
            "Este pequeno tour apresenta os principais recursos. Voc\u00ea pode revisit\u00e1-lo a qualquer momento em "
            "Configura\u00e7\u00f5es \u2192 Mostrar Tutorial."
        ),
        "tutorial.step1.title": "Pesquisa de Metagame",
        "tutorial.step1.body": (
            "O painel esquerdo \u00e9 seu centro de pesquisa de metagame.\n\n"
            "\u2022  Escolha um formato (Modern, Legacy, \u2026) no menu suspenso.\n"
            "\u2022  Digite na caixa de busca para filtrar arqu\u00e9tipos por nome.\n"
            "\u2022  Clique em um arqu\u00e9tipo para carregar seus decklists no painel de Resultados.\n"
            "\u2022  Use \u201cRecarregar Arqu\u00e9tipos\u201d para atualizar os dados do MTGGoldfish."
        ),
        "tutorial.step2.title": "\u00c1rea de Deck",
        "tutorial.step2.body": (
            "A \u00e1rea central mostra o deck carregado atualmente.\n\n"
            "\u2022  Principal \u2014 seu deck principal de 60 cartas.\n"
            "\u2022  Sideboard \u2014 seu sideboard de 15 cartas.\n"
            "\u2022  Passe o mouse ou clique em uma linha de carta para inspecion\u00e1-la no Inspetor de Cartas \u00e0 direita.\n"
            "\u2022  Use os controles + / \u2212 para editar quantidades ao montar seu pr\u00f3prio deck."
        ),
        "tutorial.step3.title": "Ferramentas da Barra",
        "tutorial.step3.body": (
            "A barra de ferramentas no topo do painel direito oferece acesso r\u00e1pido a:\n\n"
            "\u2022  Rastreador de Oponente \u2014 detecta o oponente pelo t\u00edtulo da janela do MTGO "
            "e busca os arqu\u00e9tipos mais jogados por ele.\n"
            "\u2022  Alerta de Tempo \u2014 contagem regressiva configur\u00e1vel para avisar antes do tempo acabar na rodada.\n"
            "\u2022  Hist\u00f3rico de Partidas \u2014 analisa seus arquivos GameLog do MTGO e mostra resultados recentes.\n"
            "\u2022  An\u00e1lise de Metagame \u2014 vis\u00e3o geral do formato atual."
        ),
        "tutorial.step4.title": "Montador de Deck",
        "tutorial.step4.body": (
            "Alterne o painel esquerdo para o modo Montador para buscar cartas e criar seu pr\u00f3prio deck.\n\n"
            "\u2022  Digite o nome de uma carta ou palavra-chave na caixa de busca.\n"
            "\u2022  Clique em um resultado para visualiz\u00e1-lo no Inspetor de Cartas.\n"
            "\u2022  Use \u201cAdicionar ao Principal\u201d ou \u201cAdicionar ao Sideboard\u201d para adicion\u00e1-la ao deck.\n"
            "\u2022  Abra o Teclado de Mana para inserir rapidamente s\u00edmbolos de custo de mana.\n"
            "\u2022  Use \u201cCopiar\u201d para copiar a lista de deck para a \u00e1rea de transfer\u00eancia."
        ),
        "tutorial.step5.title": "Guia de Sideboard",
        "tutorial.step5.body": (
            "A aba Guia de Sideboard permite registrar notas por matchup.\n\n"
            "\u2022  Adicione uma entrada para cada arqu\u00e9tipo que voc\u00ea enfrenta.\n"
            "\u2022  Registre as cartas para ENTRAR e SAIR em cada matchup.\n"
            "\u2022  Marque as flex slots \u2014 cartas cuja quantidade varia por matchup.\n"
            "\u2022  Fixe o guia para mant\u00ea-lo vis\u00edvel enquanto revisa outras abas.\n"
            "\u2022  Exporte ou importe como CSV para compartilhar guias com colegas de equipe."
        ),
        "tutorial.step6.title": "Voc\u00ea Est\u00e1 Pronto!",
        "tutorial.step6.body": (
            "Esse foi o tour r\u00e1pido do MTGO Tools.\n\n"
            "Mais algumas dicas:\n"
            "\u2022  Use o menu \u2699 Configura\u00e7\u00f5es para carregar sua cole\u00e7\u00e3o MTGO, baixar imagens de cartas, "
            "atualizar o banco de dados de cartas ou mudar o idioma.\n"
            "\u2022  Notas de Deck permitem manter anota\u00e7\u00f5es em texto livre vinculadas a qualquer deck.\n"
            "\u2022  O estado da sess\u00e3o (deck atual, formato, tamanho da janela) \u00e9 salvo automaticamente.\n\n"
            "Boa sorte nas suas partidas!"
        ),
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
