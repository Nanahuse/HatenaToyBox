# mypy: disable-error-code="attr-defined"

import asyncio
import logging
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import twitchio.errors as twitchio_errors
from pydantic import SecretStr
from twitchio.ext import commands

from features.communicator.twitchio_adaptor import exceptions
from features.communicator.twitchio_adaptor.base_twitch_client import BaseTwitchClient
from features.communicator.twitchio_adaptor.custom_commands import StreamInfoCommand
from features.communicator.twitchio_adaptor.stream_info_manager import StreamInfoManager
from schemas import models
from utils.model_file import ModelFile

# --- Constants ---
TEST_CHANNEL = "testchannel"
TEST_TOKEN_VALUE = "testtoken123"
TEST_STORAGE_NAME = "default"


# --- Fixtures ---


@pytest.fixture
def mock_logger() -> MagicMock:
    """モックされたロガーインスタンスを提供します。"""
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_token() -> SecretStr:
    """モックされたトークンを提供します。"""
    return SecretStr(TEST_TOKEN_VALUE)


@pytest.fixture
def mock_publisher() -> AsyncMock:
    """モックされた EventPublisher を提供します。"""
    return AsyncMock(spec="common.core.EventPublisher")


@pytest.fixture
def mock_connection_event() -> AsyncMock:
    """モックされた接続イベントを提供します。"""
    event = AsyncMock(spec=asyncio.Event)
    event.is_set.return_value = True  # ほとんどのテストでは接続済みと仮定
    return event


@pytest.fixture
def mock_model_file_cls() -> MagicMock:
    """ModelFile クラス自体をモックします。"""
    return MagicMock(spec=ModelFile)


@pytest.fixture
def mock_model_file_instance() -> MagicMock:
    """ModelFile のインスタンスをモックします。"""
    instance = MagicMock(spec=ModelFile)
    instance.data = None  # デフォルトはデータなし
    instance.update = Mock()
    instance.clear = Mock()
    return instance


@pytest.fixture
def mock_context() -> MagicMock:
    """twitchio.ext.commands.Context をモックします。"""
    context = MagicMock(spec=commands.Context)
    context.author = MagicMock(spec="twitchio.Chatter")
    context.author.name = "testuser"
    context.author.is_broadcaster = False
    context.author.is_mod = False
    return context


@pytest.fixture
def mock_user() -> AsyncMock:
    """チャンネルに関連付けられた twitchio.User オブジェクトをモックします。"""
    user = AsyncMock(spec="twitchio.User")
    user.modify_stream = AsyncMock()
    return user


@pytest.fixture
def stream_info_model() -> models.StreamInfo:
    """テスト用の StreamInfo モデルを提供します。"""
    return models.StreamInfo(
        title="Test Stream Title",
        game=models.Game(game_id="12345", name="Test Game"),
        tags=["tag1", "tag2"],
    )


@pytest.fixture
def stream_info_manager(
    mock_logger: MagicMock,
    mock_token: SecretStr,
    mock_publisher: AsyncMock,
    mock_connection_event: AsyncMock,
    tmp_path: Path,
    mock_model_file_cls: MagicMock,
    mock_model_file_instance: MagicMock,
    mock_user: AsyncMock,
) -> Generator[StreamInfoManager, None, None]:
    """StreamInfoManager のインスタンスを提供します。"""
    # BaseTwitchClient.__init__ をパッチして、初期化時の複雑さを回避
    # ModelFile クラスをパッチして、インスタンスモックを返すようにする
    with (
        patch.object(BaseTwitchClient, "__init__", return_value=None) as mock_base_init,
        patch("features.communicator.twitchio_adaptor.stream_info_manager.ModelFile", mock_model_file_cls),
    ):
        mock_model_file_cls.return_value = mock_model_file_instance

        manager = StreamInfoManager(
            logger=mock_logger,
            token=mock_token,
            channel=TEST_CHANNEL,
            stream_info_storage_directory=tmp_path,
            publisher=mock_publisher,
            connection_event=mock_connection_event,
        )
        # BaseTwitchClient によって通常設定されるか、存在すると仮定される属性を手動で設定
        manager._logger = mock_logger  # ロガーが正しく設定されていることを確認
        manager._BaseTwitchClient__token = mock_token
        manager._BaseTwitchClient__user = mock_user
        manager._connection_event = mock_connection_event
        # テストを簡略化するために is_connected プロパティを直接モック
        # 必要に応じてテストごとにオーバーライド可能
        with patch.object(StreamInfoManager, "is_connected", True, create=True):
            yield manager

    mock_base_init.assert_called_once_with(mock_logger, mock_token, TEST_CHANNEL, mock_connection_event)


