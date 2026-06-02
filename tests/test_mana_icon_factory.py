import pytest

from widgets.mana_icon_factory import ManaIconFactory, normalize_mana_query, tokenize_mana_symbols

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


def test_normalize_symbol_covers_remaining_aliases(factory: ManaIconFactory) -> None:
    assert factory._normalize_symbol("{T}") == "tap"
    assert factory._normalize_symbol("snow") == "s"
    assert factory._normalize_symbol("½") == "1-2"
    assert factory._normalize_symbol("  ") is None


def test_hybrid_components_identify_pairs(factory: ManaIconFactory) -> None:
    assert factory._hybrid_components("wu") == ["w", "u"]
    assert factory._hybrid_components("2g") == ["c", "g"]
    assert factory._hybrid_components("pw") is None


def test_color_for_key_uses_fallbacks(factory: ManaIconFactory) -> None:
    assert factory._color_for_key(None) == factory.FALLBACK_COLORS["multicolor"]
    assert factory._color_for_key("7") == (6, 6, 6)
    assert factory._color_for_key("w-u") == (1, 1, 1)
    assert factory._color_for_key("2w") == (1, 1, 1)


def test_color_for_key_covers_remaining_branches(factory: ManaIconFactory) -> None:
    # x/y/z alias to the colourless ('c') colour.
    assert factory._color_for_key("x") == factory._color_map["c"]
    # A key present in FALLBACK_COLORS but absent from the overridden _color_map.
    assert factory._color_for_key("multicolor") == factory.FALLBACK_COLORS["multicolor"]
    # Unrecognized key falls through to the terminal multicolor fallback.
    assert factory._color_for_key("pw") == factory.FALLBACK_COLORS["multicolor"]


def test_tokenize_mana_symbols_uppercases_tokens() -> None:
    assert tokenize_mana_symbols("{g}{w/u}{2g}") == ["G", "W/U", "2G"]
    assert tokenize_mana_symbols("") == []


@pytest.fixture(scope="module")
def wx_app():
    """A wx.App is required for bitmap/GraphicsContext rendering."""
    app = wx.App()
    yield app
    app.Destroy()


@pytest.fixture
def render_factory(wx_app) -> ManaIconFactory:
    return ManaIconFactory(icon_size=16)


def test_bitmap_for_symbol_renders_expected_size(render_factory: ManaIconFactory) -> None:
    braced = render_factory.bitmap_for_symbol("{W}")
    assert braced is not None
    assert braced.IsOk()
    assert (braced.GetWidth(), braced.GetHeight()) == (16, 16)
    # Unbraced form resolves to the same token/cache entry.
    bare = render_factory.bitmap_for_symbol("W")
    assert bare is braced


def test_bitmap_for_symbol_hires_is_larger_than_final(render_factory: ManaIconFactory) -> None:
    hires = render_factory.bitmap_for_symbol_hires("{U}")
    assert hires is not None and hires.IsOk()
    assert hires.GetHeight() > 16  # rendered at _RENDER_SCALE before downscale


def test_png_path_for_symbol_writes_and_caches(render_factory: ManaIconFactory) -> None:
    path = render_factory.png_path_for_symbol("{B}")
    assert path is not None
    assert path.exists()
    assert path.suffix == ".png"
    # Second call returns the same cached path without rewriting.
    assert render_factory.png_path_for_symbol("{B}") == path


def test_png_path_for_symbol_honours_height(render_factory: ManaIconFactory) -> None:
    path = render_factory.png_path_for_symbol("{R}", height=24)
    assert path is not None and path.exists()
    img = wx.Image(str(path), wx.BITMAP_TYPE_PNG)
    assert img.GetHeight() == 24


def test_png_path_for_symbol_empty_token_is_none(render_factory: ManaIconFactory) -> None:
    assert render_factory.png_path_for_symbol("") is None
    assert render_factory.png_path_for_symbol("{}") is None


def test_bitmap_for_cost_composes_and_caches(render_factory: ManaIconFactory) -> None:
    assert render_factory.bitmap_for_cost("") is None
    composed = render_factory.bitmap_for_cost("{2}{W}{U}")
    assert composed is not None and composed.IsOk()
    assert composed.GetHeight() == 16
    assert composed.GetWidth() > 16  # multiple icons laid out horizontally
    # Identical cost is served from the cost-bitmap cache.
    assert render_factory.bitmap_for_cost("{2}{W}{U}") is composed


def test_render_empty_cost_shows_placeholder(render_factory: ManaIconFactory) -> None:
    frame = wx.Frame(None)
    try:
        panel = render_factory.render(frame, "")
        labels = [c for c in panel.GetChildren() if isinstance(c, wx.StaticText)]
        assert any(label.GetLabel() == "—" for label in labels)
    finally:
        frame.Destroy()
