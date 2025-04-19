# test/features/message_filter/test_message_filter.py

import logging
from collections.abc import AsyncGenerator
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import pytest_asyncio

from common.core import EventPublisher, Hub
from common.feature import ConfigData, Feature
from features.message_filter.message_filter import MessageFilter
from schemas import events, models

# --- テストデータ ---
TEST_USER_NORMAL = models.User(id=123, name="normal_user", display_name="NormalUser")
TEST_USER_IGNORED = models.User(id=456, name="ignored_user", display_name="IgnoredUser")
TEST_USER_SELF = models.User(id=789, name="self_user", display_name="SelfUser")  # is_echo=True の場合

# --- Fixtures ---


@pytest.fixture
def mock_hub() -> MagicMock:
    """Hub のモックを提供します。"""
    hub = MagicMock(spec=Hub)
    hub.create_publisher.return_value = AsyncMock(spec=EventPublisher)
    hub.add_event_handler = Mock()
    return hub


@pytest.fixture
def mock_event_publisher(mock_hub: MagicMock) -> AsyncMock:
    """EventPublisher のモックを提供します。"""
    # hub モックによって作成されたパブリッシャーを返します
    return cast("AsyncMock", mock_hub.create_publisher.return_value)


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
def user_config_data_with_ignore() -> ConfigData:
    """ignore_accounts を含むユーザー設定データを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "ignore_accounts": {TEST_USER_IGNORED.name},  # 無視するユーザー名を設定
        }
    )


@pytest.fixture
def user_config_data_empty_ignore() -> ConfigData:
    """ignore_accounts が空のユーザー設定データを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "ignore_accounts": set(),  # 空のセット
        }
    )


@pytest.fixture
def mock_message_normal() -> models.Message:
    """フィルターを通過する通常のメッセージを提供します。"""
    return models.Message(
        content="This is a normal message.",
        parsed_content=["This is a normal message."],
        author=TEST_USER_NORMAL,
        is_echo=False,
    )


@pytest.fixture
def mock_message_echo() -> models.Message:
    """is_echo が True のメッセージを提供します。"""
    return models.Message(
        content="This is an echo message.",
        parsed_content=["This is an echo message."],
        author=TEST_USER_SELF,
        is_echo=True,
    )


@pytest.fixture
def mock_message_ignored_user() -> models.Message:
    """無視されるユーザーからのメッセージを提供します。"""
    return models.Message(
        content="This message should be ignored.",
        parsed_content=["This message should be ignored."],
        author=TEST_USER_IGNORED,
        is_echo=False,
    )


@pytest.fixture
def mock_event_normal(mock_message_normal: models.Message) -> events.NewMessageReceived:
    """フィルターを通過するメッセージのイベントを提供します。"""
    return events.NewMessageReceived(message=mock_message_normal)


@pytest.fixture
def mock_event_echo(mock_message_echo: models.Message) -> events.NewMessageReceived:
    """is_echo が True のメッセージのイベントを提供します。"""
    return events.NewMessageReceived(message=mock_message_echo)


@pytest.fixture
def mock_event_ignored_user(mock_message_ignored_user: models.Message) -> events.NewMessageReceived:
    """無視されるユーザーからのメッセージのイベントを提供します。"""
    return events.NewMessageReceived(message=mock_message_ignored_user)


@pytest_asyncio.fixture
async def message_filter(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_logger: MagicMock,
) -> AsyncGenerator[MessageFilter, None]:
    """テスト対象の MessageFilter インスタンスを提供します。"""
    instance = MessageFilter(mock_hub, system_config_data)
    instance._logger = mock_logger  # ロガーを差し替え
    yield instance
    # MessageFilter には非同期のクリーンアップ処理はないため、teardown は不要


# --- テストケース ---


def test_init(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_event_publisher: AsyncMock,
) -> None:
    """__init__: 依存関係の呼び出しと内部状態の初期化を確認します。"""
    # Arrange & Act
    instance = MessageFilter(mock_hub, system_config_data)

    # Assert
    assert isinstance(instance, Feature)
    assert instance._event_publisher is mock_event_publisher
    # イベントハンドラが正しく登録されたか確認
    mock_hub.add_event_handler.assert_called_once_with(events.NewMessageReceived, instance._filter)
    # EventPublisher が作成されたか確認
    mock_hub.create_publisher.assert_called_once()


@pytest.mark.asyncio
async def test_filter_no_user_config(
    message_filter: MessageFilter,
    mock_event_normal: events.NewMessageReceived,
    mock_event_publisher: AsyncMock,
) -> None:
    """_filter: user_config が None の場合、早期リターンすることを確認します。"""
    # Arrange
    await message_filter.set_user_config(None)  # ユーザー設定なし

    # Act
    await message_filter._filter(mock_event_normal)

    # Assert
    mock_event_publisher.publish.assert_not_called()  # イベントは発行されない


@pytest.mark.asyncio
async def test_filter_is_echo(
    message_filter: MessageFilter,
    user_config_data_empty_ignore: ConfigData,  # ignore_accounts は空で良い
    mock_event_echo: events.NewMessageReceived,
    mock_event_publisher: AsyncMock,
) -> None:
    """_filter: event.message.is_echo が True の場合、早期リターンすることを確認します。"""
    # Arrange
    await message_filter.set_user_config(user_config_data_empty_ignore)

    # Act
    await message_filter._filter(mock_event_echo)

    # Assert
    mock_event_publisher.publish.assert_not_called()  # イベントは発行されない


@pytest.mark.asyncio
async def test_filter_ignored_user(
    message_filter: MessageFilter,
    user_config_data_with_ignore: ConfigData,  # ignore_accounts を含む設定
    mock_event_ignored_user: events.NewMessageReceived,
    mock_event_publisher: AsyncMock,
) -> None:
    """_filter: メッセージの送信者が ignore_accounts に含まれる場合、早期リターンすることを確認します。"""
    # Arrange
    await message_filter.set_user_config(user_config_data_with_ignore)

    # Act
    await message_filter._filter(mock_event_ignored_user)

    # Assert
    mock_event_publisher.publish.assert_not_called()  # イベントは発行されない


@pytest.mark.asyncio
async def test_filter_pass(
    message_filter: MessageFilter,
    user_config_data_empty_ignore: ConfigData,  # ignore_accounts は空
    mock_event_normal: events.NewMessageReceived,
    mock_event_publisher: AsyncMock,
) -> None:
    """_filter: メッセージがフィルターを通過する場合、MessageFiltered イベントを発行することを確認します。"""
    # Arrange
    await message_filter.set_user_config(user_config_data_empty_ignore)

    # Act
    await message_filter._filter(mock_event_normal)

    # Assert
    # MessageFiltered イベントが発行されたか確認
    mock_event_publisher.publish.assert_awaited_once_with(events.MessageFiltered(message=mock_event_normal.message))
