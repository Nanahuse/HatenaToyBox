from collections.abc import Generator
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from cachetools import LFUCache

from features.message_translator.translator_adaptor.cache import Cache, cache_key
from schemas.enums import Language

# --- テスト用定数 ---
TEST_TEXT = "Hello"
TRANSLATED_TEXT = "こんにちは"
TARGET_LANG = Language.JAPANESE
SOURCE_LANG = Language.ENGLISH
CACHE_MAX_SIZE = 100
EXPECTED_KEY = f"{TEST_TEXT}:{TARGET_LANG!s}:{SOURCE_LANG!s}"

# --- フィクスチャ ---


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """キャッシュファイル用の一時ディレクトリパスを提供します。"""
    return tmp_path


# cache.py 内でインポートされる PersistentCache クラスをパッチします
@pytest.fixture(autouse=True)
def mock_persistent_cache_cls() -> Generator[MagicMock, None, None]:
    """shelved_cache.PersistentCache クラスをモックします。"""
    # パスは cache.py が PersistentCache を探す場所である必要があります
    patcher = patch("features.message_translator.translator_adaptor.cache.PersistentCache", autospec=True)
    mock_cls = patcher.start()
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_persistent_cache_instance(mock_persistent_cache_cls: MagicMock) -> MagicMock:
    """モックされた PersistentCache クラスのインスタンスを提供します。"""
    # インスタンスは Cache.__init__ 内で作成されます
    instance = mock_persistent_cache_cls.return_value
    # 辞書のようなメソッドをモックします
    instance.get = MagicMock(return_value=None)  # デフォルトはキャッシュミス
    instance.__setitem__ = MagicMock()
    return cast("MagicMock", instance)


@pytest.fixture
def cache_obj(tmp_cache_dir: Path) -> Cache:
    """テスト対象の Cache クラスのインスタンスを提供します。"""
    # 実際の Cache クラスをインスタンス化します。PersistentCache はモックされます。
    return Cache(tmp_cache_dir / "test_cache_file", CACHE_MAX_SIZE)


# --- cache_key 関数のテスト ---


@pytest.mark.parametrize(
    ("text", "target", "source", "expected"),
    [
        ("Hello", Language.JAPANESE, Language.ENGLISH, "Hello:ja:en"),
        ("こんにちは", Language.ENGLISH, Language.JAPANESE, "こんにちは:en:ja"),
        ("", Language.ENGLISH, Language.UNKNOWN, ":en:??"),
        ("Test", Language.UNKNOWN, Language.UNKNOWN, "Test:??:??"),
    ],
    ids=["en_to_ja", "ja_to_en", "empty_text", "unknown_langs"],
)
def test_cache_key_format(text: str, target: Language, source: Language, expected: str) -> None:
    """cache_key 関数が正しい形式の文字列を生成することをテストします。"""
    assert cache_key(text, target, source) == expected


# --- Cache クラスのテスト ---


def test_cache_initialization(
    cache_obj: Cache,  # cache_obj フィクスチャを使用
    tmp_cache_dir: Path,
    mock_persistent_cache_cls: MagicMock,
) -> None:
    """Cache クラスが PersistentCache を正しく初期化することをテストします。"""
    expected_file_path = tmp_cache_dir / "test_cache_file"
    # PersistentCache が正しい引数で呼び出されたかを確認
    # LFUCache クラスオブジェクト、絶対パス文字列、maxsize
    mock_persistent_cache_cls.assert_called_once_with(
        LFUCache,  # cachetools.LFUCache クラスそのもの
        str(expected_file_path.absolute()),  # ファイルパスの絶対パス文字列
        maxsize=CACHE_MAX_SIZE,
    )
    # _cache 属性が設定されているか確認
    assert cache_obj._cache is mock_persistent_cache_cls.return_value


def test_cache_get_hit(
    cache_obj: Cache,
    mock_persistent_cache_instance: MagicMock,
) -> None:
    """キャッシュヒットの場合に Cache.get が正しい値を返すことをテストします。"""
    # Arrange: モックされた PersistentCache インスタンスの get が値を返すように設定
    mock_persistent_cache_instance.get.return_value = TRANSLATED_TEXT

    # Act
    result = cache_obj.get(TEST_TEXT, TARGET_LANG, SOURCE_LANG)

    # Assert
    # PersistentCache.get が正しいキーで呼び出されたか確認
    mock_persistent_cache_instance.get.assert_called_once_with(EXPECTED_KEY)
    # 正しい翻訳結果が返されたか確認
    assert result == TRANSLATED_TEXT


def test_cache_get_miss(
    cache_obj: Cache,
    mock_persistent_cache_instance: MagicMock,
) -> None:
    """キャッシュミスの場合に Cache.get が None を返すことをテストします。"""
    # Arrange: モックされた PersistentCache インスタンスの get が None を返す (デフォルト)
    mock_persistent_cache_instance.get.return_value = None

    # Act
    result = cache_obj.get(TEST_TEXT, TARGET_LANG, SOURCE_LANG)

    # Assert
    # PersistentCache.get が正しいキーで呼び出されたか確認
    mock_persistent_cache_instance.get.assert_called_once_with(EXPECTED_KEY)
    # None が返されたか確認
    assert result is None


def test_cache_set(
    cache_obj: Cache,
    mock_persistent_cache_instance: MagicMock,
) -> None:
    """Cache.set が PersistentCache の __setitem__ を正しく呼び出すことをテストします。"""
    # Act
    cache_obj.set(TEST_TEXT, TARGET_LANG, SOURCE_LANG, TRANSLATED_TEXT)

    # Assert
    # PersistentCache.__setitem__ (辞書形式の代入) が正しいキーと値で呼び出されたか確認
    mock_persistent_cache_instance.__setitem__.assert_called_once_with(EXPECTED_KEY, TRANSLATED_TEXT)
