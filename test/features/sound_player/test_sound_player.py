# mypy: disable-error-code="attr-defined"

import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from common.core import Hub
from common.feature import ConfigData, Feature
from features.sound_player.config import UserConfig
from features.sound_player.sound_player import SOUND_INTERVAL, SoundPlayer
from schemas import models, services
from utils.resizable_queue import ResizableQueue

# --- テスト用定数 ---
TEST_SOUND_PATH_VALID = Path("/fake/path/valid.mp3")
TEST_SOUND_PATH_INVALID = Path("/fake/path/invalid.wav")
QUEUE_MAX_SIZE = 10

# --- フィクスチャ ---


@pytest.fixture
def mock_hub() -> MagicMock:
    """モックされた Hub インスタンスを提供します。"""
    hub = MagicMock(spec=Hub)
    hub.add_service_handler = Mock()
    # この機能では Caller/Publisher は使わない
    return hub


@pytest.fixture
def mock_system_config_data() -> ConfigData:
    """モックされた SystemConfig データを提供します (この機能では未使用)。"""
    return {"version": 0}


@pytest.fixture
def mock_user_config_data() -> ConfigData:
    """有効な UserConfig データを提供します。"""
    return {"version": 0, "queue_max": QUEUE_MAX_SIZE}


@pytest.fixture
def mock_user_config(mock_user_config_data: ConfigData) -> UserConfig:
    """有効な UserConfig インスタンスを提供します。"""
    return UserConfig.model_validate(mock_user_config_data)


# --- 依存関係のモック用フィクスチャ ---


@pytest.fixture
def mock_resizable_queue_instance() -> MagicMock:
    """モックされた ResizableQueue インスタンスを作成し、設定します。"""
    instance = MagicMock(spec=ResizableQueue)
    instance.get = AsyncMock()
    instance.put = MagicMock()
    instance.change_maxsize = MagicMock()
    return instance


@pytest.fixture(autouse=True)
def mock_routine_manager_cls() -> Generator[MagicMock, None, None]:
    """routines.RoutineManager クラスをモックします。"""
    patcher = patch("features.sound_player.sound_player.routines.RoutineManager", autospec=True)
    mock_cls = patcher.start()
    mock_cls.return_value.add = Mock()
    mock_cls.return_value.start = Mock()
    mock_cls.return_value.clear = Mock()
    yield mock_cls
    patcher.stop()


@pytest.fixture
def mock_routine_manager_instance(mock_routine_manager_cls: MagicMock) -> MagicMock:
    """モックされた RoutineManager インスタンスを提供します。"""
    return cast("MagicMock", mock_routine_manager_cls.return_value)


@pytest.fixture
def mock_playsound_thread() -> MagicMock:
    """playsound が返すモックスレッドオブジェクトを提供します。"""
    thread = MagicMock()
    # is_alive を複数回呼び出すことを想定し、最初は True、次に False を返すように設定
    thread.is_alive = Mock(side_effect=[True, False])
    return thread


@pytest.fixture
def mock_playsound(mock_playsound_thread: MagicMock) -> Generator[MagicMock, None, None]:
    """playsound3.playsound 関数をモックします。"""
    # パスは sound_player.py が playsound を探す場所
    patcher = patch("features.sound_player.sound_player.playsound", return_value=mock_playsound_thread)
    mock_func = patcher.start()
    yield mock_func
    patcher.stop()


@pytest.fixture
def mock_asyncio_sleep() -> Generator[AsyncMock, None, None]:
    """asyncio.sleep 関数をモックします。"""
    patcher = patch("asyncio.sleep", new_callable=AsyncMock)
    mock_func = patcher.start()
    yield mock_func
    patcher.stop()


