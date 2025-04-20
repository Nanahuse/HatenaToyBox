import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
import pytest_asyncio

from common.core import Hub, ServiceCaller
from common.feature import ConfigData, Feature
from features.auto_interception.auto_interception import (
    INTERCEPTION_INTERVAL,
    AutoInterception,
)
from schemas import enums, events, models, services
from utils import routines

# --- テストデータ ---

TEST_RAIDER = models.User(id=123, name="raider_test", display_name="Raider_Test")
TEST_STREAM_INFO = models.StreamInfo(
    title="Test Stream Title",
    game=models.Game(game_id="456", name="Test Game"),
    is_live=True,
    viewer_count=10,
)
TEST_STREAM_INFO_NO_GAME = models.StreamInfo(title="Another Title", game=None, is_live=True, viewer_count=5)

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
    return ConfigData({"version": 0})  # この機能ではシステム設定は使用しない


@pytest.fixture
def user_config_data_full() -> ConfigData:
    """アナウンスとシャウトアウト両方有効なユーザー設定データを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "reaction_delay": "PT5S",  # 5秒
            "do_shoutout": True,
            "do_announcement": True,
            "message_format": "Thanks {raider} for raiding! Check them out playing {game}!",
            "color": "blue",
        }
    )


@pytest.fixture
def user_config_data_announce_only() -> ConfigData:
    """アナウンスのみ有効なユーザー設定データを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "reaction_delay": "PT3S",  # 3秒
            "do_shoutout": False,
            "do_announcement": True,
            "message_format": "Welcome {raider}!",
            "color": "green",
        }
    )


