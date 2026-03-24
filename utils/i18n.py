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
        "research.switch_to_builder": "Deck Builder",
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
        "research.switch_to_builder": "Montador de Deck",
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