@pytest.fixture
def sound_player_feature(
    mock_hub: MagicMock,
    mock_system_config_data: ConfigData,
    mock_resizable_queue_instance: MagicMock,
    # autouse=True なので自動適用
    mock_routine_manager_cls: MagicMock,  # noqa: ARG001
) -> SoundPlayer:
    """テスト対象の SoundPlayer インスタンスを提供します。"""
    # ResizableQueue のインスタンス化をパッチ
    with patch(
        "features.sound_player.sound_player.ResizableQueue",
    ) as mock_resizable_queue_class:
        mock_getitem_result = MagicMock()
        mock_getitem_result.return_value = mock_resizable_queue_instance
        mock_resizable_queue_class.__getitem__ = MagicMock(return_value=mock_getitem_result)

        feature = SoundPlayer(mock_hub, mock_system_config_data)

    assert feature._sound_queue is mock_resizable_queue_instance
    return feature


# --- テストケース ---


def test_initialization(
    sound_player_feature: SoundPlayer,
    mock_hub: MagicMock,
    mock_resizable_queue_instance: MagicMock,
) -> None:
    """SoundPlayer が正しく初期化されるかをテストします。"""
    # Hub の呼び出し確認
    mock_hub.add_service_handler.assert_called_once_with(services.PlaySound, mock_resizable_queue_instance.put)
    # ResizableQueue が設定されたか確認
    assert sound_player_feature._sound_queue is mock_resizable_queue_instance
    # user_config が None であること
    assert sound_player_feature.user_config is None


@pytest.mark.asyncio
async def test_set_user_config_none(
    sound_player_feature: SoundPlayer,
    mock_resizable_queue_instance: MagicMock,
) -> None:
    """ユーザー設定が None の場合に change_maxsize が呼ばれないことをテストします。"""
    # Arrange: 最初に何か設定されている状態を作る (オプション)
    # await sound_player_feature.set_user_config(mock_user_config_data)
    # mock_resizable_queue_instance.change_maxsize.reset_mock()

    # Act: None を設定
    with patch.object(Feature, "set_user_config", new_callable=AsyncMock, return_value=True) as mock_super_set:
        result = await sound_player_feature.set_user_config(None)

    # Assert
    mock_super_set.assert_awaited_once_with(None)
    assert result is True
    assert sound_player_feature.user_config is None
    mock_resizable_queue_instance.change_maxsize.assert_not_called()


@pytest.mark.asyncio
async def test_set_user_config_valid(
    sound_player_feature: SoundPlayer,
    mock_user_config_data: ConfigData,
    mock_user_config: UserConfig,
    mock_resizable_queue_instance: MagicMock,
) -> None:
    """有効なユーザー設定が適用され、キューサイズが変更されることをテストします。"""
    result = await sound_player_feature.set_user_config(mock_user_config_data)

    # Assert
    assert result is True
    assert sound_player_feature.user_config == mock_user_config
    mock_resizable_queue_instance.change_maxsize.assert_called_once_with(mock_user_config.queue_max)


@pytest.mark.asyncio
async def test_set_user_config_super_returns_false(
    sound_player_feature: SoundPlayer,
    mock_user_config_data: ConfigData,
    mock_resizable_queue_instance: MagicMock,
) -> None:
    """super().set_user_config が False を返した場合の動作を確認します。"""
    # Act
    with patch.object(Feature, "set_user_config", new_callable=AsyncMock, return_value=False) as mock_super_set:
        result = await sound_player_feature.set_user_config(mock_user_config_data)

    # Assert
    mock_super_set.assert_awaited_once_with(mock_user_config_data)
    assert result is False
    mock_resizable_queue_instance.change_maxsize.assert_not_called()


@pytest.mark.asyncio
async def test_run(
    sound_player_feature: SoundPlayer,
    mock_routine_manager_instance: MagicMock,
) -> None:
    """run メソッドが RoutineManager を正しく制御するかをテストします。"""
    # Arrange
    with patch.object(Feature, "run", new_callable=AsyncMock) as mock_super_run:
        # Act
        run_task = asyncio.create_task(sound_player_feature.run())
        await asyncio.sleep(0)  # run タスクを開始させる

        # Assert setup and run
        mock_routine_manager_instance.add.assert_called_once_with(sound_player_feature._main, SOUND_INTERVAL)
        mock_routine_manager_instance.start.assert_called_once()
        mock_super_run.assert_awaited_once()  # super().run() が呼ばれたか

        # Assert cleanup on close
        await sound_player_feature.close()  # close を呼び出す
        await run_task  # run タスクの完了を待つ
        mock_routine_manager_instance.clear.assert_called_once()  # clear が呼ばれたか


# --- _main メソッドのテスト ---


@pytest.fixture
def mock_sound() -> models.Sound:
    """テスト用の Sound モデルを提供します。"""
    # Path オブジェクトをモックする
    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = True
    # __str__ をモックしてログ出力で見やすくする (オプション)
    mock_path.__str__.return_value = str(TEST_SOUND_PATH_VALID)
    return models.Sound(path=mock_path)


@pytest.fixture
def mock_sound_invalid_path() -> models.Sound:
    """無効なパスを持つ Sound モデルを提供します。"""
    mock_path = MagicMock(spec=Path)
    mock_path.exists.return_value = False  # 存在しない
    mock_path.is_file.return_value = False
    mock_path.__str__.return_value = str(TEST_SOUND_PATH_INVALID)
    return models.Sound(path=mock_path)


@pytest.mark.asyncio
async def test_main_success(
    sound_player_feature: SoundPlayer,
    mock_resizable_queue_instance: MagicMock,
    mock_sound: models.Sound,
    mock_playsound: MagicMock,
    mock_playsound_thread: MagicMock,
    mock_asyncio_sleep: AsyncMock,
) -> None:
    """_main: 正常にサウンドを再生するケースをテストします。"""
    # Arrange: キューが有効なサウンドを返すように設定
    mock_resizable_queue_instance.get.return_value = mock_sound

    # Act
    await sound_player_feature._main()

    # Assert: キューから取得
    mock_resizable_queue_instance.get.assert_awaited_once()
    # Assert: パスチェック
    mock_sound.path.exists.assert_called_once()
    mock_sound.path.is_file.assert_called_once()
    # Assert: playsound 呼び出し
    mock_playsound.assert_called_once_with(mock_sound.path, block=False)
    # Assert: スレッド状態チェックと sleep
    assert mock_playsound_thread.is_alive.call_count == 2  # side_effect で True, False
    mock_asyncio_sleep.assert_awaited_once_with(0.1)  # is_alive が True の間に1回呼ばれる


@pytest.mark.asyncio
async def test_main_file_not_found(
    sound_player_feature: SoundPlayer,
    mock_resizable_queue_instance: MagicMock,
    mock_sound_invalid_path: models.Sound,
    mock_playsound: MagicMock,
    mock_playsound_thread: MagicMock,
    mock_asyncio_sleep: AsyncMock,
) -> None:
    """_main: サウンドファイルが見つからないケースをテストします。"""
    # Arrange: キューが無効なパスのサウンドを返すように設定
    mock_resizable_queue_instance.get.return_value = mock_sound_invalid_path

    # Act
    await sound_player_feature._main()

    # Assert: キューから取得
    mock_resizable_queue_instance.get.assert_awaited_once()
    # Assert: パスチェック
    mock_sound_invalid_path.path.exists.assert_called_once()
    # is_file は exists が False なら呼ばれないはず (実装による)
    # mock_sound_invalid_path.path.is_file.assert_not_called() # または呼ばれて False を返す

    # Assert: playsound 呼び出し (警告後も再生は試みる)
    mock_playsound.assert_called_once_with(mock_sound_invalid_path.path, block=False)
    # Assert: スレッド状態チェックと sleep (再生試行はするため)
    assert mock_playsound_thread.is_alive.call_count == 2
    mock_asyncio_sleep.assert_awaited_once_with(0.1)
