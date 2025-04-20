import asyncio
import datetime
import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from freezegun import freeze_time

# TokenManager とその依存関係をインポート
from features.communicator.token_manager import exceptions as token_exceptions
from features.communicator.token_manager.client import Client as TokenClient
from features.communicator.token_manager.token_manager import (
    TOKEN_CHECK_INTERVAL,
    TOKEN_EXPIRE_MARGIN,
    TokenManager,
)
from features.communicator.token_manager.twitch_token import TwitchToken
from schemas import models
from utils import routines
from utils.model_file import ModelFile

# --- Constants ---
TEST_NAME = "test_token"
TEST_SCOPES = ["chat:read", "chat:edit"]
TEST_SCOPES_STR = " ".join(TEST_SCOPES)
TEST_TOKEN_DIR = Path("/fake/token/dir")
TEST_TOKEN_FILE_PATH = TEST_TOKEN_DIR / f"token_{TEST_NAME}.json"
NOW = datetime.datetime(2023, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)

# --- Fixtures ---


@pytest.fixture
def mock_logger() -> MagicMock:
    """ロガーのモックを提供します。"""
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_token_file_instance() -> MagicMock:
    """ModelFile インスタンスのモックを提供します。"""
    instance = MagicMock(spec=ModelFile)
    instance.data = None  # デフォルトではデータなし
    instance.clear = Mock(name="ModelFile.clear")
    instance.update = Mock(name="ModelFile.update")
    return instance


@pytest.fixture
def mock_token_file_cls(mock_token_file_instance: MagicMock) -> MagicMock:
    """ModelFile クラスのモックを提供し、インスタンスモックを返します。"""
    mock_cls = MagicMock(spec=ModelFile)
    mock_cls.return_value = mock_token_file_instance
    return mock_cls


@pytest.fixture
def mock_routine_instance() -> MagicMock:
    """routines.Routine インスタンスのモックを提供します。"""
    instance = MagicMock(spec=routines.Routine)
    instance.start = AsyncMock(name="Routine.start")
    instance.cancel = Mock(name="Routine.cancel")
    instance.restart = Mock(name="Routine.restart")
    return instance


@pytest.fixture
def mock_routine_decorator(mock_routine_instance: MagicMock) -> MagicMock:
    """routines.routine デコレータのモックを提供します。"""

    # デコレータ自体をモックし、呼び出されたらラップされた関数を返すようにする
    # さらに、ラップされた関数を呼び出すとモックインスタンスが返るようにする
    # (実際にはデコレータは関数をラップして Routine インスタンスを返す)
    def decorator_mock(
        *_args: tuple[Any], **_kwargs: dict[str, Any]
    ) -> Callable[[Callable[[None], Coroutine[None, None, None]]], MagicMock]:
        def wrapper(_func: Callable[[None], Coroutine[None, None, None]]) -> MagicMock:
            # デコレートされた関数自体は使わないが、構造を模倣
            # デコレータが適用された結果としてモックインスタンスを返す
            return mock_routine_instance

        return wrapper

    return MagicMock(side_effect=decorator_mock)


@pytest.fixture
def mock_start_verification() -> AsyncMock:
    """start_verification コールバックのモックを提供します。"""
    return AsyncMock(name="start_verification_callback")


@pytest.fixture
def mock_token_update_callback() -> AsyncMock:
    """token_update_callback コールバックのモックを提供します。"""
    return AsyncMock(name="token_update_callback")


@pytest.fixture
def mock_token_client_instance() -> MagicMock:
    """TokenClient インスタンスのモックを提供します。"""
    client = MagicMock(spec=TokenClient)
    client.get_device_code = AsyncMock(name="TokenClient.get_device_code")
    client.get_access_token = AsyncMock(name="TokenClient.get_access_token")
    client.refresh_access_token = AsyncMock(name="TokenClient.refresh_access_token")
    # コンテキストマネージャのモック
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock()
    return client


