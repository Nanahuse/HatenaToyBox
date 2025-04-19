# ruff: noqa: RUF001

import pytest

from features.message_translator.language_identification.japanese_identifier import JapaneseIdentifier
from schemas.enums import Language

# --- Fixtures ---


@pytest.fixture
def identifier() -> JapaneseIdentifier:
    """Provides an instance of JapaneseIdentifier."""
    # No need to check MODULES_IMPORTED here due to pytestmark
    return JapaneseIdentifier()


# --- Parameterized Test Cases ---


@pytest.mark.parametrize(
    ("test_input", "expected", "description"),
    [
        ("こんにちは、せかい", Language.JAPANESE, "Hiragana only"),
        ("コンニチハ、セカイ", Language.JAPANESE, "Full-width Katakana only"),
        ("ｺﾝﾆﾁﾊ､ｾｶｲ", Language.JAPANESE, "Half-width Katakana only"),
        ("日本語識別子試験", Language.JAPANESE, "Kanji only"),
        ("語", Language.JAPANESE, "Single Kanji"),
        ("１２３４５６７８９０", Language.JAPANESE, "Full-width numbers only"),
        ("ＡＢＣＤＥＦＧｈｉｊｋｌｍｎ", Language.JAPANESE, "Full-width letters only"),
        ("これはﾃｽﾄです：１２３漢字ＡＢＣ", Language.JAPANESE, "Mixed Japanese characters"),
        ("Hello こんにちは World", Language.JAPANESE, "Mixed Japanese and English"),
        ("テスト！どうですか？", Language.JAPANESE, "Mixed Japanese and ASCII punctuation"),
        ("あ", Language.JAPANESE, "Single Hiragana"),
        ("ア", Language.JAPANESE, "Single Full-width Katakana"),
        ("ﾃ", Language.JAPANESE, "Single Half-width Katakana"),
        ("１", Language.JAPANESE, "Single Full-width number"),
        ("Ａ", Language.JAPANESE, "Single Full-width letter"),
    ],
    ids=[  # Provides clearer test IDs in pytest output
        "hiragana",
        "katakana_full",
        "katakana_half",
        "kanji",
        "kanji_single",
        "fw_numbers",
        "fw_letters",
        "mixed_jp",
        "mixed_jp_en",
        "mixed_jp_punct",
        "single_hiragana",
        "single_katakana_full",
        "single_katakana_half",
        "single_fw_number",
        "single_fw_letter",
    ],
)
def test_identify_as_japanese(
    identifier: JapaneseIdentifier, test_input: str, expected: Language, description: str
) -> None:
    """Tests various inputs that should be identified as Japanese."""
    assert identifier.identify(test_input) == expected, f"Failed on: {description}"


@pytest.mark.parametrize(
    ("test_input", "expected", "description"),
    [
        ("This is a test string.", Language.UNKNOWN, "English only"),
        ("1234567890", Language.UNKNOWN, "ASCII numbers only"),
        ("!@#$%^&*()_+=-`~[]{}\\|;:'\",.<>/? ", Language.UNKNOWN, "ASCII punctuation only"),
        ("", Language.UNKNOWN, "Empty string"),
        ("   \t  \n ", Language.UNKNOWN, "Whitespace only"),
        ("Привет мир", Language.UNKNOWN, "Cyrillic (Russian)"),
        ("Γειά σου Κόσμε", Language.UNKNOWN, "Greek"),
        ("مرحبا بالعالم", Language.UNKNOWN, "Arabic"),
        ("a", Language.UNKNOWN, "Single ASCII letter"),
        ("1", Language.UNKNOWN, "Single ASCII number"),
        ("!", Language.UNKNOWN, "Single ASCII punctuation"),
        (" ", Language.UNKNOWN, "Single space"),
        ("é", Language.UNKNOWN, "Single Latin Extended char"),
        ("П", Language.UNKNOWN, "Single Cyrillic char"),
    ],
    ids=[  # Provides clearer test IDs in pytest output
        "english",
        "ascii_numbers",
        "ascii_punctuation",
        "empty_string",
        "whitespace",
        "cyrillic",
        "greek",
        "arabic",
        "single_ascii_letter",
        "single_ascii_number",
        "single_ascii_punct",
        "single_space",
        "single_latin_extended",
        "single_cyrillic",
    ],
)
def test_identify_as_unknown(
    identifier: JapaneseIdentifier, test_input: str, expected: Language, description: str
) -> None:
    """Tests various inputs that should be identified as Unknown."""
    assert identifier.identify(test_input) == expected, f"Failed on: {description}"
