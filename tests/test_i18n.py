from utils.i18n import DEFAULT_LOCALE, normalize_locale, translate


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