@pytest.fixture
def mock_token_client_cls(mock_token_client_instance: MagicMock) -> MagicMock:
    """TokenClient クラスのモックを提供します。"""
    mock_cls = MagicMock(spec=TokenClient)
    mock_cls.return_value = mock_token_client_instance
    return mock_cls


@pytest.fixture
def valid_twitch_token() -> TwitchToken:
    """テスト用の有効期限内の TwitchToken を提供します。"""
    return TwitchToken(
        access_token="valid_access",
        refresh_token="valid_refresh",
        scopes=TEST_SCOPES_STR,
        expires_at=NOW + datetime.timedelta(hours=1),
    )


@pytest.fixture
def expired_twitch_token() -> TwitchToken:
    """テスト用の有効期限切れの TwitchToken を提供します。"""
    return TwitchToken(
        access_token="expired_access",
        refresh_token="expired_refresh",
        scopes=TEST_SCOPES_STR,
        expires_at=NOW - datetime.timedelta(seconds=1),  # 期限切れ
    )


@pytest.fixture
def near_expiry_twitch_token() -> TwitchToken:
    """テスト用の有効期限間近の TwitchToken を提供します。"""
    return TwitchToken(
        access_token="near_expiry_access",
        refresh_token="near_expiry_refresh",
        scopes=TEST_SCOPES_STR,
        expires_at=NOW + TOKEN_EXPIRE_MARGIN - datetime.timedelta(seconds=1),  # マージン内
    )


@pytest.fixture
def different_scope_twitch_token() -> TwitchToken:
    """テスト用のスコープが異なる TwitchToken を提供します。"""
    return TwitchToken(
        access_token="diff_scope_access",
        refresh_token="diff_scope_refresh",
        scopes="user:read:email",  # 異なるスコープ
        expires_at=NOW + datetime.timedelta(hours=1),
    )


@pytest.fixture
def verification_model() -> models.TwitchVerification:
    """テスト用の TwitchVerification モデルを提供します。"""
    return models.TwitchVerification(
        device_code="dev123",
        interval=datetime.timedelta(seconds=5),
        user_code="USER123",
        uri="http://verify.test",
        expires_at=NOW + datetime.timedelta(minutes=5),
    )


# --- Helper Function ---


def create_token_manager(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
) -> TokenManager:
    """TokenManager インスタンスを生成するヘルパー関数。"""
    with patch("features.communicator.token_manager.token_manager.ModelFile", mock_token_file_cls):
        return TokenManager(
            logger=mock_logger,
            name=TEST_NAME,
            scopes=TEST_SCOPES,
            token_file_directory=TEST_TOKEN_DIR,
            start_verification_callback=mock_start_verification,
            token_update_callback=mock_token_update_callback,
        )


# --- Test Cases ---

# === __init__ ===


def test_init_basic(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
) -> None:
    """__init__: 基本的な初期化と ModelFile の呼び出しを確認。"""
    # Arrange (mock_token_file_instance.data is None by default)

    # Act
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )

    # Assert
    assert manager._logger is mock_logger.getChild.return_value
    assert manager._name == TEST_NAME
    assert manager._scopes == TEST_SCOPES_STR
    assert manager._update_routine is None
    assert manager._start_verification is mock_start_verification
    assert manager._token_update_callback is mock_token_update_callback

    mock_token_file_cls.assert_called_once_with(TwitchToken, TEST_TOKEN_FILE_PATH, mock_logger.getChild.return_value)
    mock_token_file_instance.clear.assert_not_called()  # スコープは一致するはず


def test_init_with_different_scope_token(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    different_scope_twitch_token: TwitchToken,
) -> None:
    """__init__: 既存トークンのスコープが異なる場合、clear() が呼ばれることを確認。"""
    # Arrange
    mock_token_file_instance.data = different_scope_twitch_token

    # Act
    create_token_manager(mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback)

    # Assert
    mock_token_file_cls.assert_called_once()
    mock_token_file_instance.clear.assert_called_once()  # スコープが違うのでクリアされる


