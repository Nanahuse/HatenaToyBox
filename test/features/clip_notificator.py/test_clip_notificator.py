# test/features/clip_notificator/test_clip_notificator.py

import logging
from collections.abc import AsyncGenerator
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import pytest_asyncio

from common.core import Hub, ServiceCaller
from common.feature import ConfigData, Feature
from features.clip_notificator.clip_notificator import ClipNotificator
from schemas import enums, events, models, services

# --- テストデータ ---

TEST_CLIP = models.Clip(
    title="Amazing Clip Title",
    url="http://clips.example.com/amazingclip",
    creator="TestCreator",
    created_at="2024-01-01T12:00:00Z",
)

# --- Fixtures ---


@pytest.fixture
def mock_hub() -> MagicMock:
    """Hub のモックを提供します。"""
    hub = MagicMock(spec=Hub)
    hub.create_caller.return_value = AsyncMock(spec=ServiceCaller)
    hub.add_event_handler = Mock()
    return hub


@pytest.fixture
def mock_service_caller(mock_hub: MagicMock) -> AsyncMock:
    """ServiceCaller のモックを提供します。"""
    return cast("AsyncMock", mock_hub.create_caller.return_value)


@pytest.fixture
def mock_logger() -> MagicMock:
    """ロガーのモックを提供します。"""
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def system_config_data() -> ConfigData:
    """システム設定データのモックを提供します。"""
    # この機能ではシステム設定は使用しないが、基底クラスのために必要
    return ConfigData({"version": 0})


@pytest.fixture
def user_config_data_valid() -> ConfigData:
    """有効なユーザー設定データを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "message_format": "New clip! {title} by {creator} - {url}",
            "color": "purple",  # 文字列として設定
        }
    )


@pytest.fixture
def user_config_data_no_color() -> ConfigData:
    """色設定がないユーザー設定データを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "message_format": "Clip: {url}",
            "color": None,
        }
    )


@pytest.fixture
def mock_clip_found_event() -> events.ClipFound:
    """テスト用の ClipFound イベントを提供します。"""
    return events.ClipFound(clip=TEST_CLIP)


@pytest_asyncio.fixture
async def clip_notificator(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_logger: MagicMock,
) -> AsyncGenerator[ClipNotificator, None]:
    """テスト対象の ClipNotificator インスタンスを提供します。"""
    instance = ClipNotificator(mock_hub, system_config_data)
    instance._logger = mock_logger  # ロガーを差し替え
    yield instance
    # ClipNotificator には非同期のクリーンアップ処理はないため、teardown は不要


# --- テストケース ---


def test_init(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_service_caller: AsyncMock,
) -> None:
    """__init__: 依存関係の呼び出しと内部状態の初期化を確認します。"""
    # Arrange & Act
    instance = ClipNotificator(mock_hub, system_config_data)

    # Assert
    assert isinstance(instance, Feature)
    assert instance._service_caller is mock_service_caller
    # イベントハンドラが正しく登録されたか確認
    mock_hub.add_event_handler.assert_called_once_with(events.ClipFound, instance._new_clip_found)
    # ServiceCaller が作成されたか確認
    mock_hub.create_caller.assert_called_once()


@pytest.mark.asyncio
async def test_new_clip_found_no_user_config(
    clip_notificator: ClipNotificator,
    mock_clip_found_event: events.ClipFound,
    mock_service_caller: AsyncMock,
) -> None:
    """_new_clip_found: user_config が None の場合、早期リターンすることを確認します。"""
    # Arrange
    await clip_notificator.set_user_config(None)  # ユーザー設定なし

    # Act
    await clip_notificator._new_clip_found(mock_clip_found_event)

    # Assert
    mock_service_caller.call.assert_not_called()  # サービスは呼び出されない


@pytest.mark.asyncio
async def test_new_clip_found_success_with_color(
    clip_notificator: ClipNotificator,
    user_config_data_valid: ConfigData,
    mock_clip_found_event: events.ClipFound,
    mock_service_caller: AsyncMock,
) -> None:
    """_new_clip_found: 正常系の動作（色設定あり）を確認します。"""
    # Arrange
    await clip_notificator.set_user_config(user_config_data_valid)

    # Act
    await clip_notificator._new_clip_found(mock_clip_found_event)

    # Assert
    # 1. メッセージフォーマット確認
    expected_message = f"New clip! {TEST_CLIP.title} by {TEST_CLIP.creator} - {TEST_CLIP.url}"

    # 2. サービス呼び出し確認
    expected_payload = models.Announcement(
        content=expected_message,
        color=enums.AnnouncementColor.PURPLE,  # "purple" に対応する Enum
    )
    mock_service_caller.call.assert_awaited_once_with(services.PostAnnouncement(payload=expected_payload))


@pytest.mark.asyncio
async def test_new_clip_found_success_no_color(
    clip_notificator: ClipNotificator,
    user_config_data_no_color: ConfigData,
    mock_clip_found_event: events.ClipFound,
    mock_service_caller: AsyncMock,
) -> None:
    """_new_clip_found: 正常系の動作（色設定なし）を確認します。"""
    # Arrange
    await clip_notificator.set_user_config(user_config_data_no_color)

    # Act
    await clip_notificator._new_clip_found(mock_clip_found_event)

    # Assert
    # 1. メッセージフォーマット確認
    expected_message = f"Clip: {TEST_CLIP.url}"

    # 2. サービス呼び出し確認
    expected_payload = models.Announcement(
        content=expected_message,
        color=None,  # 色設定なし
    )
    mock_service_caller.call.assert_awaited_once_with(services.PostAnnouncement(payload=expected_payload))


@pytest.mark.asyncio
async def test_new_clip_found_runtime_error(
    clip_notificator: ClipNotificator,
    user_config_data_valid: ConfigData,
    mock_clip_found_event: events.ClipFound,
    mock_service_caller: AsyncMock,
) -> None:
    """_new_clip_found: サービス呼び出しで RuntimeError が発生した場合のログ出力を確認します。"""
    # Arrange
    await clip_notificator.set_user_config(user_config_data_valid)
    error_message = "Failed to call service"
    mock_service_caller.call.side_effect = RuntimeError(error_message)

    # Act
    await clip_notificator._new_clip_found(mock_clip_found_event)

    # Assert
    # 1. サービス呼び出し確認 (呼び出されるがエラーになる)
    expected_message = f"New clip! {TEST_CLIP.title} by {TEST_CLIP.creator} - {TEST_CLIP.url}"
    expected_payload = models.Announcement(
        content=expected_message,
        color=enums.AnnouncementColor.PURPLE,
    )
    mock_service_caller.call.assert_awaited_once_with(services.PostAnnouncement(payload=expected_payload))
