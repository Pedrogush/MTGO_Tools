import pytest

from widgets.mana_icon_factory import (
    ManaIconFactory,
    normalize_mana_query,
    tokenize_mana_symbols,
    type_global_mana_symbol,
)

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


def test_type_global_mana_symbol_empty_input_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty/whitespace tokens normalize to "" and must skip the simulator entirely."""

    def _fail() -> None:  # pragma: no cover - must never be reached
        raise AssertionError("UIActionSimulator should not be constructed for empty input")

    monkeypatch.setattr(wx, "UIActionSimulator", _fail)
    # No simulator is constructed, so nothing is typed and no exception is raised.
    assert type_global_mana_symbol("") is None
    assert type_global_mana_symbol("   ") is None


def test_type_global_mana_symbol_types_normalized_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    typed: list[int] = []

    class _RecordingSimulator:
        def Char(self, code: int) -> None:
            typed.append(code)

    monkeypatch.setattr(wx, "UIActionSimulator", _RecordingSimulator)
    type_global_mana_symbol("2w")
    # The token is normalized to "{2}{W}" before being typed character by character.
    assert "".join(chr(c) for c in typed) == "{2}{W}"


# ============= SvgRendererMixin (transparent PNGs) =============


@pytest.fixture
def svg_factory(wx_app, tmp_path) -> ManaIconFactory:
    factory = ManaIconFactory(icon_size=16)
    # Pin the rasterizer cache to tmp_path so PNGs land in the test sandbox
    # instead of a process-wide temp dir.
    factory._rasterizer_cache_dir = tmp_path
    return factory


def test_transparent_png_path_renders_basic_symbol(svg_factory: ManaIconFactory) -> None:
    path = svg_factory.transparent_png_path("{W}", height=20)
    assert path is not None
    assert path.exists()
    assert path.suffix == ".png"
    img = wx.Image(str(path), wx.BITMAP_TYPE_PNG)
    assert (img.GetWidth(), img.GetHeight()) == (20, 20)
    assert img.HasAlpha()


def test_transparent_png_path_renders_hybrid_symbol(svg_factory: ManaIconFactory) -> None:
    path = svg_factory.transparent_png_path("{U/B}", height=20)
    assert path is not None and path.exists()
    img = wx.Image(str(path), wx.BITMAP_TYPE_PNG)
    assert (img.GetWidth(), img.GetHeight()) == (20, 20)


def test_transparent_png_path_renders_standalone_energy(svg_factory: ManaIconFactory) -> None:
    path = svg_factory.transparent_png_path("{E}", height=20)
    assert path is not None and path.exists()
    img = wx.Image(str(path), wx.BITMAP_TYPE_PNG)
    assert (img.GetWidth(), img.GetHeight()) == (20, 20)


def test_transparent_png_path_renders_phyrexian_symbol(svg_factory: ManaIconFactory) -> None:
    path = svg_factory.transparent_png_path("{W/P}", height=20)
    assert path is not None and path.exists()
    img = wx.Image(str(path), wx.BITMAP_TYPE_PNG)
    assert (img.GetWidth(), img.GetHeight()) == (20, 20)


def test_transparent_png_path_non_positive_height_is_none(svg_factory: ManaIconFactory) -> None:
    assert svg_factory.transparent_png_path("{W}", height=0) is None
    assert svg_factory.transparent_png_path("{W}", height=-5) is None


def test_transparent_png_path_empty_token_is_none(svg_factory: ManaIconFactory) -> None:
    assert svg_factory.transparent_png_path("", height=20) is None
    assert svg_factory.transparent_png_path("{}", height=20) is None


def test_transparent_png_path_is_cached(svg_factory: ManaIconFactory) -> None:
    first = svg_factory.transparent_png_path("{G}", height=20)
    assert first is not None
    # A second call at the same height returns the cached path object.
    assert svg_factory.transparent_png_path("{G}", height=20) == first
    # A different height produces a distinct cache entry / file.
    other = svg_factory.transparent_png_path("{G}", height=24)
    assert other is not None and other != first


# ============= BitmapRendererMixin standalone / hybrid =============


def test_bitmap_for_symbol_renders_standalone_energy(render_factory: ManaIconFactory) -> None:
    """{E} takes the no-circle standalone branch."""
    bmp = render_factory.bitmap_for_symbol("{E}")
    assert bmp is not None and bmp.IsOk()
    assert (bmp.GetWidth(), bmp.GetHeight()) == (16, 16)


def test_bitmap_for_symbol_renders_hybrid(render_factory: ManaIconFactory) -> None:
    """{W/U} takes the split-circle hybrid branch."""
    bmp = render_factory.bitmap_for_symbol("{W/U}")
    assert bmp is not None and bmp.IsOk()
    assert (bmp.GetWidth(), bmp.GetHeight()) == (16, 16)


def test_bitmap_for_cost_with_hybrid_and_standalone(render_factory: ManaIconFactory) -> None:
    composed = render_factory.bitmap_for_cost("{W/U}{E}")
    assert composed is not None and composed.IsOk()
    assert composed.GetHeight() == 16
    assert composed.GetWidth() > 16
