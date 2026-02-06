from utils.i18n import DEFAULT_LOCALE, MESSAGES, SUPPORTED_LOCALES, normalize_locale, translate


def test_normalize_locale_falls_back_to_default_for_unknown_values() -> None:
    assert normalize_locale("pt-BR") == "pt-BR"
    assert normalize_locale("en-US") == "en-US"
    assert normalize_locale("es-ES") == DEFAULT_LOCALE
    assert normalize_locale(None) == DEFAULT_LOCALE


def test_translate_returns_locale_string_and_falls_back_to_default() -> None:
    assert translate("pt-BR", "app.status.ready") == "Pronto"
    assert translate("es-ES", "app.status.ready") == "Ready"


def test_translate_returns_key_when_missing() -> None:
    assert translate("pt-BR", "missing.translation.key") == "missing.translation.key"


def test_translate_formats_params_when_present() -> None:
    assert (
        translate("pt-BR", "app.status.selected_language", language="Português (Brasil)")
        == "Idioma selecionado: Português (Brasil)"
    )


def test_core_ui_translation_keys_exist_for_all_supported_locales() -> None:
    required_keys = {
        "app.status.ready",
        "app.status.language_changed",
        "app.title.main_frame",
        "app.label.deck_data_source",
        "app.label.language",
        "toolbar.opponent_tracker",
        "toolbar.timer_alert",
        "toolbar.match_history",
        "toolbar.metagame_analysis",
        "toolbar.load_collection",
        "toolbar.download_card_images",
        "toolbar.update_card_database",
        "deck_actions.daily_average",
        "deck_actions.copy",
        "deck_actions.save_deck",
        "research.format",
        "research.search_hint",
        "research.reload_archetypes",
        "research.loading_archetypes",
        "research.failed_archetypes",
        "research.no_archetypes",
    }
    for locale in SUPPORTED_LOCALES:
        assert required_keys.issubset(set(MESSAGES[locale]))