@pytest.fixture
def user_config_data_shoutout_only() -> ConfigData:
    """シャウトアウトのみ有効なユーザー設定データを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "reaction_delay": "PT1S",  # 1秒
            "do_shoutout": True,
            "do_announcement": False,
            "message_format": "",  # 使われない
            "color": None,
        }
    )


@pytest.fixture
def user_config_data_no_action() -> ConfigData:
    """アクションが無効なユーザー設定データを提供します。"""
    return ConfigData(
        {
            "version": 0,
            "reaction_delay": "PT1S",
            "do_shoutout": False,
            "do_announcement": False,
            "message_format": "",
            "color": None,
        }
    )


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
def mock_raid_event() -> events.RaidDetected:
    """テスト用の RaidDetected イベントを提供します。"""
    return events.RaidDetected(raider=TEST_RAIDER)


@pytest_asyncio.fixture
async def auto_interception(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_logger: MagicMock,
    mock_routine_manager_cls: MagicMock,  # run のテストで使用
) -> AsyncGenerator[AutoInterception, None]:
    """テスト対象の AutoInterception インスタンスを提供します。"""
    # RoutineManager をパッチして run のテストを可能にします
    with patch("features.auto_interception.auto_interception.routines.RoutineManager", mock_routine_manager_cls):
        instance = AutoInterception(mock_hub, system_config_data)
        instance._logger = mock_logger  # ロガーを差し替え
        yield instance
        # クリーンアップ (run が呼ばれた場合)
    if hasattr(instance, "_routine_manager") and instance._routine_manager is not None:
        await instance.close()


# --- テストケース ---


def test_init(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_service_caller: AsyncMock,
) -> None:
    """__init__: 依存関係の呼び出しと内部状態の初期化を確認します。"""
    # Arrange & Act
    instance = AutoInterception(mock_hub, system_config_data)

    # Assert
    assert isinstance(instance, Feature)
    assert instance._service_caller is mock_service_caller
    assert isinstance(instance._raid_event_queue, asyncio.Queue)
    mock_hub.add_event_handler.assert_called_once_with(events.RaidDetected, instance._raid_event_queue.put)
    mock_hub.create_caller.assert_called_once()


@pytest.mark.asyncio
async def test_run(
    auto_interception: AutoInterception,
    mock_routine_manager_instance: MagicMock,
) -> None:
    """run: RoutineManager のセットアップ、super().run() の呼び出し、クリーンアップを確認します。"""
    # Arrange
    # auto_interception fixture 内で RoutineManager はモックされています
    with patch.object(Feature, "run", new_callable=AsyncMock) as mock_super_run:
        # Act
        run_task = asyncio.create_task(auto_interception.run())
        await asyncio.sleep(0)  # run タスクを開始させます

        # Assert setup and run
        mock_routine_manager_instance.add.assert_called_once_with(auto_interception._main, INTERCEPTION_INTERVAL)
        mock_routine_manager_instance.start.assert_called_once()
        mock_super_run.assert_awaited_once()  # super().run() が呼ばれたか

        # Assert cleanup on close
        await auto_interception.close()  # close を呼び出す
        await run_task  # run タスクの完了を待つ
        mock_routine_manager_instance.clear.assert_called_once()  # clear が呼ばれたか


@pytest.mark.asyncio
async def test_main_no_user_config(
    auto_interception: AutoInterception,
    mock_raid_event: events.RaidDetected,
) -> None:
    """_main: user_config が None の場合、イベントを再キューイングして早期リターンすることを確認します。"""
    # Arrange
    await auto_interception.set_user_config(None)  # ユーザー設定なし
    await auto_interception._raid_event_queue.put(mock_raid_event)
    assert auto_interception._raid_event_queue.qsize() == 1

    # Act
    # _main は get() で待機するため、完了を待つ
    main_task = asyncio.create_task(auto_interception._main())
    await asyncio.sleep(0)  # タスクを開始させる

    # Assert
    assert main_task.done()  # 早期リターンしたはず
    # イベントがキューに戻っていることを確認
    assert auto_interception._raid_event_queue.qsize() == 1
    requeued_event = await auto_interception._raid_event_queue.get()
    assert requeued_event == mock_raid_event


@pytest.mark.asyncio
async def test_main_no_action_config(
    auto_interception: AutoInterception,
    user_config_data_no_action: ConfigData,
    mock_raid_event: events.RaidDetected,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: do_announcement と do_shoutout が False の場合、早期リターンすることを確認します。"""
    # Arrange
    await auto_interception.set_user_config(user_config_data_no_action)
    await auto_interception._raid_event_queue.put(mock_raid_event)

    # Act
    main_task = asyncio.create_task(auto_interception._main())
    await asyncio.sleep(0)

    # Assert
    assert main_task.done()  # 早期リターンしたはず
    assert auto_interception._raid_event_queue.empty()  # キューは空になる
    mock_service_caller.call.assert_not_called()  # サービスは呼ばれない


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)  # asyncio.sleep をモック
async def test_main_full_action(
    mock_sleep: AsyncMock,
    auto_interception: AutoInterception,
    user_config_data_full: ConfigData,
    mock_raid_event: events.RaidDetected,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: アナウンスとシャウトアウト両方が有効な場合のフルフローを確認します。"""
    # Arrange
    await auto_interception.set_user_config(user_config_data_full)
    await auto_interception._raid_event_queue.put(mock_raid_event)
    mock_service_caller.call.side_effect = [TEST_STREAM_INFO, None, None]  # FetchStreamInfo, PostAnnounce, Shoutout

    # Act
    await auto_interception._main()

    # Assert
    assert auto_interception._raid_event_queue.empty()

    # 2. FetchStreamInfo 呼び出し
    fetch_call = call(services.FetchStreamInfo(payload=TEST_RAIDER))

    # 3. asyncio.sleep 呼び出し
    assert auto_interception.user_config is not None  # user_config がセットされていることを確認
    mock_sleep.assert_awaited_once_with(auto_interception.user_config.reaction_delay.total_seconds())

    # 4. PostAnnouncement 呼び出し
    expected_message = "Thanks Raider_Test for raiding! Check them out playing Test Game!"
    announce_call = call(
        services.PostAnnouncement(
            payload=models.Announcement(
                content=expected_message,
                color=enums.AnnouncementColor.BLUE,
            )
        )
    )

    # 5. Shoutout 呼び出し
    shoutout_call = call(services.Shoutout(payload=TEST_RAIDER))

    # サービス呼び出し全体を確認 (順序も考慮)
    mock_service_caller.call.assert_has_awaits([fetch_call, announce_call, shoutout_call])


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_main_only_announcement(
    mock_sleep: AsyncMock,
    auto_interception: AutoInterception,
    user_config_data_announce_only: ConfigData,
    mock_raid_event: events.RaidDetected,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: アナウンスのみ有効な場合のフローを確認します。"""
    # Arrange
    await auto_interception.set_user_config(user_config_data_announce_only)
    await auto_interception._raid_event_queue.put(mock_raid_event)
    mock_service_caller.call.side_effect = [TEST_STREAM_INFO, None]  # FetchStreamInfo, PostAnnounce

    # Act
    await auto_interception._main()

    # Assert
    assert auto_interception._raid_event_queue.empty()
    assert auto_interception.user_config is not None  # user_config がセットされていることを確認
    mock_sleep.assert_awaited_once_with(auto_interception.user_config.reaction_delay.total_seconds())

    fetch_call = call(services.FetchStreamInfo(payload=TEST_RAIDER))
    expected_message = "Welcome Raider_Test!"
    announce_call = call(
        services.PostAnnouncement(
            payload=models.Announcement(
                content=expected_message,
                color=enums.AnnouncementColor.GREEN,
            )
        )
    )
    # Shoutout は呼ばれない
    mock_service_caller.call.assert_has_awaits([fetch_call, announce_call])
    assert mock_service_caller.call.await_count == 2


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_main_only_shoutout(
    mock_sleep: AsyncMock,
    auto_interception: AutoInterception,
    user_config_data_shoutout_only: ConfigData,
    mock_raid_event: events.RaidDetected,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: シャウトアウトのみ有効な場合のフローを確認します。"""
    # Arrange
    await auto_interception.set_user_config(user_config_data_shoutout_only)
    await auto_interception._raid_event_queue.put(mock_raid_event)
    mock_service_caller.call.side_effect = [None]  # Shoutout

    # Act
    await auto_interception._main()

    # Assert
    assert auto_interception._raid_event_queue.empty()
    assert auto_interception.user_config is not None  # user_config がセットされていることを確認
    mock_sleep.assert_awaited_once_with(auto_interception.user_config.reaction_delay.total_seconds())

    # FetchStreamInfo は呼ばれない
    shoutout_call = call(services.Shoutout(payload=TEST_RAIDER))
    mock_service_caller.call.assert_has_awaits([shoutout_call])
    assert mock_service_caller.call.await_count == 1


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_main_announcement_no_game(
    mock_sleep: AsyncMock,
    auto_interception: AutoInterception,
    user_config_data_full: ConfigData,  # アナウンス有効な設定を使用
    mock_raid_event: events.RaidDetected,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: FetchStreamInfo が game=None を返した場合のメッセージフォーマットを確認します。"""
    # Arrange
    await auto_interception.set_user_config(user_config_data_full)
    await auto_interception._raid_event_queue.put(mock_raid_event)
    # FetchStreamInfo が game=None の情報を返すように設定
    mock_service_caller.call.side_effect = [TEST_STREAM_INFO_NO_GAME, None, None]

    # Act
    await auto_interception._main()

    # Assert
    mock_sleep.assert_awaited_once()
    fetch_call = call(services.FetchStreamInfo(payload=TEST_RAIDER))
    # メッセージ内の {game} が "???" に置き換わることを期待
    expected_message = "Thanks Raider_Test for raiding! Check them out playing ???!"
    announce_call = call(
        services.PostAnnouncement(
            payload=models.Announcement(
                content=expected_message,
                color=enums.AnnouncementColor.BLUE,
            )
        )
    )
    shoutout_call = call(services.Shoutout(payload=TEST_RAIDER))
    mock_service_caller.call.assert_has_awaits([fetch_call, announce_call, shoutout_call])


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_main_runtime_error_on_announce(
    mock_sleep: AsyncMock,
    auto_interception: AutoInterception,
    user_config_data_full: ConfigData,
    mock_raid_event: events.RaidDetected,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: PostAnnouncement で RuntimeError が発生した場合の処理を確認します。"""
    # Arrange
    await auto_interception.set_user_config(user_config_data_full)
    await auto_interception._raid_event_queue.put(mock_raid_event)
    error_message = "Failed to post announcement"
    # FetchStreamInfo は成功、PostAnnouncement でエラー、Shoutout は成功
    mock_service_caller.call.side_effect = [
        TEST_STREAM_INFO,
        RuntimeError(error_message),
        None,
    ]

    # Act
    await auto_interception._main()

    # Assert
    assert auto_interception._raid_event_queue.empty()
    mock_sleep.assert_awaited_once()

    # サービス呼び出しを確認
    fetch_call = call(services.FetchStreamInfo(payload=TEST_RAIDER))
    expected_message = "Thanks Raider_Test for raiding! Check them out playing Test Game!"
    expected_announce_payload = models.Announcement(
        content=expected_message,
        color=enums.AnnouncementColor.BLUE,  # user_config_data_full の設定に合わせる
    )
    announce_call = call(services.PostAnnouncement(payload=expected_announce_payload))
    mock_service_caller.call.assert_has_awaits([fetch_call, announce_call])  # Shoutout は呼ばれない
    assert mock_service_caller.call.await_count == 2  # 呼び出し回数も修正


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_main_runtime_error_on_shoutout(
    mock_sleep: AsyncMock,
    auto_interception: AutoInterception,
    user_config_data_full: ConfigData,
    mock_raid_event: events.RaidDetected,
    mock_service_caller: AsyncMock,
) -> None:
    """_main: Shoutout で RuntimeError が発生した場合の処理を確認します。"""
    # Arrange
    await auto_interception.set_user_config(user_config_data_full)
    await auto_interception._raid_event_queue.put(mock_raid_event)
    error_message = "Failed to shoutout"
    # FetchStreamInfo, PostAnnouncement は成功、Shoutout でエラー
    mock_service_caller.call.side_effect = [
        TEST_STREAM_INFO,
        None,
        RuntimeError(error_message),
    ]

    # Act
    await auto_interception._main()

    # Assert
    assert auto_interception._raid_event_queue.empty()
    mock_sleep.assert_awaited_once()

    # サービス呼び出しを確認
    fetch_call = call(services.FetchStreamInfo(payload=TEST_RAIDER))
    expected_message = "Thanks Raider_Test for raiding! Check them out playing Test Game!"
    expected_announce_payload = models.Announcement(
        content=expected_message,
        color=enums.AnnouncementColor.BLUE,  # user_config_data_full の設定に合わせる
    )
    announce_call = call(services.PostAnnouncement(payload=expected_announce_payload))
    shoutout_call = call(services.Shoutout(payload=TEST_RAIDER))  # エラーが発生する呼び出し
    mock_service_caller.call.assert_has_awaits([fetch_call, announce_call, shoutout_call])