def test_init_with_same_scope_token(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    valid_twitch_token: TwitchToken,
) -> None:
    """__init__: 既存トークンのスコープが同じ場合、clear() が呼ばれないことを確認。"""
    # Arrange
    mock_token_file_instance.data = valid_twitch_token  # スコープは TEST_SCOPES_STR

    # Act
    create_token_manager(mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback)

    # Assert
    mock_token_file_cls.assert_called_once()
    mock_token_file_instance.clear.assert_not_called()  # スコープが同じなのでクリアされない


# === _token (property) ===


def test_token_property_returns_data(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    valid_twitch_token: TwitchToken,
) -> None:
    """_token プロパティが _token_file.data を返すことを確認。"""
    # Arrange
    mock_token_file_instance.data = valid_twitch_token
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )

    # Act & Assert
    assert manager._token is valid_twitch_token


def test_token_property_returns_none(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
) -> None:
    """_token プロパティが _token_file.data が None の場合に None を返すことを確認。"""
    # Arrange
    mock_token_file_instance.data = None
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )

    # Act & Assert
    assert manager._token is None


# === _get_valid_token ===


@freeze_time(NOW)
def test_get_valid_token_none(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
) -> None:
    """_get_valid_token: トークンが存在しない場合に None を返す。"""
    # Arrange
    mock_token_file_instance.data = None
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )

    # Act & Assert
    assert manager._get_valid_token() is None


@freeze_time(NOW)
def test_get_valid_token_expired(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    expired_twitch_token: TwitchToken,
) -> None:
    """_get_valid_token: トークンが有効期限切れの場合に None を返す。"""
    # Arrange
    mock_token_file_instance.data = expired_twitch_token
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )

    # Act & Assert
    assert manager._get_valid_token() is None


@freeze_time(NOW)
def test_get_valid_token_near_expiry(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    near_expiry_twitch_token: TwitchToken,
) -> None:
    """_get_valid_token: トークンが有効期限間近 (マージン内) の場合に None を返す。"""
    # Arrange
    mock_token_file_instance.data = near_expiry_twitch_token
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )

    # Act & Assert
    assert manager._get_valid_token() is None


@freeze_time(NOW)
def test_get_valid_token_valid(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    valid_twitch_token: TwitchToken,
) -> None:
    """_get_valid_token: トークンが有効な場合にそのトークンを返す。"""
    # Arrange
    mock_token_file_instance.data = valid_twitch_token
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )

    # Act & Assert
    assert manager._get_valid_token() is valid_twitch_token


# === run ===


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_run_with_valid_token_loads_and_starts_routine(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    valid_twitch_token: TwitchToken,
    mock_routine_decorator: MagicMock,
    mock_routine_instance: MagicMock,
) -> None:
    """run: 有効なトークンが存在する場合、_update_token を呼び出し、ルーチンを開始する。"""
    # Arrange
    mock_token_file_instance.data = valid_twitch_token
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    # run の中で _update_token が呼ばれることを確認するため、事前にリセット
    mock_token_update_callback.reset_mock()
    mock_token_file_instance.update.reset_mock()

    # Act
    with patch("features.communicator.token_manager.token_manager.routines.routine", mock_routine_decorator):
        await manager.run()

    # Assert
    mock_token_file_instance.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )
    # ルーチンが設定・開始される
    mock_routine_decorator.assert_called_once_with(seconds=TOKEN_CHECK_INTERVAL.total_seconds())
    assert manager._update_routine is mock_routine_instance
    mock_routine_instance.start.assert_awaited_once()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_run_without_valid_token_starts_routine(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_decorator: MagicMock,
    mock_routine_instance: MagicMock,
) -> None:
    """run: 有効なトークンが存在しない場合、_update_token を呼び出さず、ルーチンを開始する。"""
    # Arrange
    mock_token_file_instance.data = None  # 有効なトークンなし
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_token_update_callback.reset_mock()
    mock_token_file_instance.update.reset_mock()

    # Act
    with patch("features.communicator.token_manager.token_manager.routines.routine", mock_routine_decorator):
        await manager.run()

    # Assert
    mock_token_file_instance.update.assert_not_called()
    mock_token_update_callback.assert_not_awaited()
    # ルーチンが設定・開始される
    mock_routine_decorator.assert_called_once_with(seconds=TOKEN_CHECK_INTERVAL.total_seconds())
    assert manager._update_routine is mock_routine_instance
    mock_routine_instance.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_handles_cancelled_error(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_decorator: MagicMock,
    mock_routine_instance: MagicMock,
) -> None:
    """run: ルーチン開始時の CancelledError を抑制する。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_routine_instance.start.side_effect = asyncio.CancelledError  # start で CancelledError

    # Act & Assert (例外が発生しないことを確認)
    with patch("features.communicator.token_manager.token_manager.routines.routine", mock_routine_decorator):
        await manager.run()

    mock_routine_instance.start.assert_awaited_once()


# === close ===


@pytest.mark.asyncio
async def test_close_when_running(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_instance: MagicMock,
) -> None:
    """close: 実行中の場合、ルーチンをキャンセルし、ログを出力する。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    manager._update_routine = mock_routine_instance  # 実行中状態にする

    # Act
    await manager.close()

    # Assert
    assert manager._update_routine is None  # ルーチンがクリアされる
    mock_routine_instance.cancel.assert_called_once()  # キャンセルが呼ばれる


