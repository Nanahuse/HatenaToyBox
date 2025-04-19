from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from common.core import Hub
from common.feature import Config, ConfigData, FeatureProtocol, SetConfigService
from features.auto_interception import AutoInterception
from features.clip_notificator import ClipNotificator
from features.communicator import Communicator
from features.configuration_manager import ConfigurationManager
from features.door_bell import DoorBell
from features.feature_manager import FeatureManager
from features.message_filter import MessageFilter
from features.message_translator import MessageTranslator
from features.periodic_announce import PeriodicAnnounce
from features.sound_player import SoundPlayer

# --- テスト用定数 ---
TEST_CONFIG_FILE = Path("/fake/config.json")
# 各 Feature の名前と、load_system_config が返す想定のダミー設定データ
MOCK_SYSTEM_CONFIGS: dict[str, ConfigData] = {
    "AutoInterception": {"version": 0, "dummy_sys_key_ai": "value_ai"},
    "ClipNotificator": {"version": 0, "dummy_sys_key_cn": "value_cn"},
    "Communicator": {"version": 0, "dummy_sys_key_comm": "value_comm"},
    "ConfigurationManager": {"version": 0, "dummy_sys_key_confm": "value_confm"},
    "DoorBell": {"version": 0, "dummy_sys_key_db": "value_db"},
    "MessageFilter": {"version": 0, "dummy_sys_key_mf": "value_mf"},
    "MessageTranslator": {"version": 0, "dummy_sys_key_mt": "value_mt"},
    "PeriodicAnnounce": {"version": 0, "dummy_sys_key_pa": "value_pa"},
    "SoundPlayer": {"version": 0, "dummy_sys_key_sp": "value_sp"},
}
# FeatureManager が管理する Feature クラスのリスト
FEATURE_CLASSES: list[type[FeatureProtocol]] = [
    AutoInterception,
    ClipNotificator,
    Communicator,
    ConfigurationManager,
    DoorBell,
    MessageFilter,
    MessageTranslator,
    PeriodicAnnounce,
    SoundPlayer,
]
FEATURE_CLASS_PATHS: dict[str, str] = {
    cls.__name__: f"features.feature_manager.{cls.__name__}" for cls in FEATURE_CLASSES
}

# --- フィクスチャ ---


@pytest.fixture
def mock_hub() -> MagicMock:
    """モックされた Hub インスタンスを提供します。"""
    hub = MagicMock(spec=Hub)
    hub.add_service_handler = Mock()
    return hub


@pytest.fixture
def mock_config_file_path() -> Path:
    """テスト用の設定ファイルパスを提供します。"""
    return TEST_CONFIG_FILE


# --- 依存関係のモック用フィクスチャ ---


@pytest.fixture
def mock_json_load() -> Generator[MagicMock, None, None]:
    """json.load 関数をモックします。"""
    patcher = patch("features.feature_manager.json.load", return_value=MOCK_SYSTEM_CONFIGS)
    mock_func = patcher.start()
    yield mock_func
    patcher.stop()


@pytest.fixture
def mock_path_open() -> Generator[MagicMock, None, None]:
    """Path(...).open をモックします。"""
    # mock_open はファイルの内容を読み取る場合に便利だが、ここでは json.load を
    # 直接モックするので、open が呼び出されたことの確認とコンテキストマネージャの
    # 動作だけをシミュレートすれば良い。
    # MagicMock を使ってコンテキストマネージャプロトコル (__enter__, __exit__) を模倣する。
    mock_file = MagicMock()
    mock_file.__enter__.return_value = mock_file  # __enter__ は自身 (ファイルオブジェクト) を返す
    mock_file.__exit__.return_value = None  # __exit__ は通常 None を返す
    patcher = patch("features.feature_manager.Path.open", return_value=mock_file)
    mock_open_func = patcher.start()
    yield mock_open_func
    patcher.stop()


@pytest.fixture
def mock_feature_classes() -> Generator[dict[str, MagicMock], None, None]:
    """各 Feature クラスをモックします。"""
    mocks: dict[str, MagicMock] = {}
    patchers: list[Any] = []
    try:
        for name, path in FEATURE_CLASS_PATHS.items():
            patcher = patch(path, autospec=True)
            mock_cls = patcher.start()
            # __init__ は MagicMock が自動で処理
            mock_cls.__name__ = name
            # run と set_user_config を AsyncMock にする
            mock_cls.return_value.run = AsyncMock(name=f"{name}().run")
            mock_cls.return_value.set_user_config = AsyncMock(name=f"{name}().set_user_config")
            mocks[name] = mock_cls
            patchers.append(patcher)
        yield mocks
    finally:
        for patcher in patchers:
            patcher.stop()


@pytest.fixture
def mock_feature_instances(mock_feature_classes: dict[str, MagicMock]) -> dict[str, MagicMock]:
    """モックされた各 Feature クラスのインスタンスを提供します。"""
    return {name: mock_cls.return_value for name, mock_cls in mock_feature_classes.items()}


@pytest.fixture
def mock_asyncio_gather() -> Generator[AsyncMock, None, None]:
    """asyncio.gather 関数をモックします。"""
    patcher = patch("features.feature_manager.asyncio.gather", new_callable=AsyncMock)
    mock_func = patcher.start()
    yield mock_func
    patcher.stop()