# --- Test Cases ---


def test_init(stream_info_manager: StreamInfoManager, mock_logger: MagicMock, tmp_path: Path) -> None:
    """StreamInfoManager の初期化をテストします。"""
    assert stream_info_manager._logger is mock_logger
    assert stream_info_manager._publisher is not None  # フィクスチャから
    assert stream_info_manager._stream_info_storage_directory == tmp_path
    assert stream_info_manager._stream_info_storage == {}


@pytest.mark.asyncio
async def test_info_command_permission_denied(stream_info_manager: StreamInfoManager, mock_context: MagicMock) -> None:
    """ユーザーがモデレーターまたは配信者でない場合、!info コマンドが失敗することをテストします。"""
    mock_context.author.is_broadcaster = False
    mock_context.author.is_mod = False

    await stream_info_manager.info._callback(
        stream_info_manager, mock_context, StreamInfoCommand.SAVE, TEST_STORAGE_NAME
    )

    # ファイル操作や API 呼び出しが試行されなかったことを確認
    assert not stream_info_manager._stream_info_storage


@pytest.mark.asyncio
@pytest.mark.parametrize("is_mod", [True, False])
async def test_info_command_save_new(
    stream_info_manager: StreamInfoManager,
    mock_context: MagicMock,
    mock_logger: MagicMock,
    mock_model_file_cls: MagicMock,
    mock_model_file_instance: MagicMock,
    stream_info_model: models.StreamInfo,
    tmp_path: Path,
    is_mod: bool,  # noqa: FBT001
) -> None:
    """初めて保存する場合の !info save コマンドをテストします。"""
    mock_context.author.is_broadcaster = not is_mod
    mock_context.author.is_mod = is_mod

    # fetch_stream_info をモックしてモデルを返すようにする
    stream_info_manager.fetch_stream_info = AsyncMock(return_value=stream_info_model)  # type:ignore[method-assign]

    await stream_info_manager.info._callback(
        stream_info_manager, mock_context, StreamInfoCommand.SAVE, TEST_STORAGE_NAME
    )

    stream_info_manager.fetch_stream_info.assert_awaited_once_with(None)
    expected_path = tmp_path / f"{TEST_STORAGE_NAME}.json"
    mock_model_file_cls.assert_called_once_with(models.StreamInfo, expected_path, mock_logger)
    assert stream_info_manager._stream_info_storage[TEST_STORAGE_NAME] is mock_model_file_instance
    mock_model_file_instance.update.assert_called_once_with(stream_info_model)


@pytest.mark.asyncio
async def test_info_command_save_existing(
    stream_info_manager: StreamInfoManager,
    mock_context: MagicMock,
    mock_model_file_cls: MagicMock,
    mock_model_file_instance: MagicMock,
    stream_info_model: models.StreamInfo,
) -> None:
    """ストレージエントリが既に存在する場合の !info save コマンドをテストします。"""
    mock_context.author.is_broadcaster = True
    stream_info_manager._stream_info_storage[TEST_STORAGE_NAME] = mock_model_file_instance
    stream_info_manager.fetch_stream_info = AsyncMock(return_value=stream_info_model)  # type:ignore[method-assign]

    await stream_info_manager.info._callback(
        stream_info_manager, mock_context, StreamInfoCommand.SAVE, TEST_STORAGE_NAME
    )

    stream_info_manager.fetch_stream_info.assert_awaited_once_with(None)
    mock_model_file_cls.assert_not_called()  # 既存のものを取得するはず
    assert stream_info_manager._stream_info_storage[TEST_STORAGE_NAME] is mock_model_file_instance
    mock_model_file_instance.update.assert_called_once_with(stream_info_model)


@pytest.mark.asyncio
async def test_info_command_load_no_data(
    stream_info_manager: StreamInfoManager,
    mock_context: MagicMock,
    mock_logger: MagicMock,
    mock_model_file_cls: MagicMock,
    mock_model_file_instance: MagicMock,
    tmp_path: Path,
) -> None:
    """データが保存されていない場合の !info load コマンドをテストします。"""
    mock_context.author.is_mod = True
    mock_model_file_instance.data = None  # データがないことを確認

    # _update_stream_info をモックして呼び出されないことを確認
    stream_info_manager._update_stream_info = AsyncMock()  # type:ignore[method-assign]

    await stream_info_manager.info._callback(
        stream_info_manager, mock_context, StreamInfoCommand.LOAD, TEST_STORAGE_NAME
    )

    expected_path = tmp_path / f"{TEST_STORAGE_NAME}.json"
    mock_model_file_cls.assert_called_once_with(models.StreamInfo, expected_path, mock_logger)
    assert stream_info_manager._stream_info_storage[TEST_STORAGE_NAME] is mock_model_file_instance
    stream_info_manager._update_stream_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_info_command_load_success(
    stream_info_manager: StreamInfoManager,
    mock_context: MagicMock,
    mock_model_file_instance: MagicMock,
    stream_info_model: models.StreamInfo,
) -> None:
    """!info load コマンドが正常に配信情報をロードし、更新することをテストします。"""
    mock_context.author.is_broadcaster = True
    mock_model_file_instance.data = stream_info_model
    stream_info_manager._stream_info_storage[TEST_STORAGE_NAME] = mock_model_file_instance

    # _update_stream_info をモック
    stream_info_manager._update_stream_info = AsyncMock()  # type:ignore[method-assign]

    await stream_info_manager.info._callback(
        stream_info_manager, mock_context, StreamInfoCommand.LOAD, TEST_STORAGE_NAME
    )

    stream_info_manager._update_stream_info.assert_awaited_once_with(stream_info_model)


@pytest.mark.asyncio
async def test_info_command_load_update_fails(
    stream_info_manager: StreamInfoManager,
    mock_context: MagicMock,
    mock_model_file_instance: MagicMock,
    stream_info_model: models.StreamInfo,
) -> None:
    """基盤となる _update_stream_info が失敗した場合の !info load コマンドをテストします。"""
    mock_context.author.is_mod = True
    mock_model_file_instance.data = stream_info_model
    stream_info_manager._stream_info_storage[TEST_STORAGE_NAME] = mock_model_file_instance

    # _update_stream_info をモックしてエラーを発生させる
    update_error = exceptions.StreamInfoUpdateError("API failed")
    stream_info_manager._update_stream_info = AsyncMock(side_effect=update_error)  # type:ignore[method-assign]

    await stream_info_manager.info._callback(
        stream_info_manager, mock_context, StreamInfoCommand.LOAD, TEST_STORAGE_NAME
    )

    stream_info_manager._update_stream_info.assert_awaited_once_with(stream_info_model)


@pytest.mark.asyncio
async def test_info_command_clear(
    stream_info_manager: StreamInfoManager,
    mock_context: MagicMock,
    mock_logger: MagicMock,
    mock_model_file_cls: MagicMock,
    mock_model_file_instance: MagicMock,
    tmp_path: Path,
) -> None:
    """!info clear コマンドをテストします。"""
    mock_context.author.is_broadcaster = True

    await stream_info_manager.info._callback(
        stream_info_manager, mock_context, StreamInfoCommand.CLEAR, TEST_STORAGE_NAME
    )

    expected_path = tmp_path / f"{TEST_STORAGE_NAME}.json"
    mock_model_file_cls.assert_called_once_with(models.StreamInfo, expected_path, mock_logger)
    assert stream_info_manager._stream_info_storage[TEST_STORAGE_NAME] is mock_model_file_instance
    mock_model_file_instance.clear.assert_called_once()


