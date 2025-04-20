# test/features/configuration_manager/test_configuration_manager.py

import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call, mock_open, patch

import pytest
import pytest_asyncio

from common.core import Hub, ServiceCaller
from common.feature import Config, ConfigData, Feature, SetConfigService
from features.configuration_manager.configuration_manager import ConfigurationManager

# --- テストデータ ---
TEST_CONFIG_FILE_PATH = Path("/fake/settings.json")
TEST_CONFIG_CONTENT = {
    "feature_a": {"setting1": "value1", "setting2": 123},
    "feature_b": {"enabled": True},
    "feature_c": None,  # 設定データが None のケース
}
TEST_CONFIG_JSON = json.dumps(TEST_CONFIG_CONTENT)

# --- Fixtures ---


@pytest.fixture
def mock_hub() -> MagicMock:
    """Hub のモックを提供します。"""
    hub = MagicMock(spec=Hub)
    hub.create_caller.return_value = AsyncMock(spec=ServiceCaller)
    # add_event_handler など、他の Hub のメソッドはここでは不要
    return hub


@pytest.fixture
def mock_caller(mock_hub: MagicMock) -> AsyncMock:
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
    # user_setting_file を含める
    return ConfigData({"version": 0, "user_setting_file": str(TEST_CONFIG_FILE_PATH)})


@pytest_asyncio.fixture
async def configuration_manager(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_logger: MagicMock,
) -> AsyncGenerator[ConfigurationManager, None]:
    """テスト対象の ConfigurationManager インスタンスを提供します。"""
    instance = ConfigurationManager(mock_hub, system_config_data)
    instance._logger = mock_logger  # ロガーを差し替え
    yield instance
    # ConfigurationManager には非同期のクリーンアップ処理はないため、teardown は不要


# --- テストケース ---


def test_init(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_caller: AsyncMock,
) -> None:
    """__init__: 依存関係の呼び出しと内部状態の初期化を確認します。"""
    # Arrange & Act
    instance = ConfigurationManager(mock_hub, system_config_data)

    # Assert
    assert isinstance(instance, Feature)
    assert instance._caller is mock_caller
    # SystemConfig が正しくパースされたか確認
    assert instance.system_config.user_setting_file == TEST_CONFIG_FILE_PATH
    # ServiceCaller が作成されたか確認
    mock_hub.create_caller.assert_called_once()


@pytest.mark.asyncio
# Feature.run と ConfigurationManager.load_config をモック
@patch.object(Feature, "run", new_callable=AsyncMock)
@patch.object(ConfigurationManager, "load_config", new_callable=AsyncMock)
async def test_run(
    mock_load_config: AsyncMock,
    mock_super_run: AsyncMock,
    configuration_manager: ConfigurationManager,
) -> None:
    """run: load_config と super().run() が await されることを確認します。"""
    # Arrange (特になし)

    # Act
    await configuration_manager.run()

    # Assert
    mock_load_config.assert_awaited_once()  # load_config が呼ばれたか
    mock_super_run.assert_awaited_once()  # 基底クラスの run が呼ばれたか


@pytest.mark.asyncio
# Path.open と json.load をモック
@patch("pathlib.Path.open", new_callable=mock_open, read_data=TEST_CONFIG_JSON)
@patch("json.load")
async def test_load_config_success(
    mock_json_load: MagicMock,
    mock_file_open: MagicMock,
    configuration_manager: ConfigurationManager,
    mock_caller: AsyncMock,
) -> None:
    """load_config: ファイルを正常に読み込み、設定ごとにサービスを呼び出すことを確認します。"""
    # Arrange
    # json.load がテストデータを返すように設定
    mock_json_load.return_value = TEST_CONFIG_CONTENT
    mock_caller.call.reset_mock()  # 呼び出し履歴をクリア

    # Act
    await configuration_manager.load_config()

    # Assert
    # 1. ファイルオープン確認
    mock_file_open.assert_called_once_with("r", encoding="utf-8")

    # 2. json.load 確認
    # mock_open はファイルハンドルを返すので、そのハンドルで load が呼ばれる
    mock_json_load.assert_called_once_with(mock_file_open())

    # 3. サービス呼び出し確認
    expected_service_calls = [
        call(SetConfigService(payload=Config(name="feature_a", data=TEST_CONFIG_CONTENT["feature_a"]))),
        call(SetConfigService(payload=Config(name="feature_b", data=TEST_CONFIG_CONTENT["feature_b"]))),
        call(SetConfigService(payload=Config(name="feature_c", data=TEST_CONFIG_CONTENT["feature_c"]))),
    ]
    mock_caller.call.assert_has_awaits(expected_service_calls, any_order=True)
    assert mock_caller.call.await_count == len(TEST_CONFIG_CONTENT)


@pytest.mark.asyncio
@patch("pathlib.Path.open", side_effect=FileNotFoundError("File not found"))
async def test_load_config_file_not_found(
    mock_file_open: MagicMock,
    configuration_manager: ConfigurationManager,
    mock_caller: AsyncMock,
) -> None:
    """load_config: 設定ファイルが見つからない場合に FileNotFoundError が発生することを確認します。"""
    # Arrange (特になし)

    # Act & Assert
    with pytest.raises(FileNotFoundError, match="File not found"):
        await configuration_manager.load_config()

    # ファイルオープンが試みられたことを確認
    mock_file_open.assert_called_once_with("r", encoding="utf-8")
    # サービス呼び出しは行われない
    mock_caller.call.assert_not_called()


@pytest.mark.asyncio
@patch("pathlib.Path.open", new_callable=mock_open, read_data="invalid json")
@patch("json.load", side_effect=json.JSONDecodeError("Decode error", "", 0))
async def test_load_config_invalid_json(
    mock_json_load: MagicMock,
    mock_file_open: MagicMock,
    configuration_manager: ConfigurationManager,
    mock_caller: AsyncMock,
) -> None:
    """load_config: JSON のデコードに失敗した場合に JSONDecodeError が発生することを確認します。"""
    # Arrange (特になし)

    # Act & Assert
    with pytest.raises(json.JSONDecodeError):
        await configuration_manager.load_config()

    # ファイルオープンと json.load が試みられたことを確認
    mock_file_open.assert_called_once_with("r", encoding="utf-8")
    mock_json_load.assert_called_once_with(mock_file_open())
    # サービス呼び出しは行われない
    mock_caller.call.assert_not_called()


@pytest.mark.asyncio
@patch("pathlib.Path.open", new_callable=mock_open, read_data="{}")  # 空のJSON
@patch("json.load")
async def test_load_config_empty_file(
    mock_json_load: MagicMock,
    mock_file_open: MagicMock,
    configuration_manager: ConfigurationManager,
    mock_caller: AsyncMock,
) -> None:
    """load_config: 設定ファイルが空の JSON オブジェクトの場合、サービス呼び出しが行われないことを確認します。"""
    # Arrange
    mock_json_load.return_value = {}  # 空の辞書を返す
    mock_caller.call.reset_mock()

    # Act
    await configuration_manager.load_config()

    # Assert
    # ファイルオープンと json.load は行われる
    mock_file_open.assert_called_once_with("r", encoding="utf-8")
    mock_json_load.assert_called_once_with(mock_file_open())
    # サービス呼び出しは行われない
    mock_caller.call.assert_not_called()
