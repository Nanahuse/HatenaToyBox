from collections.abc import Generator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import gpytranslate
import pytest

from features.message_translator.translator_adaptor.google_translator import (
    GoogleTranslationError,
    GoogleTranslator,
)
from features.message_translator.translator_adaptor.google_translator import (
    convert as google_convert,  # convert 関数もテスト対象
)
from features.message_translator.translator_adaptor.translator_adaptor import TranslationError
from features.message_translator.translator_adaptor.translator_config import GoogleConfig
from schemas.enums import Language

# --- テスト用定数 ---
CACHE_MAX_SIZE = 100
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
def mock_google_config() -> GoogleConfig:
    """GoogleConfig のインスタンスを提供します。"""
    # GoogleConfig は追加のフィールドを持たないので、シンプルにインスタンス化
    return GoogleConfig(type="google")


# GoogleTranslator がインポートするモジュール内の gpytranslate.Translator クラスをパッチします
@pytest.fixture(autouse=True)
def mock_gpytranslate_translator_cls() -> Generator[MagicMock, None, None]:
    """gpytranslate.Translator クラスをモックします。"""
    # パスは GoogleTranslator が gpytranslate.Translator を探す場所である必要があります
    patcher = patch(
        "features.message_translator.translator_adaptor.google_translator.google_translate.Translator", autospec=True
    )
    mock_cls = patcher.start()
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_gpytranslate_translator_instance(mock_gpytranslate_translator_cls: MagicMock) -> MagicMock:
    """モックされた gpytranslate.Translator クラスのインスタンスを提供します。"""
    # Translator インスタンスは GoogleTranslator.__init__ 内で作成されます
    instance = mock_gpytranslate_translator_cls.return_value
    # translate メソッドを AsyncMock として設定
    instance.translate = AsyncMock()
    return cast("MagicMock", instance)


# TranslatorAdaptor と同様に Cache クラスをモックします
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
def translator(
    mock_logger: MagicMock,
    tmp_cache_dir: Path,
    mock_google_config: GoogleConfig,  # GoogleConfig を使用
) -> GoogleTranslator:
    """モックされた依存関係を持つ GoogleTranslator のインスタンスを提供します。"""
    return GoogleTranslator(mock_logger, tmp_cache_dir, CACHE_MAX_SIZE, mock_google_config)


# --- convert 関数のテスト ---


@pytest.mark.parametrize(
    ("input_lang", "expected_output"),
    [
        (Language.JAPANESE, "ja"),
        (Language.ENGLISH, "en"),
        (Language.UNKNOWN, "auto"),
    ],
)
def test_google_convert_success(input_lang: Language, expected_output: str) -> None:
    """google_convert 関数が正しく言語コード文字列に変換することをテストします。"""
    assert google_convert(input_lang) == expected_output


def test_google_convert_not_implemented() -> None:
    """google_convert 関数が未対応の言語で NotImplementedError を発生させることをテストします。"""

    class MockInvalidLanguage:
        pass

    with pytest.raises(NotImplementedError):
        google_convert(MockInvalidLanguage)  # type: ignore[arg-type]


# --- GoogleTranslationError のテスト ---


def test_google_translation_error_instantiation() -> None:
    """GoogleTranslationError が正しくインスタンス化されることをテストします。"""
    error = GoogleTranslationError()
    assert error.message == "Google Translation error."
    assert isinstance(error, TranslationError)  # 親クラスを継承しているか確認


# --- GoogleTranslator のテスト ---


def test_initialization(
    translator: GoogleTranslator,
    mock_logger: MagicMock,
    tmp_cache_dir: Path,
    mock_gpytranslate_translator_cls: MagicMock,  # gpytranslate.Translator の呼び出しを検証
    mock_cache_class: MagicMock,  # Cache の呼び出しを検証
) -> None:
    """GoogleTranslator が正しく初期化されるかをテストします。"""
    # 1. 親クラスの初期化確認 (Logger と Cache)
    mock_logger.getChild.assert_called_once_with("GoogleTranslator")
    expected_cache_path = tmp_cache_dir / "GoogleTranslator"
    mock_cache_class.assert_called_once_with(expected_cache_path, CACHE_MAX_SIZE)
    assert translator._logger is mock_logger.getChild.return_value
    assert translator._cache is mock_cache_class.return_value

    # 2. gpytranslate.Translator の初期化確認 (引数なしで呼び出される)
    mock_gpytranslate_translator_cls.assert_called_once_with()

    # 3. translator インスタンスが設定されていることの確認
    assert translator._translator is mock_gpytranslate_translator_cls.return_value


@pytest.mark.asyncio
async def test_translate_impl_success(
    translator: GoogleTranslator,
    mock_gpytranslate_translator_instance: MagicMock,
) -> None:
    """_translate_impl が正常に翻訳を実行し、結果を返すことをテストします。"""
    # Arrange: モックされた gpytranslate.Translator の translate メソッドが結果を返すように設定
    # gpytranslate は結果オブジェクトを返し、その .text 属性に翻訳結果が入る
    mock_result = MagicMock()
    mock_result.text = TRANSLATED_TEXT
    mock_gpytranslate_translator_instance.translate.return_value = mock_result

    # Act
    result = await translator._translate_impl(TEST_TEXT, TARGET_LANG, SOURCE_LANG)

    # Assert
    # gpytranslate.Translator.translate が正しい引数で呼び出されたか確認
    mock_gpytranslate_translator_instance.translate.assert_awaited_once_with(
        TEST_TEXT,
        sourcelang=google_convert(SOURCE_LANG),
        targetlang=google_convert(TARGET_LANG),
    )
    # 結果が正しく返されたか確認 (mock_result.text)
    assert result == TRANSLATED_TEXT


@pytest.mark.asyncio
async def test_translate_impl_error(
    translator: GoogleTranslator,
    mock_gpytranslate_translator_instance: MagicMock,
) -> None:
    """_translate_impl が gpytranslate.TranslationError をキャッチし、GoogleTranslationError を送出することをテストします。"""  # noqa: E501
    # Arrange: モックされた gpytranslate.Translator の translate メソッドがエラーを送出するように設定
    original_exception = gpytranslate.TranslationError(ValueError("API error"))
    mock_gpytranslate_translator_instance.translate.side_effect = original_exception

    # Act & Assert
    with pytest.raises(GoogleTranslationError) as exc_info:
        await translator._translate_impl(TEST_TEXT, TARGET_LANG, SOURCE_LANG)

    # 送出された例外が GoogleTranslationError であることを確認
    assert isinstance(exc_info.value, GoogleTranslationError)
    # 元の例外が原因として保持されていることを確認 (__cause__)
    assert exc_info.value.__cause__ is original_exception
    # gpytranslate.Translator.translate が呼び出されたことを確認
    mock_gpytranslate_translator_instance.translate.assert_awaited_once_with(
        TEST_TEXT,
        sourcelang=google_convert(SOURCE_LANG),
        targetlang=google_convert(TARGET_LANG),
    )
