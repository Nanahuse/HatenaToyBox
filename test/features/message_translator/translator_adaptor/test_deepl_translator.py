from collections.abc import Generator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import deepl
import deepl.errors
import pytest

from features.message_translator.translator_adaptor.deepl_translator import (
    DeeplTranslationError,
    DeeplTranslator,
)
from features.message_translator.translator_adaptor.deepl_translator import (
    convert as deepl_convert,
)
from features.message_translator.translator_adaptor.translator_adaptor import TranslationError
from features.message_translator.translator_adaptor.translator_config import DeeplConfig
from schemas.enums import Language

# --- テスト用定数 ---
CACHE_MAX_SIZE = 100
TEST_API_KEY = "test-deepl-api-key"
TEST_TEXT = "Hello"
TRANSLATED_TEXT = "こんにちは"
TARGET_LANG = Language.JAPANESE
SOURCE_LANG = Language.ENGLISH


# --- フィクスチャ ---
@pytest.fixture
def mock_logger() -> MagicMock:
    """モックされたロガーインスタンスを提供します。"""
    logger = MagicMock()
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """キャッシュ用の一時ディレクトリパスを提供します。"""
    return tmp_path


@pytest.fixture
def mock_deepl_config() -> DeeplConfig:
    """DeeplConfig のインスタンスを提供します。"""
    return DeeplConfig(type="deepl", api_key=TEST_API_KEY)


@pytest.fixture(autouse=True)
def mock_deepl_translator_cls() -> Generator[MagicMock, None, None]:
    """deepl.Translator クラスをモックします。"""
    patcher = patch("features.message_translator.translator_adaptor.deepl_translator.deepl.Translator", autospec=True)
    mock_cls = patcher.start()
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_deepl_translator_instance(mock_deepl_translator_cls: MagicMock) -> MagicMock:
    """モックされた deepl.Translator クラスのインスタンスを提供します。"""
    instance = mock_deepl_translator_cls.return_value
    instance.translate = AsyncMock()
    return cast("MagicMock", instance)


@pytest.fixture(autouse=True)
def mock_cache_class() -> Generator[MagicMock, None, None]:
    """Cache クラスをモックします。"""
    patcher = patch("features.message_translator.translator_adaptor.translator_adaptor.Cache", autospec=True)
    mock_cls = patcher.start()
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_cache_instance(mock_cache_class: MagicMock) -> MagicMock:
    """モックされた Cache クラスのインスタンスを提供します。"""
    return cast("MagicMock", mock_cache_class.return_value)


@pytest.fixture
def translator(mock_logger: MagicMock, tmp_cache_dir: Path, mock_deepl_config: DeeplConfig) -> DeeplTranslator:
    """モックされた依存関係を持つ DeeplTranslator のインスタンスを提供します。"""
    return DeeplTranslator(mock_logger, tmp_cache_dir, CACHE_MAX_SIZE, mock_deepl_config)


# --- convert 関数のテスト ---


@pytest.mark.parametrize(
    ("input_lang", "expected_output"),
    [
        (Language.JAPANESE, deepl.TargetLang.Japanese),
        (Language.ENGLISH, deepl.TargetLang.English),
        (Language.UNKNOWN, None),
    ],
)
def test_deepl_convert_success(input_lang: Language, expected_output: deepl.TargetLang | None) -> None:
    """deepl_convert 関数が正しく言語を変換することをテストします。"""
    assert deepl_convert(input_lang) == expected_output


def test_deepl_convert_not_implemented() -> None:
    """deepl_convert 関数が未対応の言語で NotImplementedError を発生させることをテストします。"""

    class MockInvalidLanguage:
        pass

    with pytest.raises(NotImplementedError):
        deepl_convert(MockInvalidLanguage)  # type:ignore[arg-type]


# --- DeeplTranslationError のテスト ---


def test_deepl_translation_error_instantiation() -> None:
    """DeeplTranslationError が正しくインスタンス化されることをテストします。"""
    error = DeeplTranslationError()
    assert error.message == "Deepl translation error."
    assert isinstance(error, TranslationError)


# --- DeeplTranslator のテスト ---


def test_initialization(
    translator: DeeplTranslator,
    tmp_cache_dir: Path,
    mock_deepl_translator_cls: MagicMock,
    mock_cache_class: MagicMock,
) -> None:
    """DeeplTranslator が正しく初期化されるかをテストします。"""
    expected_cache_path = tmp_cache_dir / "DeeplTranslator"
    mock_cache_class.assert_called_once_with(expected_cache_path, CACHE_MAX_SIZE)
    assert translator._cache is mock_cache_class.return_value

    # deepl.Translator が一度だけ呼び出されたことを確認
    mock_deepl_translator_cls.assert_called_once()

    # --- translator インスタンスが設定されていることの確認 ---
    assert translator._translator is mock_deepl_translator_cls.return_value


@pytest.mark.asyncio
async def test_translate_impl_success(
    translator: DeeplTranslator,
    mock_deepl_translator_instance: MagicMock,
) -> None:
    """_translate_impl が正常に翻訳を実行し、結果を返すことをテストします。"""
    mock_deepl_translator_instance.translate.return_value = TRANSLATED_TEXT
    result = await translator._translate_impl(TEST_TEXT, TARGET_LANG, SOURCE_LANG)
    mock_deepl_translator_instance.translate.assert_awaited_once_with(
        TEST_TEXT,
        target_lang=deepl_convert(TARGET_LANG),
        source_lang=deepl_convert(SOURCE_LANG),
    )
    assert result == TRANSLATED_TEXT


@pytest.mark.asyncio
async def test_translate_impl_error(
    translator: DeeplTranslator,
    mock_deepl_translator_instance: MagicMock,
) -> None:
    """_translate_impl が deepl.errors.DeepLException をキャッチし、DeeplTranslationError を送出することをテストします。"""  # noqa: E501
    original_exception = deepl.errors.DeepLException("API error")
    mock_deepl_translator_instance.translate.side_effect = original_exception
    with pytest.raises(DeeplTranslationError) as exc_info:
        await translator._translate_impl(TEST_TEXT, TARGET_LANG, SOURCE_LANG)
    assert isinstance(exc_info.value, DeeplTranslationError)
    assert exc_info.value.__cause__ is original_exception
    mock_deepl_translator_instance.translate.assert_awaited_once_with(
        TEST_TEXT,
        target_lang=deepl_convert(TARGET_LANG),
        source_lang=deepl_convert(SOURCE_LANG),
    )
