# mypy: disable-error-code="attr-defined"

import asyncio
import contextlib
import datetime
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
import pytest_asyncio

from common.core import Hub
from common.feature import ConfigData, Feature
from features.communicator.client_manager import ClientManager as RealClientManager
from features.communicator.communicator import (
    ANNOUNCEMENT_MINIMUM_INTERVAL,
    COMMENTING_MINIMUM_INTERVAL,
    POLLING_INTERVAL,
    SHOUTOUT_MINIMUM_INTERVAL,
    Communicator,
)
from features.communicator.twitchio_adaptor import (
    Client as TwitchioClientProtocol,
)
from features.communicator.update_detector import (
    UpdateDetector as RealUpdateDetector,
)
from schemas import events, models, services
from utils import routines
from utils.process_manager import ProcessManager as RealProcessManager

# --- Constants ---
TEST_CHANNEL = "testchannel"
TEST_TOKEN_DIR = Path("/fake/token")
TEST_STREAM_INFO_DIR = Path("/fake/streaminfo")


# --- Fixtures ---


@pytest.fixture
def mock_hub() -> MagicMock:
    """Hub のモックを提供します。"""
    hub = MagicMock(spec=Hub)
    hub.create_publisher.return_value = AsyncMock()
    hub.add_event_handler = Mock()
    hub.add_service_handler = Mock()
    return hub


@pytest.fixture
def mock_logger() -> MagicMock:
    """ロガーのモックを提供します。"""
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_event_publisher(mock_hub: MagicMock) -> AsyncMock:
    """イベントパブリッシャーのモックを提供します。"""
    # hub モックによって作成されたパブリッシャーを返します
    return cast("AsyncMock", mock_hub.create_publisher.return_value)


@pytest.fixture
def system_config_data() -> ConfigData:
    """システム設定データのモックを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "token_file_directory": str(TEST_TOKEN_DIR),
            "stream_info_storage_directory": str(TEST_STREAM_INFO_DIR),
        }
    )


@pytest.fixture
def user_config_data() -> ConfigData:
    """ユーザー設定データのモックを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "channel": TEST_CHANNEL,
            "enable_stream_info_command": True,
        }
    )


@pytest.fixture
def mock_client_manager_instance() -> MagicMock:
    """ClientManager インスタンスのモックを提供します。"""
    manager = MagicMock(spec=RealClientManager)
    manager.get_twitch_client = AsyncMock(return_value=None)  # デフォルトではクライアントなし
    manager.update = AsyncMock()  # update メソッドをモックします
    return manager


@pytest.fixture
def mock_client_manager_cls(mock_client_manager_instance: MagicMock) -> MagicMock:
    """ClientManager クラスをモックし、特定のインスタンスを返します。"""
    mock_cls = MagicMock(spec=RealClientManager)
    mock_cls.return_value = mock_client_manager_instance
    return mock_cls


@pytest.fixture
def mock_update_detector_instance() -> MagicMock:
    """UpdateDetector インスタンスのモックを提供します。"""
    detector = MagicMock(spec=RealUpdateDetector)
    detector.initialize = Mock()
    detector.update = AsyncMock()
    return detector


@pytest.fixture
def mock_update_detector_cls(mock_update_detector_instance: MagicMock) -> MagicMock:
    """UpdateDetector クラスをモックし、特定のインスタンスを返します。"""
    mock_cls = MagicMock(spec=RealUpdateDetector)
    mock_cls.return_value = mock_update_detector_instance
    return mock_cls


@pytest.fixture
def mock_routine_manager_instance() -> MagicMock:
    """RoutineManager インスタンスのモックを提供します。"""
    manager = MagicMock(spec=routines.RoutineManager)
    manager.add = Mock()
    manager.start = Mock()
    manager.clear = Mock()
    return manager


@pytest.fixture
def mock_routine_manager_cls(mock_routine_manager_instance: MagicMock) -> MagicMock:
    """RoutineManager クラスをモックし、特定のインスタンスを返します。"""
    mock_cls = MagicMock(spec=routines.RoutineManager)
    mock_cls.return_value = mock_routine_manager_instance
    return mock_cls


@pytest.fixture
def mock_process_manager_instance() -> MagicMock:
    """ProcessManager インスタンスのモックを提供します。"""
    manager = MagicMock(spec=RealProcessManager)
    manager.get = AsyncMock(return_value=None)  # デフォルトではプロセスなし
    manager.update = AsyncMock()
    return manager


