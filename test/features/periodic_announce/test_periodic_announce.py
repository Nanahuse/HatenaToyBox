import datetime
from collections.abc import Generator
from typing import cast
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, call, patch

import pytest

from common.core import Hub, ServiceCaller
from common.feature import ConfigData, Feature
from features.periodic_announce.announcement_task import AnnouncementTask
from features.periodic_announce.config import UserConfig
from features.periodic_announce.periodic_announce import AnnouncementHandler as RealAnnouncementHandler
from features.periodic_announce.periodic_announce import PeriodicAnnounce
from schemas import enums, models, services

# --- テスト用定数 ---
TEST_INTERVAL_1 = datetime.timedelta(minutes=1)
TEST_INITIAL_WAIT_1 = datetime.timedelta(seconds=5)
TEST_MESSAGE_1 = "First announcement!"
TEST_COLOR_1 = enums.AnnouncementColor.BLUE

TEST_INTERVAL_2 = datetime.timedelta(hours=1)
TEST_INITIAL_WAIT_2 = datetime.timedelta(seconds=0)
TEST_MESSAGE_2 = "Second announcement (no color)."

# --- フィクスチャ ---


@pytest.fixture
def mock_hub() -> MagicMock:
    """モックされた Hub インスタンスを提供します。"""
    hub = MagicMock(spec=Hub)
    hub.create_caller.return_value = AsyncMock(spec=ServiceCaller)
    return hub


@pytest.fixture
def mock_service_caller(mock_hub: MagicMock) -> AsyncMock:
    """モックされた ServiceCaller インスタンスを提供します。"""
    return cast("AsyncMock", mock_hub.create_caller.return_value)


@pytest.fixture
def mock_system_config_data() -> ConfigData:
    """モックされた SystemConfig データを提供します (この機能では未使用)。"""
    return {"version": 0}


@pytest.fixture
def mock_user_config_data_valid() -> ConfigData:
    """有効なアナウンスタスクリストを含む UserConfig データを提供します。"""
    return {
        "version": 0,
        "announcements": [
            {
                "message": TEST_MESSAGE_1,
                "initial_wait": TEST_INITIAL_WAIT_1.total_seconds(),  # 秒数で渡す
                "interval": TEST_INTERVAL_1.total_seconds(),  # 秒数で渡す
                "color": TEST_COLOR_1.value,  # enum の値
            },
            {
                "message": TEST_MESSAGE_2,
                "initial_wait": TEST_INITIAL_WAIT_2.total_seconds(),
                "interval": TEST_INTERVAL_2.total_seconds(),
                # color は None
            },
        ],
    }


@pytest.fixture
def mock_user_config_valid(mock_user_config_data_valid: ConfigData) -> UserConfig:
    """有効な UserConfig インスタンスを提供します。"""
    return UserConfig.model_validate(mock_user_config_data_valid)


# --- 依存クラスのモック用フィクスチャ ---


@pytest.fixture(autouse=True)
def mock_routine_manager_cls() -> Generator[MagicMock, None, None]:
    """routines.RoutineManager クラスをモックします。"""
    patcher = patch("features.periodic_announce.periodic_announce.routines.RoutineManager", autospec=True)
    mock_cls = patcher.start()
    # メソッドをモック
    mock_cls.return_value.add = Mock()
    mock_cls.return_value.start = Mock()
    mock_cls.return_value.clear = Mock()
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_routine_manager_instance(mock_routine_manager_cls: MagicMock) -> MagicMock:
    """モックされた RoutineManager インスタンスを提供します。"""
    return cast("MagicMock", mock_routine_manager_cls.return_value)


@pytest.fixture(autouse=True)
def mock_announcement_handler_cls() -> Generator[MagicMock, None, None]:
    """AnnouncementHandler クラスをモックします。"""
    patcher = patch("features.periodic_announce.periodic_announce.AnnouncementHandler", autospec=True)
    mock_cls = patcher.start()
    # main メソッドを AsyncMock にする
    mock_cls.return_value.main = AsyncMock()
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_announcement_handler_instance(mock_announcement_handler_cls: MagicMock) -> MagicMock:
    """モックされた AnnouncementHandler インスタンスを提供します。"""
    return cast("MagicMock", mock_announcement_handler_cls.return_value)


@pytest.fixture
def periodic_announce_feature(
    mock_hub: MagicMock,
    mock_system_config_data: ConfigData,
    # autouse=True なので自動適用
    mock_routine_manager_cls: MagicMock,  # noqa: ARG001
    mock_announcement_handler_cls: MagicMock,  # noqa: ARG001
) -> PeriodicAnnounce:
    """テスト対象の PeriodicAnnounce インスタンスを提供します。"""
    return PeriodicAnnounce(mock_hub, mock_system_config_data)


# --- AnnouncementHandler のテスト ---


