import pytest

from widgets.mana_icon_service import ManaIconFactory, normalize_mana_query, tokenize_mana_symbols

wx = pytest.importorskip("wx")


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> ManaIconFactory:
    instance = ManaIconFactory(icon_size=12)
    monkeypatch.setattr(
        instance,
        "_color_map",
        {
            "w": (1, 1, 1),
            "u": (2, 2, 2),
            "b": (3, 3, 3),
            "r": (4, 4, 4),
            "g": (5, 5, 5),
            "c": (6, 6, 6),
        },
        raising=False,
    )
    return instance


def test_normalize_mana_query_wraps_unbraced_tokens() -> None:
    assert normalize_mana_query("2wu") == "{2}{W}{U}"
    assert normalize_mana_query("w/u b") == "{W/U}{B}"
    assert normalize_mana_query("∞rg") == "{∞}{R}{G}"


def test_normalize_mana_query_preserves_existing_braces() -> None:
    assert normalize_mana_query(" {T}{G/U} ") == "{T}{G/U}"
    assert normalize_mana_query("{x}{y}{z}") == "{x}{y}{z}"


def test_normalize_symbol_applies_aliases(factory: ManaIconFactory) -> None:
    assert factory._normalize_symbol("{W/U}") == "wu"
    assert factory._normalize_symbol("1/2") == "1-2"
    assert factory._normalize_symbol("∞") == "infinity"
    assert factory._normalize_symbol("2/U") == "2u"


def test_hybrid_components_identify_pairs(factory: ManaIconFactory) -> None:
    assert factory._hybrid_components("wu") == ["w", "u"]
    assert factory._hybrid_components("2g") == ["c", "g"]
    assert factory._hybrid_components("pw") is None


def test_color_for_key_uses_fallbacks(factory: ManaIconFactory) -> None:
    assert factory._color_for_key(None) == factory.FALLBACK_COLORS["multicolor"]
    assert factory._color_for_key("7") == (6, 6, 6)
    assert factory._color_for_key("w-u") == (1, 1, 1)
    assert factory._color_for_key("2w") == (1, 1, 1)


def test_tokenize_mana_symbols_uppercases_tokens() -> None:
    assert tokenize_mana_symbols("{g}{w/u}{2g}") == ["G", "W/U", "2G"]
    assert tokenize_mana_symbols("") == []