@pytest.mark.asyncio
async def test_info_command_unknown_action(stream_info_manager: StreamInfoManager, mock_context: MagicMock) -> None:
    """未知のアクションを持つ !info コマンドをテストします。"""
    mock_context.author.is_mod = True

    # 副作用を持つ可能性のあるメソッドをモックして、呼び出されないことを確認
    stream_info_manager.fetch_stream_info = AsyncMock()  # type:ignore[method-assign]
    stream_info_manager._update_stream_info = AsyncMock()  # type:ignore[method-assign]
    mock_model_file_instance = stream_info_manager._stream_info_storage.setdefault(
        TEST_STORAGE_NAME, MagicMock(spec=ModelFile)
    )

    await stream_info_manager.info._callback(stream_info_manager, mock_context, "unknown_action", TEST_STORAGE_NAME)

    # モデルファイルを取得/作成するが、update/clear/fetch などは呼び出さないはず
    assert TEST_STORAGE_NAME in stream_info_manager._stream_info_storage
    stream_info_manager.fetch_stream_info.assert_not_awaited()
    stream_info_manager._update_stream_info.assert_not_awaited()
    mock_model_file_instance.update.assert_not_called()
    mock_model_file_instance.clear.assert_not_called()


@pytest.mark.asyncio
async def test_update_stream_info_not_connected(
    stream_info_manager: StreamInfoManager, stream_info_model: models.StreamInfo
) -> None:
    """接続されていない場合、_update_stream_info が NotConnectedError を発生させることをテストします。"""
    with patch.object(StreamInfoManager, "is_connected", False, create=True):  # noqa: SIM117
        with pytest.raises(exceptions.NotConnectedError, match="StreamInfo update failed."):
            await stream_info_manager._update_stream_info(stream_info_model)


@pytest.mark.asyncio
async def test_update_stream_info_success_with_game(
    stream_info_manager: StreamInfoManager,
    stream_info_model: models.StreamInfo,
    mock_user: AsyncMock,
    mock_token: SecretStr,
) -> None:
    """_update_stream_info がゲーム情報付きで modify_stream を正常に呼び出すことをテストします。"""
    assert stream_info_model.game is not None  # 前提条件

    await stream_info_manager._update_stream_info(stream_info_model)

    mock_user.modify_stream.assert_awaited_once_with(
        mock_token.get_secret_value(),
        game_id=stream_info_model.game.game_id,
        title=stream_info_model.title,
        tags=stream_info_model.tags,
    )


@pytest.mark.asyncio
async def test_update_stream_info_success_no_game(
    stream_info_manager: StreamInfoManager,
    stream_info_model: models.StreamInfo,
    mock_user: AsyncMock,
    mock_token: SecretStr,
) -> None:
    """_update_stream_info がゲーム情報なしで modify_stream を正常に呼び出すことをテストします。"""
    stream_info_model_no_game = stream_info_model.model_copy(update={"game": None})

    await stream_info_manager._update_stream_info(stream_info_model_no_game)

    mock_user.modify_stream.assert_awaited_once_with(
        mock_token.get_secret_value(),
        game_id=None,
        title=stream_info_model_no_game.title,
        tags=stream_info_model_no_game.tags,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raised_exception", "expected_exception", "error_message"),
    [
        (
            twitchio_errors.Unauthorized("Auth failed"),
            exceptions.StreamInfoUpdateError,
            "Auth failed",
        ),
        (
            twitchio_errors.HTTPException("Bad request"),
            exceptions.StreamInfoUpdateError,
            "Bad request",
        ),
        (ValueError("Some other error"), exceptions.UnhandledError, "Some other error"),
    ],
)
async def test_update_stream_info_error_wrapping(
    stream_info_manager: StreamInfoManager,
    stream_info_model: models.StreamInfo,
    mock_user: AsyncMock,
    raised_exception: Exception,
    expected_exception: type[exceptions.TwitchioAdaptorError],
    error_message: str,
) -> None:
    """_update_stream_info が twitchio やその他のエラーを正しくラップすることをテストします。"""
    mock_user.modify_stream.side_effect = raised_exception

    with pytest.raises(expected_exception) as exc_info:
        await stream_info_manager._update_stream_info(stream_info_model)

    assert error_message in str(exc_info.value)
    assert exc_info.value.__cause__ is raised_exception