@pytest.mark.asyncio
async def test_close_when_not_running(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_instance: MagicMock,  # cancel が呼ばれないことの確認用
) -> None:
    """close: 実行中でない場合、早期リターンし、キャンセルは呼ばれない。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    manager._update_routine = None  # 実行中でない状態

    # Act
    await manager.close()

    # Assert
    assert manager._update_routine is None
    mock_routine_instance.cancel.assert_not_called()  # キャンセルは呼ばれない


# === clear === (個別形式で再作成)


def test_clear_with_token_and_routine(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_instance: MagicMock,
    valid_twitch_token: TwitchToken,
) -> None:
    """clear: トークンデータと更新ルーチンが存在する場合。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_token_file_instance.data = valid_twitch_token
    manager._update_routine = mock_routine_instance
    mock_token_file_instance.clear.reset_mock()
    mock_routine_instance.restart.reset_mock()

    # Act
    manager.clear()

    # Assert
    mock_token_file_instance.clear.assert_called_once()
    mock_routine_instance.restart.assert_called_once()


def test_clear_without_token_but_with_routine(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_instance: MagicMock,
) -> None:
    """clear: トークンデータがなく、更新ルーチンが存在する場合。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_token_file_instance.data = None
    manager._update_routine = mock_routine_instance
    mock_token_file_instance.clear.reset_mock()
    mock_routine_instance.restart.reset_mock()

    # Act
    manager.clear()

    # Assert
    mock_token_file_instance.clear.assert_not_called()
    mock_routine_instance.restart.assert_called_once()


def test_clear_with_token_but_without_routine(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_instance: MagicMock,  # restart が呼ばれないことの確認用
    valid_twitch_token: TwitchToken,
) -> None:
    """clear: トークンデータが存在し、更新ルーチンがない場合。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_token_file_instance.data = valid_twitch_token
    manager._update_routine = None
    mock_token_file_instance.clear.reset_mock()
    mock_routine_instance.restart.reset_mock()

    # Act
    manager.clear()

    # Assert
    mock_token_file_instance.clear.assert_called_once()
    mock_routine_instance.restart.assert_not_called()


def test_clear_without_token_and_routine(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_instance: MagicMock,  # restart が呼ばれないことの確認用
) -> None:
    """clear: トークンデータも更新ルーチンもない場合。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_token_file_instance.data = None
    manager._update_routine = None
    mock_token_file_instance.clear.reset_mock()
    mock_routine_instance.restart.reset_mock()

    # Act
    manager.clear()

    # Assert
    mock_token_file_instance.clear.assert_not_called()
    mock_routine_instance.restart.assert_not_called()


# === is_running (property) ===


def test_is_running_true(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_instance: MagicMock,
) -> None:
    """is_running: _update_routine が存在する場合に True を返す。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    manager._update_routine = mock_routine_instance

    # Act & Assert
    assert manager.is_running is True


