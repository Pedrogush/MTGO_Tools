from services.deck_service import DeckService
from utils.deck import sanitize_filename

SAMPLE_DECK = """4 Ragavan, Nimble Pilferer
2 Blood Moon
1 Otawara, Soaring City

2 Sideboard Card
3 Force of Vigor
"""


def test_deck_to_dictionary_parses_main_and_side():
    deck_service = DeckService()
    parsed = deck_service.deck_to_dictionary(SAMPLE_DECK)
    assert parsed["Ragavan, Nimble Pilferer"] == 4.0
    assert parsed["Blood Moon"] == 2.0
    assert parsed["Otawara, Soaring City"] == 1.0
    assert parsed["Sideboard Sideboard Card"] == 2.0
    assert parsed["Sideboard Force of Vigor"] == 3.0


def test_analyze_deck_counts_cards_correctly():
    summary = DeckService().analyze_deck(SAMPLE_DECK)
    assert summary["mainboard_count"] == 7
    assert summary["sideboard_count"] == 5
    assert summary["total_cards"] == 12
    assert summary["unique_mainboard"] == 3
    assert summary["unique_sideboard"] == 2


def test_analyze_deck_sums_land_counts():
    """Verify that estimated_lands sums card counts, not just unique names."""
    deck_with_lands = """4 Mountain
3 Island
2 Swamp
1 Forest
4 Lightning Bolt
2 Counterspell

3 Duress
"""
    summary = DeckService().analyze_deck(deck_with_lands)
    # Should sum 4+3+2+1 = 10 lands, not count 4 unique land names
    assert summary["estimated_lands"] == 10
    assert summary["mainboard_count"] == 16
    assert summary["unique_mainboard"] == 6


def test_analyze_deck_detects_land_keywords():
    """Verify that lands are detected by keyword matching."""
    deck_with_various_lands = """2 Hallowed Fountain
3 Breeding Pool
1 Urza's Saga
4 Misty Rainforest
2 Flooded Strand
1 Scalding Tarn
2 Lightning Bolt
"""
    summary = DeckService().analyze_deck(deck_with_various_lands)
    # Only "Misty Rainforest" contains a keyword ("forest")
    # So estimated_lands = 4
    # Note: Many real MTG lands don't contain basic land type keywords
    assert summary["estimated_lands"] == 4
    assert summary["mainboard_count"] == 15
    assert summary["unique_mainboard"] == 7


def test_analyze_deck_no_lands():
    """Verify that decks without lands report 0 estimated_lands."""
    deck_without_lands = """4 Lightning Bolt
4 Counterspell
4 Opt

3 Duress
"""
    summary = DeckService().analyze_deck(deck_without_lands)
    assert summary["estimated_lands"] == 0
    assert summary["mainboard_count"] == 12


def test_analyze_deck_merges_duplicate_lines():
    duplicate_entries = """2 Lightning Bolt
1 Lightning Bolt
3 Island

Sideboard
1 Abrade
2 Abrade
"""
    summary = DeckService().analyze_deck(duplicate_entries)

    mainboard_dict = dict(summary["mainboard_cards"])
    assert mainboard_dict["Lightning Bolt"] == 3
    assert mainboard_dict["Island"] == 3
    assert summary["unique_mainboard"] == 2

    sideboard_dict = dict(summary["sideboard_cards"])
    assert sideboard_dict["Abrade"] == 3
    assert summary["unique_sideboard"] == 1


def test_analyze_deck_skips_malformed_lines():
    """Verify lines without a leading numeric count or with too few parts are ignored."""
    deck_with_noise = """Deck
4 Lightning Bolt
// comment
x Counterspell
3 Island
Wasteland
"""
    summary = DeckService().analyze_deck(deck_with_noise)
    mainboard_dict = dict(summary["mainboard_cards"])
    # Only the two valid, count-prefixed lines parse.
    assert mainboard_dict == {"Lightning Bolt": 4, "Island": 3}
    assert summary["unique_mainboard"] == 2
    assert summary["mainboard_count"] == 7


def test_deck_to_dictionary_skips_malformed_lines():
    """Verify deck_to_dictionary ignores non-numeric counts and single-token lines."""
    deck_with_noise = """Deck
2 Ragavan, Nimble Pilferer
// comment
Wasteland
1 Blood Moon
"""
    parsed = DeckService().deck_to_dictionary(deck_with_noise)
    assert parsed == {"Ragavan, Nimble Pilferer": 2.0, "Blood Moon": 1.0}


def test_analyze_deck_preserves_fractional_quantities():
    """Averaged decks use fractional counts; whole numbers must stay int, fractions stay float."""
    averaged_deck = """2.5 Lightning Bolt
3 Island
"""
    summary = DeckService().analyze_deck(averaged_deck)
    mainboard_dict = dict(summary["mainboard_cards"])

    assert mainboard_dict["Lightning Bolt"] == 2.5
    assert isinstance(mainboard_dict["Lightning Bolt"], float)
    assert mainboard_dict["Island"] == 3
    assert isinstance(mainboard_dict["Island"], int)


def test_deck_to_dictionary_preserves_fractional_quantities():
    """deck_to_dictionary keeps float counts intact for averaged decks."""
    averaged_deck = """2.5 Lightning Bolt
3 Island
"""
    parsed = DeckService().deck_to_dictionary(averaged_deck)
    assert parsed["Lightning Bolt"] == 2.5
    assert parsed["Island"] == 3.0


def test_sanitize_filename_removes_null_bytes():
    """Verify null bytes are replaced with underscores (consecutive underscores collapsed)."""
    assert sanitize_filename("test\x00file") == "test_file"
    # Multiple null bytes collapse to single underscore
    assert sanitize_filename("null\x00\x00byte") == "null_byte"


def test_sanitize_filename_prevents_path_traversal():
    """Verify path traversal attempts are neutralized."""
    # ".." becomes "_", "/" becomes "_", consecutive _ collapsed, leading/trailing _ stripped
    assert sanitize_filename("../etc/passwd") == "etc_passwd"
    # ".." becomes "_", "\\" becomes "_", consecutive _ collapsed, leading/trailing _ stripped
    assert sanitize_filename("..\\windows\\system32") == "windows_system32"
    # ".." becomes "_", "/" becomes "_", consecutive _ collapsed
    assert sanitize_filename("test/../secret") == "test_secret"
    # "..." becomes "_", fallback triggered as only underscores remain after stripping
    assert sanitize_filename("...") == "saved_deck"


def test_sanitize_filename_handles_invalid_characters():
    """Verify invalid filesystem characters are replaced."""
    assert sanitize_filename("test:file") == "test_file"
    assert sanitize_filename("test*file") == "test_file"
    assert sanitize_filename("test?file") == "test_file"
    assert sanitize_filename('test"file') == "test_file"
    assert sanitize_filename("test<file>") == "test_file"
    assert sanitize_filename("test|file") == "test_file"
    assert sanitize_filename("test/file") == "test_file"
    assert sanitize_filename("test\\file") == "test_file"


def test_sanitize_filename_handles_reserved_windows_names():
    """Verify reserved Windows filenames are prefixed."""
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("PRN") == "_PRN"
    assert sanitize_filename("AUX") == "_AUX"
    assert sanitize_filename("NUL") == "_NUL"
    assert sanitize_filename("COM1") == "_COM1"
    assert sanitize_filename("com1") == "_com1"  # Case insensitive
    assert sanitize_filename("LPT1") == "_LPT1"
    assert sanitize_filename("lpt9") == "_lpt9"
    # Reserved names with extensions should also be prefixed
    assert sanitize_filename("CON.txt") == "_CON.txt"
    assert sanitize_filename("aux.backup") == "_aux.backup"


def test_sanitize_filename_strips_leading_trailing():
    """Verify leading/trailing whitespace and underscores are removed."""
    assert sanitize_filename("  test  ") == "test"
    assert sanitize_filename("__test__") == "test"
    assert sanitize_filename("  __test__  ") == "test"
    # Leading dots are removed (prevents hidden files)
    assert sanitize_filename(".hidden") == "hidden"
    assert sanitize_filename("...test") == "test"  # Multiple dots become _, then leading _ stripped
    # Trailing dots are removed
    assert sanitize_filename("test.") == "test"
    assert sanitize_filename("test..") == "test"


def test_sanitize_filename_uses_fallback():
    """Verify fallback is used for empty or invalid results."""
    assert sanitize_filename("") == "saved_deck"
    assert sanitize_filename("   ") == "saved_deck"
    assert sanitize_filename("___") == "saved_deck"
    assert sanitize_filename("...", fallback="custom") == "custom"
    assert sanitize_filename("///", fallback="my_deck") == "my_deck"


def test_sanitize_filename_normal_cases():
    """Verify normal filenames work correctly."""
    assert sanitize_filename("my_deck") == "my_deck"
    # Spaces are preserved in filenames
    assert sanitize_filename("Mono Red Aggro") == "Mono Red Aggro"
    assert sanitize_filename("UW Control v2") == "UW Control v2"
    # Single dots are allowed for version numbers
    assert sanitize_filename("UW Control v2.0") == "UW Control v2.0"
    assert sanitize_filename("deck.backup") == "deck.backup"