@pytest.fixture
def mock_process_manager_cls(mock_process_manager_instance: MagicMock) -> MagicMock:
    """ProcessManager クラスをモックし、特定のインスタンスを返します。"""
    mock_cls = MagicMock(spec=RealProcessManager)
    mock_cls.return_value = mock_process_manager_instance
    return mock_cls


@pytest.fixture
def mock_twitch_client() -> MagicMock:
    """Twitch クライアントのモックを提供します。"""
    client = MagicMock(spec=TwitchioClientProtocol)
    client.fetch_stream_info = AsyncMock()
    client.fetch_clips = AsyncMock()
    client.send_comment = AsyncMock()
    client.post_announcement = AsyncMock()
    client.shoutout = AsyncMock()
    return client


@pytest.fixture
def mock_stream_info() -> models.StreamInfo:
    """StreamInfo モデルのモックを提供します。"""
    return models.StreamInfo(title="Test Title", game_name="Test Game", is_live=True, viewer_count=50)


@pytest.fixture
def mock_clips() -> list[models.Clip]:
    """Clip モデルのリストのモックを提供します。"""
    return [models.Clip(title="Clip", url="url", creator="creator", created_at="time")]


@pytest_asyncio.fixture
async def communicator(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_logger: MagicMock,
) -> AsyncGenerator[Communicator, None]:
    """テスト対象の Communicator インスタンスを提供します。"""
    with (
        patch("features.communicator.communicator.UpdateDetector", autospec=True),
        patch("features.communicator.communicator.routines.RoutineManager", autospec=True),
        patch("features.communicator.communicator.ProcessManager", autospec=True),
    ):
        communicator_instance = Communicator(mock_hub, system_config_data)

    # 必要に応じてロガーをオーバーライドします
    communicator_instance._logger = mock_logger
    yield communicator_instance

    # クリーンアップ
    with contextlib.suppress(Exception):
        await communicator_instance.close()


# --- Test Cases ---


@patch("features.communicator.communicator.UpdateDetector", autospec=True)
@patch("features.communicator.communicator.routines.RoutineManager", autospec=True)
@patch("features.communicator.communicator.ProcessManager", autospec=True)
def test_init(
    mock_process_manager_cls_comm: MagicMock,
    mock_routine_manager_cls_comm: MagicMock,
    mock_update_detector_cls_comm: MagicMock,
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_event_publisher: AsyncMock,
) -> None:
    """Communicator の初期化をテストします。"""

    # パッチがアクティブな状態で、テスト関数内で Communicator をインスタンス化します
    communicator = Communicator(mock_hub, system_config_data)

    # --- アサーション ---
    assert communicator._event_publisher is mock_event_publisher
    assert isinstance(communicator.logger, logging.Logger)

    # マネージャーのインスタンス化を確認します
    # これらのモックは、*この* テスト関数のデコレータによって注入されたものであり、
    # 上記の Communicator() 呼び出し中にアクティブでした。
    mock_process_manager_cls_comm.assert_called_once()  # これはパスするはずです
    assert communicator._client_manager is mock_process_manager_cls_comm.return_value
    mock_update_detector_cls_comm.assert_called_once_with(communicator.logger, mock_event_publisher)
    assert communicator._update_detector is mock_update_detector_cls_comm.return_value
    mock_routine_manager_cls_comm.assert_called_once()
    assert communicator._routine_manager is mock_routine_manager_cls_comm.return_value

    # キューが作成されたことを確認します
    assert isinstance(communicator._comment_queue, asyncio.Queue)
    assert isinstance(communicator._announce_queue, asyncio.Queue)
    assert isinstance(communicator._shoutout_queue, asyncio.Queue)

    # イベント/サービスハンドラが登録されたことを確認します
    expected_event_calls = [
        call(events.TwitchChannelConnected, communicator._on_twitch_channel_connected),
    ]
    mock_hub.add_event_handler.assert_has_calls(expected_event_calls)

    expected_service_calls = [
        call(services.FetchClip, communicator.fetch_clips),
        call(services.FetchStreamInfo, communicator.fetch_stream_info),
        call(services.SendComment, communicator._comment_queue.put),
        call(services.PostAnnouncement, communicator._announce_queue.put),
        call(services.Shoutout, communicator._shoutout_queue.put),
    ]
    mock_hub.add_service_handler.assert_has_calls(expected_service_calls, any_order=True)


@pytest.mark.asyncio
# communicator モジュール内で使用されている ClientManager をパッチします
@patch("features.communicator.communicator.ClientManager", autospec=True)
async def test_set_user_config_none(
    mock_client_manager_cls_comm: MagicMock,  # パッチオブジェクトの名前を変更
    communicator: Communicator,
) -> None:
    """ユーザー設定を None に設定すると ClientManager がクリアされることをテストします。"""
    communicator._client_manager.get.return_value = MagicMock()

    result = await communicator.set_user_config(None)

    assert result is False
    assert communicator.user_config is None
    # ClientManager を保持する ProcessManager で update(None) が呼び出されたことをアサートします
    communicator._client_manager.update.assert_not_called()  # update(None) は直接呼ばれない
    # ClientManager クラスがインスタンス化されなかったことを確認します
    mock_client_manager_cls_comm.assert_not_called()


@pytest.mark.asyncio
@patch("features.communicator.communicator.ClientManager", autospec=True)
async def test_set_user_config_valid(
    mock_client_manager_cls_comm: MagicMock,  # パッチオブジェクトの名前を変更
    communicator: Communicator,
    user_config_data: ConfigData,
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """有効なユーザー設定を設定すると ClientManager が作成および更新されることをテストします。"""
    result = await communicator.set_user_config(user_config_data)

    assert result is True
    assert communicator.user_config is not None
    assert communicator.user_config.channel == TEST_CHANNEL

    # ClientManager クラスが正しい引数でインスタンス化されたことをアサートします
    mock_client_manager_cls_comm.assert_called_once_with(
        mock_logger,
        mock_event_publisher,
        communicator.system_config.token_file_directory,
        communicator.system_config.stream_info_storage_directory,
        TEST_CHANNEL,
        True,  # enable_stream_info_command
    )
    # 新しい ClientManager インスタンスで update が呼び出されたことをアサートします
    communicator._client_manager.update.assert_awaited_once_with(mock_client_manager_cls_comm.return_value)


@pytest.mark.asyncio
async def test_set_user_config_reset(
    user_config_data: ConfigData,
    communicator: Communicator,
) -> None:
    """ユーザー設定を None に設定すると ClientManager がクリアされることをテストします。"""
    await communicator.set_user_config(user_config_data)  # 最初に None でない設定を設定します

    communicator._client_manager.update.reset_mock()  # 以前の呼び出しをクリアします

    result = await communicator.set_user_config(None)

    assert result is True
    assert communicator.user_config is None
    communicator._client_manager.update.assert_awaited_once_with(None)


@pytest.mark.asyncio
async def test_run(communicator: Communicator) -> None:
    """メインの実行ループがルーチンを開始し、待機することをテストします。"""
    with patch.object(Feature, "run", new_callable=AsyncMock) as mock_base_run:
        # ブロックする可能性のあるチェックの前に、別のタスクで実行します
        run_task = asyncio.create_task(communicator.run())
        await asyncio.sleep(0)  # 制御を譲ります

        # ルーチンが追加されたことを確認します
        expected_routine_calls = [
            call(communicator._send_comment, COMMENTING_MINIMUM_INTERVAL),
            call(communicator._post_announce, ANNOUNCEMENT_MINIMUM_INTERVAL),
            call(communicator._shoutout, SHOUTOUT_MINIMUM_INTERVAL),
            call(communicator._polling, POLLING_INTERVAL),
        ]
        communicator._routine_manager.add.assert_has_calls(expected_routine_calls, any_order=True)

        # ルーチンが開始されたことを確認します
        communicator._routine_manager.start.assert_called_once()

        # super().run が await されたことを確認します
        mock_base_run.assert_awaited_once()

        # タスクをキャンセルし、CancelledError が発生することを確認します
        await communicator.close()
        await run_task
        # キャンセル/完了試行後に clear が呼び出されたことをアサートします
        communicator._routine_manager.clear.assert_called_once()


@pytest.mark.asyncio
async def test_on_twitch_channel_connected(
    communicator: Communicator,
    mock_twitch_client: MagicMock,
    mock_stream_info: models.StreamInfo,
    mock_clips: list[models.Clip],
) -> None:
    """TwitchChannelConnected イベントのハンドラをテストします。"""
    # _get_twitch_client がモッククライアントを返すようにモックします
    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client) as mock_get:
        mock_twitch_client.fetch_stream_info.return_value = mock_stream_info
        mock_twitch_client.fetch_clips.return_value = mock_clips
        # _polling の実行詳細が干渉しないようにモックします
        await communicator._on_twitch_channel_connected(MagicMock())

        mock_get.assert_awaited_once()
        mock_twitch_client.fetch_stream_info.assert_awaited_once_with(None)
        mock_twitch_client.fetch_clips.assert_awaited_once_with(datetime.timedelta(minutes=10))
        communicator._update_detector.initialize.assert_called_once_with(mock_stream_info, mock_clips)


@pytest.mark.asyncio
async def test_on_twitch_channel_connected_exception(
    communicator: Communicator,
    mock_logger: MagicMock,
) -> None:
    """_on_twitch_channel_connected の例外処理をテストします。"""
    error = ValueError("Fetch failed")
    with patch.object(communicator, "_get_twitch_client", side_effect=error):  # クライアント取得を失敗させます
        await communicator._on_twitch_channel_connected(MagicMock())

        mock_logger.exception.assert_called_once_with("Failed to initialize update detector")
        communicator._update_detector.initialize.assert_not_called()


@pytest.mark.asyncio
async def test_get_twitch_client_no_manager(communicator: Communicator) -> None:
    """ClientManager が設定されていない場合の _get_twitch_client をテストします。"""
    communicator._client_manager.get.return_value = None  # マネージャーなしをシミュレートします
    with pytest.raises(RuntimeError, match="ClientManger is not initialized"):
        await communicator._get_twitch_client()


@pytest.mark.asyncio
async def test_get_twitch_client_no_client(communicator: Communicator, mock_client_manager_instance: MagicMock) -> None:
    """ClientManager にアクティブなクライアントがない場合の _get_twitch_client をテストします。"""
    communicator._client_manager.get.return_value = mock_client_manager_instance
    mock_client_manager_instance.get_twitch_client.return_value = None  # クライアントなしをシミュレートします
    with pytest.raises(RuntimeError, match="TwitchClient is not initialized"):
        await communicator._get_twitch_client()


@pytest.mark.asyncio
async def test_get_twitch_client_success(
    communicator: Communicator, mock_client_manager_instance: MagicMock, mock_twitch_client: MagicMock
) -> None:
    """_get_twitch_client がクライアントを正常に返すことをテストします。"""
    communicator._client_manager.get.return_value = mock_client_manager_instance
    mock_client_manager_instance.get_twitch_client.return_value = mock_twitch_client

    client = await communicator._get_twitch_client()
    assert client is mock_twitch_client


@pytest.mark.asyncio
@patch(
    "features.communicator.communicator.cached",
    lambda cache: lambda func: func,  # noqa: ARG005
)  # キャッシュを無効化します
async def test_fetch_stream_info_service(
    communicator: Communicator, mock_twitch_client: MagicMock, mock_stream_info: models.StreamInfo
) -> None:
    """fetch_stream_info サービスハンドラをテストします。"""
    user_arg = models.User(id=123, name="test", display_name="Test")
    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        mock_twitch_client.fetch_stream_info.return_value = mock_stream_info
        result = await communicator.fetch_stream_info(user_arg)

        assert result == mock_stream_info
        mock_twitch_client.fetch_stream_info.assert_awaited_once_with(user_arg)


@pytest.mark.asyncio
@patch(
    "features.communicator.communicator.cached",
    lambda cache: lambda func: func,  # noqa: ARG005
)  # キャッシュを無効化します
async def test_fetch_clips_service(
    communicator: Communicator, mock_twitch_client: MagicMock, mock_clips: list[models.Clip]
) -> None:
    """fetch_clips サービスハンドラをテストします。"""
    duration_arg = datetime.timedelta(hours=1)
    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        mock_twitch_client.fetch_clips.return_value = mock_clips
        result = await communicator.fetch_clips(duration_arg)

        assert result == mock_clips
        mock_twitch_client.fetch_clips.assert_awaited_once_with(duration_arg)


# --- Routine Tests ---


@pytest.mark.asyncio
async def test_send_comment_routine(communicator: Communicator, mock_twitch_client: MagicMock) -> None:
    """_send_comment ルーチンをテストします。"""
    comment = models.Comment(content="Test", is_italic=True)
    await communicator._comment_queue.put(comment)

    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client) as mock_get_client:
        await communicator._send_comment()  # ルーチンを一度実行します

        mock_get_client.assert_awaited_once()  # クライアントが取得されたことを確認します

    mock_twitch_client.send_comment.assert_awaited_once_with(comment)
    assert communicator._comment_queue.empty()


@pytest.mark.asyncio
async def test_send_comment_routine_runtime_error(communicator: Communicator, mock_twitch_client: MagicMock) -> None:
    """_send_comment ルーチンが RuntimeError 時に再キューイングすることをテストします。"""
    comment = models.Comment(content="Test", is_italic=False)
    await communicator._comment_queue.put(comment)

    # クライアントが準備できていない状態をシミュレートします
    with patch.object(communicator, "_get_twitch_client", side_effect=RuntimeError("Client not ready")):
        await communicator._send_comment()

    mock_twitch_client.send_comment.assert_not_called()
    # アイテムがキューに戻されたことを確認します
    assert not communicator._comment_queue.empty()
    assert await communicator._comment_queue.get() == comment


@pytest.mark.asyncio
async def test_post_announce_routine(communicator: Communicator, mock_twitch_client: MagicMock) -> None:
    """_post_announce ルーチンをテストします。"""
    announce = models.Announcement(content="Announce", color="blue")
    await communicator._announce_queue.put(announce)

    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        await communicator._post_announce()

    mock_twitch_client.post_announcement.assert_awaited_once_with(announce)
    assert communicator._announce_queue.empty()


@pytest.mark.asyncio
async def test_post_announce_routine_runtime_error(communicator: Communicator) -> None:
    """_post_announce ルーチンが RuntimeError を処理することをテストします。"""
    announce = models.Announcement(content="Announce", color="blue")
    await communicator._announce_queue.put(announce)

    with patch.object(communicator, "_get_twitch_client", side_effect=RuntimeError("Client gone")):
        await communicator._post_announce()

    # アイテムがキューに戻されたことを確認します
    assert communicator._announce_queue.qsize() == 1
    value = await communicator._announce_queue.get()
    assert value == announce


@pytest.mark.asyncio
async def test_shoutout_routine(communicator: Communicator, mock_twitch_client: MagicMock) -> None:
    """_shoutout ルーチンをテストします。"""
    user = models.User(id=456, name="shout", display_name="Shout")
    await communicator._shoutout_queue.put(user)

    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        await communicator._shoutout()

    mock_twitch_client.shoutout.assert_awaited_once_with(user)
    assert communicator._shoutout_queue.empty()


@pytest.mark.asyncio
async def test_shoutout_routine_runtime_error(communicator: Communicator) -> None:
    """_shoutout ルーチンが RuntimeError を処理することをテストします。"""
    user = models.User(id=456, name="shout", display_name="Shout")
    await communicator._shoutout_queue.put(user)

    with patch.object(communicator, "_get_twitch_client", side_effect=RuntimeError("Client gone")):
        await communicator._shoutout()

    # アイテムがキューに戻されたことを確認します
    assert communicator._shoutout_queue.qsize() == 1
    value = await communicator._shoutout_queue.get()
    assert value == user


@pytest.mark.asyncio
async def test_polling_routine(
    communicator: Communicator,
    mock_twitch_client: MagicMock,
    mock_stream_info: models.StreamInfo,
    mock_clips: list[models.Clip],
) -> None:
    """_polling ルーチンをテストします。"""
    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        mock_twitch_client.fetch_stream_info.return_value = mock_stream_info
        mock_twitch_client.fetch_clips.return_value = mock_clips

        await communicator._polling()

        mock_twitch_client.fetch_stream_info.assert_awaited_once_with(None)
        mock_twitch_client.fetch_clips.assert_awaited_once_with(datetime.timedelta(minutes=10))
        communicator._update_detector.update.assert_awaited_once_with(mock_stream_info, mock_clips)


@pytest.mark.asyncio
async def test_polling_routine_runtime_error(
    communicator: Communicator,
) -> None:
    """_polling ルーチンが RuntimeError を処理することをテストします。"""
    with patch.object(communicator, "_get_twitch_client", side_effect=RuntimeError("Client gone")):
        # 例外が発生しないはずです
        await communicator._polling()

    communicator._update_detector.update.assert_not_called()