def test_is_running_false(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
) -> None:
    """is_running: _update_routine が None の場合に False を返す。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    manager._update_routine = None

    # Act & Assert
    assert manager.is_running is False


# === _refresh_token ===


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_still_valid(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    valid_twitch_token: TwitchToken,
    mock_token_client_cls: MagicMock,  # Client が呼ばれないことの確認用
) -> None:
    """_refresh_token: トークンがまだ有効な場合、何もしないでリターンする。"""
    # Arrange
    mock_token_file_instance.data = valid_twitch_token
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )

    # Act
    with patch("features.communicator.token_manager.token_manager.Client", mock_token_client_cls):
        await manager._refresh_token()

    # Assert
    # _get_valid_token が呼ばれ、有効なトークンが返される
    mock_token_client_cls.assert_not_called()  # Client は生成されない


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_refresh_success(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    expired_twitch_token: TwitchToken,  # 期限切れトークンを使用
    mock_token_client_cls: MagicMock,
    mock_token_client_instance: MagicMock,
    valid_twitch_token: TwitchToken,  # リフレッシュ後の新しいトークン
) -> None:
    """_refresh_token: 既存トークンがあり、リフレッシュに成功する場合。"""
    # Arrange
    mock_token_file_instance.data = expired_twitch_token
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_token_client_instance.refresh_access_token.return_value = valid_twitch_token
    # _update_token の呼び出し確認用リセット
    mock_token_update_callback.reset_mock()
    mock_token_file_instance.update.reset_mock()

    # Act
    with patch("features.communicator.token_manager.token_manager.Client", mock_token_client_cls):
        await manager._refresh_token()

    # Assert
    # _get_valid_token が呼ばれ、None が返される
    mock_token_client_cls.assert_called_once_with(TEST_SCOPES_STR)  # Client が生成される
    mock_token_client_instance.__aenter__.assert_awaited_once()
    mock_token_client_instance.refresh_access_token.assert_awaited_once_with(expired_twitch_token.refresh_token)
    # _update_token が呼ばれる
    mock_token_file_instance.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )
    mock_token_client_instance.__aexit__.assert_awaited_once()
    # 新規取得フローは実行されない
    mock_token_client_instance.get_device_code.assert_not_awaited()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_refresh_fail_then_get_new_success(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    expired_twitch_token: TwitchToken,  # 期限切れトークンを使用
    mock_token_client_cls: MagicMock,
    mock_token_client_instance: MagicMock,
    verification_model: models.TwitchVerification,
    valid_twitch_token: TwitchToken,  # 新規取得後のトークン
) -> None:
    """_refresh_token: リフレッシュに失敗し、その後新規取得に成功する場合。"""
    # Arrange
    mock_token_file_instance.data = expired_twitch_token
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_token_client_instance.refresh_access_token.side_effect = token_exceptions.AuthorizationError("Refresh failed")
    mock_token_client_instance.get_device_code.return_value = verification_model
    mock_token_client_instance.get_access_token.return_value = valid_twitch_token
    # _update_token の呼び出し確認用リセット
    mock_token_update_callback.reset_mock()
    mock_token_file_instance.update.reset_mock()

    # Act
    with patch("features.communicator.token_manager.token_manager.Client", mock_token_client_cls):
        await manager._refresh_token()

    # Assert
    # _get_valid_token が呼ばれ、None が返される
    mock_token_client_cls.assert_called_once_with(TEST_SCOPES_STR)
    mock_token_client_instance.__aenter__.assert_awaited_once()
    # リフレッシュ試行 -> 失敗
    mock_token_client_instance.refresh_access_token.assert_awaited_once_with(expired_twitch_token.refresh_token)
    # 新規取得フローへ
    mock_token_client_instance.get_device_code.assert_awaited_once()
    mock_start_verification.assert_awaited_once_with(verification_model)
    mock_token_client_instance.get_access_token.assert_awaited_once_with(verification_model)
    # _update_token が呼ばれる
    mock_token_file_instance.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )
    mock_token_client_instance.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_no_token_get_new_success(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_token_client_cls: MagicMock,
    mock_token_client_instance: MagicMock,
    verification_model: models.TwitchVerification,
    valid_twitch_token: TwitchToken,  # 新規取得後のトークン
) -> None:
    """_refresh_token: 既存トークンがなく、新規取得に成功する場合。"""
    # Arrange
    mock_token_file_instance.data = None  # トークンなし
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_token_client_instance.get_device_code.return_value = verification_model
    mock_token_client_instance.get_access_token.return_value = valid_twitch_token
    # _update_token の呼び出し確認用リセット
    mock_token_update_callback.reset_mock()
    mock_token_file_instance.update.reset_mock()

    # Act
    with patch("features.communicator.token_manager.token_manager.Client", mock_token_client_cls):
        await manager._refresh_token()

    # Assert
    # _get_valid_token が呼ばれ、None が返される
    mock_token_client_cls.assert_called_once_with(TEST_SCOPES_STR)
    mock_token_client_instance.__aenter__.assert_awaited_once()
    # リフレッシュは試行されない (self._token is None のため)
    mock_token_client_instance.refresh_access_token.assert_not_awaited()
    # 新規取得フローへ
    mock_token_client_instance.get_device_code.assert_awaited_once()
    mock_start_verification.assert_awaited_once_with(verification_model)
    mock_token_client_instance.get_access_token.assert_awaited_once_with(verification_model)
    # _update_token が呼ばれる
    mock_token_file_instance.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )
    mock_token_client_instance.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_get_new_fail(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    mock_token_client_cls: MagicMock,
    mock_token_client_instance: MagicMock,
    verification_model: models.TwitchVerification,
) -> None:
    """_refresh_token: 新規取得に失敗する場合 (AuthorizationError)。"""
    # Arrange
    mock_token_file_instance.data = None  # トークンなし
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    mock_token_client_instance.get_device_code.return_value = verification_model
    mock_token_client_instance.get_access_token.side_effect = token_exceptions.AuthorizationError(
        "Get access token failed"
    )
    # _update_token が呼ばれないことの確認用リセット
    mock_token_update_callback.reset_mock()
    mock_token_file_instance.update.reset_mock()

    # Act
    with patch("features.communicator.token_manager.token_manager.Client", mock_token_client_cls):
        await manager._refresh_token()

    # Assert
    mock_token_client_cls.assert_called_once_with(TEST_SCOPES_STR)
    mock_token_client_instance.__aenter__.assert_awaited_once()
    # 新規取得フローへ
    mock_token_client_instance.get_device_code.assert_awaited_once()
    mock_start_verification.assert_awaited_once_with(verification_model)
    mock_token_client_instance.get_access_token.assert_awaited_once_with(verification_model)
    # _update_token は呼ばれない
    mock_token_file_instance.update.assert_not_called()
    mock_token_update_callback.assert_not_awaited()
    mock_token_client_instance.__aexit__.assert_awaited_once()


# === _update_token ===


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_update_token(
    mock_logger: MagicMock,
    mock_token_file_cls: MagicMock,
    mock_token_file_instance: MagicMock,
    mock_start_verification: AsyncMock,
    mock_token_update_callback: AsyncMock,
    valid_twitch_token: TwitchToken,
) -> None:
    """_update_token: ログ出力、ファイル更新、コールバック呼び出しを行う。"""
    # Arrange
    manager = create_token_manager(
        mock_logger, mock_token_file_cls, mock_start_verification, mock_token_update_callback
    )
    message = "Test update message"
    # 事前リセット
    mock_token_update_callback.reset_mock()
    mock_token_file_instance.update.reset_mock()

    # Act
    await manager._update_token(message, valid_twitch_token)

    # Assert
    mock_token_file_instance.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )
