from collections.abc import Generator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from features.message_translator.translator_adaptor.cache import cache_key
from features.message_translator.translator_adaptor.translator_adaptor import TranslationError, TranslatorAdaptor
from schemas.enums import Language

# --- テスト用定数 ---
CACHE_MAX_SIZE = 100
TEST_TEXT = "Hello"
TRANSLATED_TEXT = "こんにちは"
TARGET_LANG = Language.JAPANESE
SOURCE_LANG = Language.ENGLISH
CACHE_KEY = cache_key(TEST_TEXT, TARGET_LANG, SOURCE_LANG)  # アサーション用に事前に計算

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


# TranslatorAdaptor がインポートするモジュール内の Cache クラスをパッチします
@pytest.fixture(autouse=True)  # このモジュール内のすべてのテストに自動的に適用します
def mock_cache_class() -> Generator[MagicMock, None, None]:  # mocker 引数を削除
    """TranslatorAdaptor によって使用される Cache クラスをモックします。"""
    # パスは TranslatorAdaptor が Cache を探す場所である必要があります
    # unittest.mock.patch を使用し、yield でパッチの開始/停止を管理
    patcher = patch("features.message_translator.translator_adaptor.translator_adaptor.Cache", autospec=True)
    mock_cls = patcher.start()  # パッチを開始し、モッククラスを取得
    yield mock_cls  # テスト実行中はモッククラスを提供
    patcher.stop()  # テスト終了後にパッチを停止


@pytest.fixture
def mock_cache_instance(mock_cache_class: MagicMock) -> MagicMock:
    """モックされた Cache クラスのインスタンスを提供します。"""
    # Cache インスタンスは TranslatorAdaptor.__init__ 内で作成されます
    # mock_cache_class.return_value でそのインスタンスにアクセスできます
    return cast("MagicMock", mock_cache_class.return_value)


@pytest.fixture
def adaptor(mock_logger: MagicMock, tmp_cache_dir: Path) -> TranslatorAdaptor:
    """モックされた依存関係を持つ TranslatorAdaptor のインスタンスを提供します。"""
    # 実際のクラスをインスタンス化しますが、その Cache 依存関係は mock_cache_class によってモックされます
    return TranslatorAdaptor(mock_logger, tmp_cache_dir, CACHE_MAX_SIZE)


# --- テストケース ---


def test_initialization(
    adaptor: TranslatorAdaptor,
    mock_logger: MagicMock,
    tmp_cache_dir: Path,
    mock_cache_class: MagicMock,
) -> None:
    """TranslatorAdaptor が正しく初期化されるかをテストします。"""
    # ロガーの子が正しいクラス名で作成されたことをアサートします
    mock_logger.getChild.assert_called_once_with("TranslatorAdaptor")

    # Cache が正しくインスタンス化されたことをアサートします
    expected_cache_path = tmp_cache_dir / "TranslatorAdaptor"
    mock_cache_class.assert_called_once_with(expected_cache_path, CACHE_MAX_SIZE)
    assert adaptor._logger is mock_logger.getChild.return_value
    assert adaptor._cache is mock_cache_class.return_value  # インスタンスの割り当てを確認


@pytest.mark.asyncio
async def test_translate_cache_hit(
    adaptor: TranslatorAdaptor,
    mock_cache_instance: MagicMock,
) -> None:
    """結果がキャッシュで見つかった場合の translate メソッドをテストします。"""
    # Arrange: キャッシュが値を返すようにモックします
    mock_cache_instance.get.return_value = TRANSLATED_TEXT
    # unittest.mock.patch.object をコンテキストマネージャとして使用
    with patch.object(adaptor, "_translate_impl", new_callable=AsyncMock) as mock_impl:
        # Act
        result = await adaptor.translate(TEST_TEXT, TARGET_LANG, SOURCE_LANG)

        # Assert
        assert result == TRANSLATED_TEXT
        mock_cache_instance.get.assert_called_once_with(TEST_TEXT, TARGET_LANG, SOURCE_LANG)
        mock_impl.assert_not_called()  # 重要: 実装が呼び出されなかったことを確認
        mock_cache_instance.set.assert_not_called()  # 重要: キャッシュに書き込まれなかったことを確認


@pytest.mark.asyncio
async def test_translate_cache_miss(
    adaptor: TranslatorAdaptor,
    mock_cache_instance: MagicMock,
) -> None:
    """結果がキャッシュにない場合の translate メソッドをテストします。"""
    # Arrange: キャッシュが None を返すようにモックします (キャッシュミス)
    mock_cache_instance.get.return_value = None
    # unittest.mock.patch.object をコンテキストマネージャとして使用
    with patch.object(adaptor, "_translate_impl", new_callable=AsyncMock) as mock_impl:
        mock_impl.return_value = TRANSLATED_TEXT

        # Act
        result = await adaptor.translate(TEST_TEXT, TARGET_LANG, SOURCE_LANG)

        # Assert
        assert result == TRANSLATED_TEXT
        # cache get が呼び出されたことを確認
        mock_cache_instance.get.assert_called_once_with(TEST_TEXT, TARGET_LANG, SOURCE_LANG)
        # _translate_impl が呼び出されたことを確認
        mock_impl.assert_called_once_with(TEST_TEXT, TARGET_LANG, SOURCE_LANG)
        # cache set が正しい引数で呼び出されたことを確認
        mock_cache_instance.set.assert_called_once_with(TEST_TEXT, TARGET_LANG, SOURCE_LANG, TRANSLATED_TEXT)


def test_translation_error_instantiation() -> None:
    """カスタム TranslationError クラスをテストします。"""
    error_message = "特定の翻訳失敗。"
    error = TranslationError(error_message)
    assert error.message == error_message
    assert isinstance(error, RuntimeError)  # 継承を確認


@pytest.mark.asyncio
async def test_translate_impl_raises_error_no_cache_set(
    adaptor: TranslatorAdaptor,
    mock_cache_instance: MagicMock,
) -> None:
    """_translate_impl がエラーを発生させた場合にキャッシュが設定されないことをテストします。"""
    # Arrange: キャッシュミス
    mock_cache_instance.get.return_value = None
    # _translate_impl がエラーを発生させるようにモックします
    test_error = ValueError("内部で翻訳に失敗しました")
    # unittest.mock.patch.object をコンテキストマネージャとして使用
    with patch.object(adaptor, "_translate_impl", new_callable=AsyncMock) as mock_impl:
        mock_impl.side_effect = test_error

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:  # 元のエラーが伝播することを期待します  # noqa: PT011
            await adaptor.translate(TEST_TEXT, TARGET_LANG, SOURCE_LANG)

        assert exc_info.value is test_error  # 同じエラーインスタンスであることを確認
        mock_cache_instance.get.assert_called_once_with(TEST_TEXT, TARGET_LANG, SOURCE_LANG)
        mock_impl.assert_called_once_with(TEST_TEXT, TARGET_LANG, SOURCE_LANG)
        mock_cache_instance.set.assert_not_called()  # 重要: エラー時にキャッシュに書き込まれなかったことを確認