@pytest.mark.asyncio
async def test_announcement_handler_main(mock_service_caller: AsyncMock) -> None:
    """AnnouncementHandler.main が sleep し、サービスを呼び出すことをテストします。"""
    task = AnnouncementTask(
        message=TEST_MESSAGE_1,
        initial_wait=TEST_INITIAL_WAIT_1,
        interval=TEST_INTERVAL_1,
        color=TEST_COLOR_1,
    )
    handler = RealAnnouncementHandler(mock_service_caller, task)  # モックではなく実際のクラスを使用

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await handler.main()

        # Assert sleep
        mock_sleep.assert_awaited_once_with(TEST_INITIAL_WAIT_1.total_seconds())
        # Assert service call
        expected_payload = models.Announcement(content=TEST_MESSAGE_1, color=TEST_COLOR_1)
        mock_service_caller.call.assert_awaited_once_with(services.PostAnnouncement(payload=expected_payload))


# --- PeriodicAnnounce のテスト ---


def test_initialization(
    periodic_announce_feature: PeriodicAnnounce,
    mock_hub: MagicMock,
    mock_service_caller: AsyncMock,
    mock_routine_manager_cls: MagicMock,
    mock_routine_manager_instance: MagicMock,
) -> None:
    """PeriodicAnnounce が正しく初期化されるかをテストします。"""
    # Hub の呼び出し確認
    mock_hub.create_caller.assert_called_once()
    assert periodic_announce_feature._service_caller is mock_service_caller

    # RoutineManager の初期化確認
    mock_routine_manager_cls.assert_called_once_with()
    assert periodic_announce_feature._routine_manager is mock_routine_manager_instance

    # user_config が None であること
    assert periodic_announce_feature.user_config is None


@pytest.mark.asyncio
async def test_set_user_config_none(
    periodic_announce_feature: PeriodicAnnounce,
    mock_routine_manager_instance: MagicMock,
) -> None:
    """ユーザー設定が None の場合に RoutineManager がクリアされることをテストします。"""
    # Arrange: 最初に何か設定されている状態を作る (オプション)
    # await periodic_announce_feature.set_user_config(mock_user_config_data_valid)
    # mock_routine_manager_instance.clear.reset_mock() # 必要ならリセット

    # Act: None を設定
    with patch.object(Feature, "set_user_config", new_callable=AsyncMock, return_value=True) as mock_super_set:
        result = await periodic_announce_feature.set_user_config(None)

    # Assert
    mock_super_set.assert_awaited_once_with(None)
    assert result is True
    assert periodic_announce_feature.user_config is None
    mock_routine_manager_instance.clear.assert_called_once_with()
    mock_routine_manager_instance.add.assert_not_called()
    mock_routine_manager_instance.start.assert_not_called()


@pytest.mark.asyncio
async def test_set_user_config_valid(
    periodic_announce_feature: PeriodicAnnounce,
    mock_user_config_data_valid: ConfigData,
    mock_user_config_valid: UserConfig,  # 検証用にインスタンスも取得
    mock_service_caller: AsyncMock,  # AnnouncementHandler の初期化に必要
    mock_routine_manager_instance: MagicMock,
    mock_announcement_handler_cls: MagicMock,
) -> None:
    """有効なユーザー設定が適用され、RoutineManager が設定されることをテストします。"""
    # Act
    await periodic_announce_feature.set_user_config(mock_user_config_data_valid)

    # RoutineManager の clear が呼ばれたか
    mock_routine_manager_instance.clear.assert_called_once_with()

    # AnnouncementHandler と RoutineManager.add の呼び出しを確認
    expected_handler_calls = []
    expected_add_calls = []
    for task in mock_user_config_valid.announcements:
        expected_handler_calls.append(call(mock_service_caller, task))
        expected_add_calls.append(call(ANY, task.interval))  # ANY を使用

    assert mock_announcement_handler_cls.call_count == len(mock_user_config_valid.announcements)
    mock_announcement_handler_cls.assert_has_calls(expected_handler_calls, any_order=True)

    assert mock_routine_manager_instance.add.call_count == len(mock_user_config_valid.announcements)
    mock_routine_manager_instance.add.assert_has_calls(expected_add_calls, any_order=True)

    # RoutineManager.start が呼ばれたか
    mock_routine_manager_instance.start.assert_called_once_with()


@pytest.mark.asyncio
async def test_set_user_config_super_returns_false(
    periodic_announce_feature: PeriodicAnnounce,
    mock_user_config_data_valid: ConfigData,
    mock_routine_manager_instance: MagicMock,
) -> None:
    """super().set_user_config が False を返した場合の動作を確認します。"""
    # Act
    with patch.object(Feature, "set_user_config", new_callable=AsyncMock, return_value=False) as mock_super_set:
        result = await periodic_announce_feature.set_user_config(mock_user_config_data_valid)

    # Assert
    mock_super_set.assert_awaited_once_with(mock_user_config_data_valid)
    assert result is False
    # RoutineManager のメソッドが呼ばれないこと
    mock_routine_manager_instance.clear.assert_not_called()
    mock_routine_manager_instance.add.assert_not_called()
    mock_routine_manager_instance.start.assert_not_called()