@pytest.fixture
def feature_manager(
    mock_hub: MagicMock,
    mock_config_file_path: Path,
    # 以下のモックは自動適用または上記で呼び出される
    mock_json_load: MagicMock,  # noqa: ARG001
    mock_path_open: MagicMock,  # noqa: ARG001
    mock_feature_classes: dict[str, MagicMock],  # noqa: ARG001
) -> FeatureManager:
    """テスト対象の FeatureManager インスタンスを提供します。"""
    # __init__ 内で load_system_config と Feature のインスタンス化が実行される
    return FeatureManager(mock_hub, mock_config_file_path)


# --- テストケース ---


def test_initialization(
    feature_manager: FeatureManager,  # インスタンスを要求すると __init__ が実行される
    mock_hub: MagicMock,
    mock_config_file_path: Path,  # noqa: ARG001
    mock_path_open: MagicMock,
    mock_json_load: MagicMock,
    mock_feature_classes: dict[str, MagicMock],
    mock_feature_instances: dict[str, MagicMock],
) -> None:
    """FeatureManager が正しく初期化されるかをテストします。"""
    # 1. load_system_config の呼び出し確認
    # Path(config_file).open(...)
    mock_path_open.assert_called_once_with(encoding="utf-8")
    # json.load(f) - open が返したモックファイルオブジェクトが渡される
    mock_json_load.assert_called_once_with(mock_path_open.return_value.__enter__.return_value)

    # 2. 各 Feature クラスのインスタンス化確認
    assert len(feature_manager._features) == len(FEATURE_CLASSES)
    for name, mock_cls in mock_feature_classes.items():
        assert name in feature_manager._features
        # Feature(hub, system_config) で呼び出されたか
        mock_cls.assert_called_once_with(mock_hub, MOCK_SYSTEM_CONFIGS[name])
        # _features にインスタンスが格納されたか
        assert feature_manager._features[name] is mock_feature_instances[name]

    # 3. Hub へのハンドラ登録確認
    mock_hub.add_service_handler.assert_called_once_with(SetConfigService, feature_manager.handle_set_config)


def test_load_system_config(
    mock_config_file_path: Path,
    mock_path_open: MagicMock,
    mock_json_load: MagicMock,
) -> None:
    """load_system_config がファイルを読み込み JSON をパースすることをテストします。"""
    # FeatureManager のインスタンスを直接作成してメソッドを呼び出す
    # (初期化のテストとは独立させるため)
    fm = FeatureManager.__new__(FeatureManager)  # __init__ を呼ばずにインスタンス作成

    result = fm.load_system_config(mock_config_file_path)

    # Path(...).open(...)
    mock_path_open.assert_called_once_with(encoding="utf-8")
    # json.load(f)
    mock_json_load.assert_called_once_with(mock_path_open.return_value.__enter__.return_value)
    # 戻り値が json.load の結果と一致するか
    assert result == MOCK_SYSTEM_CONFIGS


# ファイルが見つからない場合や JSON エラーのテストは、mock_path_open や mock_json_load の
# side_effect を設定することで実装可能だが、ここでは省略。


@pytest.mark.asyncio
async def test_handle_set_config_success(
    feature_manager: FeatureManager,
    mock_feature_instances: dict[str, MagicMock],
) -> None:
    """handle_set_config が対応する feature の set_user_config を呼び出すことをテストします。"""
    target_feature_name = "MessageTranslator"
    user_config_data: ConfigData = {"version": 1, "some_key": "some_value"}
    config = Config(name=target_feature_name, data=user_config_data)

    # 対応する feature のモックインスタンスを取得
    mock_target_instance = mock_feature_instances[target_feature_name]

    # Act
    await feature_manager.handle_set_config(config)

    # Assert
    mock_target_instance.set_user_config.assert_awaited_once_with(user_config_data)

    # 他の feature の set_user_config が呼ばれていないことを確認 (オプション)
    for name, instance in mock_feature_instances.items():
        if name != target_feature_name:
            instance.set_user_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_set_config_unknown_feature(feature_manager: FeatureManager) -> None:
    """handle_set_config が未知の feature 名で ValueError を送出することをテストします。"""
    unknown_feature_name = "NonExistentFeature"
    config = Config(name=unknown_feature_name, data={"version": 0})

    # Act & Assert
    with pytest.raises(ValueError, match=f"Unknown feature: {unknown_feature_name}"):
        await feature_manager.handle_set_config(config)


@pytest.mark.asyncio
async def test_run(
    feature_manager: FeatureManager,
    mock_feature_instances: dict[str, MagicMock],
    mock_asyncio_gather: AsyncMock,
) -> None:
    """run が asyncio.gather で全 feature の run を呼び出すことをテストします。"""
    # Act
    await feature_manager.run()

    # Assert: asyncio.gather が呼び出されたか
    mock_asyncio_gather.assert_awaited_once()

    # Assert: gather に渡された引数を確認
    # gather の最初の位置引数を取得
    assert mock_asyncio_gather.await_args is not None
    args, kwargs = mock_asyncio_gather.await_args

    # 引数の数が feature の数と一致するか
    assert len(args) == len(mock_feature_instances)
