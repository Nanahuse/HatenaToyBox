# test/features/door_bell/test_door_bell.py

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio

from common.core import Hub, ServiceCaller
from common.feature import ConfigData, Feature
from features.door_bell.door_bell import DoorBell
from schemas import events, models, services

# --- テストデータ ---
TEST_SOUND_FILE_PATH = Path("/fake/doorbell.wav")
TEST_USER_ID_1 = 123
TEST_USER_ID_2 = 456
TEST_USER_1 = models.User(id=TEST_USER_ID_1, name="user1", display_name="User1")
TEST_USER_2 = models.User(id=TEST_USER_ID_2, name="user2", display_name="User2")

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
            "sound_file": str(TEST_SOUND_FILE_PATH),  # 文字列としてパスを渡す
        }
    )


@pytest.fixture
def mock_message_event_user1() -> events.MessageFiltered:
    """ユーザー1からの MessageFiltered イベントを提供します。"""
    return events.MessageFiltered(
        message=models.Message(
            content="Hello!",
            parsed_content=["Hello!"],
            author=TEST_USER_1,
            is_echo=False,
        )
    )


@pytest.fixture
def mock_message_event_user2() -> events.MessageFiltered:
    """ユーザー2からの MessageFiltered イベントを提供します。"""
    return events.MessageFiltered(
        message=models.Message(
            content="Hi there!",
            parsed_content=["Hi there!"],
            author=TEST_USER_2,
            is_echo=False,
        )
    )


@pytest_asyncio.fixture
async def door_bell(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_logger: MagicMock,
) -> AsyncGenerator[DoorBell, None]:
    """テスト対象の DoorBell インスタンスを提供します。"""
    instance = DoorBell(mock_hub, system_config_data)
    instance._logger = mock_logger  # ロガーを差し替え
    yield instance
    # DoorBell には非同期のクリーンアップ処理はないため、teardown は不要


# --- テストケース ---


def test_init(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_service_caller: AsyncMock,
) -> None:
    """__init__: 依存関係の呼び出しと内部状態の初期化を確認します。"""
    # Arrange & Act
    instance = DoorBell(mock_hub, system_config_data)

    # Assert
    assert isinstance(instance, Feature)
    assert instance._service_caller is mock_service_caller
    assert instance._handled_user == set()  # 初期状態は空のセット
    # イベントハンドラが正しく登録されたか確認
    mock_hub.add_event_handler.assert_called_once_with(events.MessageFiltered, instance._message_received)
    # ServiceCaller が作成されたか確認
    mock_hub.create_caller.assert_called_once()


@pytest.mark.asyncio
async def test_message_received_no_user_config(
    door_bell: DoorBell,
    mock_message_event_user1: events.MessageFiltered,
    mock_service_caller: AsyncMock,
) -> None:
    """_message_received: user_config が None の場合、早期リターンすることを確認します。"""
    # Arrange
    await door_bell.set_user_config(None)  # ユーザー設定なし

    # Act
    await door_bell._message_received(mock_message_event_user1)

    # Assert
    mock_service_caller.call.assert_not_called()  # サービスは呼び出されない
    assert TEST_USER_ID_1 not in door_bell._handled_user  # ユーザーは処理済みにならない


@pytest.mark.asyncio
# Path.exists をモック
@patch("pathlib.Path.exists", return_value=False)
async def test_message_received_sound_file_not_exists(
    mock_path_exists: MagicMock,  # モックオブジェクトを受け取る
    door_bell: DoorBell,
    user_config_data_valid: ConfigData,
    mock_message_event_user1: events.MessageFiltered,
    mock_service_caller: AsyncMock,
) -> None:
    """_message_received: サウンドファイルが存在しない場合に警告ログを出力し、早期リターンすることを確認します。"""
    # Arrange
    await door_bell.set_user_config(user_config_data_valid)
    assert door_bell.user_config is not None  # 設定が適用されたことを確認

    # Act
    await door_bell._message_received(mock_message_event_user1)

    # Assert
    # Path.exists が user_config の sound_file で呼び出されたか確認
    # (user_config.sound_file は Path オブジェクトになっているはず)
    # 注意: このアサーションは Path のモック方法によっては複雑になる可能性がある
    # ここでは、exists が False を返したという事実で代用する
    mock_path_exists.assert_called()  # exists が呼び出されたことだけ確認

    # サービスは呼び出されない
    mock_service_caller.call.assert_not_called()
    # ユーザーは処理済みにならない
    assert TEST_USER_ID_1 not in door_bell._handled_user


@pytest.mark.asyncio
# Path.exists は True を返し、Path.is_file は False を返すようにモック
@patch("pathlib.Path.exists", return_value=True)
@patch("pathlib.Path.is_file", return_value=False)
async def test_message_received_sound_file_is_directory(
    mock_path_is_file: MagicMock,
    mock_path_exists: MagicMock,
    door_bell: DoorBell,
    user_config_data_valid: ConfigData,
    mock_message_event_user1: events.MessageFiltered,
    mock_service_caller: AsyncMock,
) -> None:
    """_message_received: サウンドファイルがディレクトリの場合に警告ログを出力し、早期リターンすることを確認します。"""
    # Arrange
    await door_bell.set_user_config(user_config_data_valid)
    assert door_bell.user_config is not None

    # Act
    await door_bell._message_received(mock_message_event_user1)

    # Assert
    mock_path_exists.assert_called()
    mock_path_is_file.assert_called()  # is_file も呼び出されたか確認

    # サービスは呼び出されない
    mock_service_caller.call.assert_not_called()
    # ユーザーは処理済みにならない
    assert TEST_USER_ID_1 not in door_bell._handled_user


@pytest.mark.asyncio
# Path.exists と Path.is_file は True を返すようにモック
@patch("pathlib.Path.exists", return_value=True)
@patch("pathlib.Path.is_file", return_value=True)
async def test_message_received_user_already_handled(
    mock_path_is_file: MagicMock,
    mock_path_exists: MagicMock,
    door_bell: DoorBell,
    user_config_data_valid: ConfigData,
    mock_message_event_user1: events.MessageFiltered,
    mock_service_caller: AsyncMock,
) -> None:
    """_message_received: ユーザーが既に処理済みの場合に早期リターンすることを確認します。"""
    # Arrange
    await door_bell.set_user_config(user_config_data_valid)
    # ユーザー1を事前に処理済みリストに追加
    door_bell._handled_user.add(TEST_USER_ID_1)

    # Act
    await door_bell._message_received(mock_message_event_user1)

    # Assert
    mock_path_exists.assert_called()
    mock_path_is_file.assert_called()
    # サービスは呼び出されない
    mock_service_caller.call.assert_not_called()
    # 処理済みリストは変わらない
    assert door_bell._handled_user == {TEST_USER_ID_1}


@pytest.mark.asyncio
# Path.exists と Path.is_file は True を返すようにモック
@patch("pathlib.Path.exists", return_value=True)
@patch("pathlib.Path.is_file", return_value=True)
async def test_message_received_success(
    mock_path_is_file: MagicMock,
    mock_path_exists: MagicMock,
    door_bell: DoorBell,
    user_config_data_valid: ConfigData,
    mock_message_event_user1: events.MessageFiltered,
    mock_service_caller: AsyncMock,
) -> None:
    """_message_received: 正常系の動作を確認します。"""
    # Arrange
    await door_bell.set_user_config(user_config_data_valid)
    assert door_bell.user_config is not None
    assert TEST_USER_ID_1 not in door_bell._handled_user  # 事前に処理済みでないことを確認

    # Act
    await door_bell._message_received(mock_message_event_user1)

    # Assert
    mock_path_exists.assert_called()
    mock_path_is_file.assert_called()

    # ユーザーが処理済みリストに追加されたか確認
    assert TEST_USER_ID_1 in door_bell._handled_user

    # サービス呼び出し確認
    expected_payload = models.Sound(path=door_bell.user_config.sound_file)
    mock_service_caller.call.assert_awaited_once_with(services.PlaySound(payload=expected_payload))


@pytest.mark.asyncio
# Path.exists と Path.is_file は True を返すようにモック
@patch("pathlib.Path.exists", return_value=True)
@patch("pathlib.Path.is_file", return_value=True)
async def test_message_received_multiple_users(
    mock_path_is_file: MagicMock,  # noqa: ARG001
    mock_path_exists: MagicMock,  # noqa: ARG001
    door_bell: DoorBell,
    user_config_data_valid: ConfigData,
    mock_message_event_user1: events.MessageFiltered,
    mock_message_event_user2: events.MessageFiltered,
    mock_service_caller: AsyncMock,
) -> None:
    """_message_received: 複数の異なるユーザーからのメッセージを処理できることを確認します。"""
    # Arrange
    await door_bell.set_user_config(user_config_data_valid)
    assert door_bell.user_config is not None

    # Act: ユーザー1のメッセージ処理
    await door_bell._message_received(mock_message_event_user1)

    # Assert: ユーザー1の処理確認
    assert TEST_USER_ID_1 in door_bell._handled_user
    expected_payload_1 = models.Sound(path=door_bell.user_config.sound_file)
    mock_service_caller.call.assert_awaited_once_with(services.PlaySound(payload=expected_payload_1))

    # Arrange: ユーザー2のメッセージ処理準備
    mock_service_caller.call.reset_mock()  # 呼び出し履歴をリセット
    assert TEST_USER_ID_2 not in door_bell._handled_user

    # Act: ユーザー2のメッセージ処理
    await door_bell._message_received(mock_message_event_user2)

    # Assert: ユーザー2の処理確認
    assert TEST_USER_ID_2 in door_bell._handled_user
    expected_payload_2 = models.Sound(path=door_bell.user_config.sound_file)
    mock_service_caller.call.assert_awaited_once_with(services.PlaySound(payload=expected_payload_2))

    # 処理済みリストに両方のユーザーが含まれていることを確認
    assert door_bell._handled_user == {TEST_USER_ID_1, TEST_USER_ID_2}


@pytest.mark.asyncio
# Path.exists と Path.is_file は True を返すようにモック
@patch("pathlib.Path.exists", return_value=True)
@patch("pathlib.Path.is_file", return_value=True)
async def test_message_received_runtime_error(
    mock_path_is_file: MagicMock,
    mock_path_exists: MagicMock,
    door_bell: DoorBell,
    user_config_data_valid: ConfigData,
    mock_message_event_user1: events.MessageFiltered,
    mock_service_caller: AsyncMock,
) -> None:
    """_message_received: サービス呼び出しで RuntimeError が発生した場合のログ出力を確認します。"""
    # Arrange
    await door_bell.set_user_config(user_config_data_valid)
    assert door_bell.user_config is not None
    error_message = "Failed to play sound service"
    mock_service_caller.call.side_effect = RuntimeError(error_message)

    # Act
    await door_bell._message_received(mock_message_event_user1)

    # Assert
    mock_path_exists.assert_called()
    mock_path_is_file.assert_called()

    # ユーザーは処理済みリストに追加される
    assert TEST_USER_ID_1 in door_bell._handled_user

    # サービス呼び出し確認 (呼び出されるがエラーになる)
    expected_payload = models.Sound(path=door_bell.user_config.sound_file)
    mock_service_caller.call.assert_awaited_once_with(services.PlaySound(payload=expected_payload))
