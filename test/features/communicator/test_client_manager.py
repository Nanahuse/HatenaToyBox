# mypy: disable-error-code="attr-defined"

import asyncio
import datetime
import logging
from asyncio import Event as RealAsyncioEvent
from collections.abc import Generator
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, call, patch

import pytest
from pydantic import SecretStr
from twitchio import AuthenticationError

from common.core import EventPublisher
from features.communicator import constants as communicator_constants
from features.communicator.client_manager import ClientManager, TokenTag
from features.communicator.token_manager import TokenManager as RealTokenManager
from features.communicator.twitchio_adaptor import (
    Client as TwitchioClientProtocol,
)
from features.communicator.twitchio_adaptor import (
    StreamInfoManager as RealStreamInfoManager,
)
from features.communicator.twitchio_adaptor import TwitchClient as RealTwitchClient
from schemas import errors, events, models
from utils.process_manager import Process, ProcessManager

# --- Constants ---
TEST_CHANNEL = "testchannel"
TEST_TOKEN_FILE_DIR = Path("/fake/token/dir")
TEST_STREAM_INFO_DIR = Path("/fake/streaminfo/dir")


# --- Fixtures ---


@pytest.fixture
def mock_logger() -> MagicMock:
    """ロガーのモックを提供します。"""
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger  # getChild が同じロガーを返すようにします
    return logger


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """EventPublisher のモックを提供します。"""
    return AsyncMock(spec=EventPublisher)


@pytest.fixture
def mock_close_event() -> MagicMock:
    """asyncio.Event のモックを提供し、wait() がキャンセルされるまで待機するようにします。"""
    event = MagicMock(spec=RealAsyncioEvent)

    async def wait_side_effect(*_args: object, **_kwargs: object) -> None:
        # キャンセルされるまで待機します
        await asyncio.sleep(1)
        # キャンセルされずに完了した場合、アサーションエラーを発生させます
        msg = "mock_close_event.wait() がキャンセルされずに完了しました。"
        raise AssertionError(msg)

    event.wait = AsyncMock(side_effect=wait_side_effect)
    event.set = Mock()
    return event


@pytest.fixture
def mock_connection_event() -> MagicMock:
    """await 可能な wait メソッドを持つ asyncio.Event のモックを提供します。"""
    event = MagicMock(spec=RealAsyncioEvent)

    # wait が await されたときに None を返すように設定します
    async def wait_side_effect() -> None:
        return None

    event.wait = AsyncMock(side_effect=wait_side_effect)
    event.set = Mock()
    return event


@pytest.fixture
def mock_process_manager_cls() -> MagicMock:
    """ProcessManager クラス自体をモックします。"""
    mock_cls = MagicMock(spec=ProcessManager)

    def create_new_mock_instance(*_args: object, **_kwargs: object) -> MagicMock:
        # 呼び出しごとに新しいインスタンスモックを作成します
        instance = MagicMock(spec=ProcessManager)
        instance.get = AsyncMock(return_value=None)  # デフォルトではプロセスなし
        instance.update = AsyncMock()

        # store メソッドのモック動作を定義します
        async def mock_store(_: Process, task: asyncio.Task[None]) -> None:
            """提供されたタスクを await するように store メソッドをモックします。"""
            if task:
                # 2番目の引数として渡されたタスクを await します
                await task

        # カスタム非同期関数を store モックの side_effect として割り当てます
        instance.store = AsyncMock(side_effect=mock_store)
        # モックストア自体が await 可能であり、呼び出しを追跡することを確認します
        instance.store.await_count = 0  # アサーションで必要な場合は await カウントを初期化します

        return instance

    mock_cls.side_effect = create_new_mock_instance
    return mock_cls


@pytest.fixture
def mock_token_manager_cls() -> MagicMock:
    """TokenManager クラスをモックします。"""
    return MagicMock(spec=RealTokenManager)


@pytest.fixture
def mock_twitch_client_cls() -> MagicMock:
    """TwitchClient クラスをモックします。"""
    return MagicMock(spec=RealTwitchClient)


@pytest.fixture
def mock_stream_info_manager_cls() -> MagicMock:
    """StreamInfoManager クラスをモックします。"""
    return MagicMock(spec=RealStreamInfoManager)


@pytest.fixture
def mock_twitch_client_instance() -> MagicMock:
    """TwitchClient のインスタンスをモックします。"""
    client = MagicMock(spec=TwitchioClientProtocol)  # spec にプロトコルを使用します
    client.run = AsyncMock()
    client.close = AsyncMock()
    client.nick = "test_bot_nick"
    client.is_streamer = False  # デフォルトではストリーマーではない
    return client


@pytest.fixture
def mock_stream_info_manager_instance() -> MagicMock:
    """StreamInfoManager のインスタンスをモックします。"""
    manager = MagicMock(spec=RealStreamInfoManager)
    manager.run = AsyncMock()
    manager.close = AsyncMock()
    return manager


@pytest.fixture
def mock_token() -> models.Token:
    """テスト用の Token モデルを提供します。"""
    return models.Token(name=TokenTag.BOT, access_token=SecretStr("fake_access_token"))


@pytest.fixture
def mock_verification() -> models.TwitchVerification:
    """テスト用の TwitchVerification モデルを提供します。"""
    return models.TwitchVerification(
        device_code="dev123",
        interval=datetime.timedelta(seconds=5),
        user_code="USER123",
        uri="http://verify.test",
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
    )


@pytest.fixture
def mock_token_manager_instance() -> MagicMock:
    """clear メソッドを持つ TokenManager のインスタンスをモックします。"""
    manager = MagicMock(spec=RealTokenManager)
    manager.clear = Mock()  # clear メソッドをモックします
    return manager


@pytest.fixture
def client_manager(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    mock_close_event: MagicMock,
    mock_process_manager_cls: MagicMock,  # クラスモックを使用します
) -> Generator[ClientManager, None, None]:
    """テスト対象の ClientManager インスタンスを提供します。"""
    # この fixture のスコープで ProcessManager をグローバルにパッチします
    with (
        patch("features.communicator.client_manager.ProcessManager", mock_process_manager_cls),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_close_event),
    ):
        manager = ClientManager(
            logger=mock_logger,
            event_publisher=mock_event_publisher,
            token_file_directory=TEST_TOKEN_FILE_DIR,
            stream_info_storage_directory=TEST_STREAM_INFO_DIR,
            channel=TEST_CHANNEL,
            enable_stream_info_command=True,  # デフォルトでは有効
        )
        yield manager


# --- テストケース ---


def test_init(
    client_manager: ClientManager,
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    mock_close_event: MagicMock,
    mock_process_manager_cls: MagicMock,
) -> None:
    """ClientManager の初期化をテストします。"""
    assert client_manager._logger is mock_logger.getChild.return_value
    assert client_manager._event_publisher is mock_event_publisher
    assert client_manager._token_file_directory == TEST_TOKEN_FILE_DIR
    assert client_manager._stream_info_storage_directory == TEST_STREAM_INFO_DIR
    assert client_manager._channel == TEST_CHANNEL
    assert client_manager._enable_stream_info_command is True
    assert client_manager._close_event is mock_close_event

    # ProcessManager が4回インスタンス化されたことを確認します
    assert mock_process_manager_cls.call_count == 4
    assert isinstance(client_manager._twitch_client_manager, MagicMock)
    assert isinstance(client_manager._twitch_token_manager, MagicMock)
    assert isinstance(client_manager._stream_info_manager, MagicMock)
    assert isinstance(client_manager._stream_info_token_manager, MagicMock)


@pytest.mark.asyncio
async def test_get_twitch_client(client_manager: ClientManager, mock_twitch_client_instance: MagicMock) -> None:
    """Twitch クライアントの取得をテストします。"""
    # ProcessManager モックがクライアントインスタンスを返すように設定します
    client_manager._twitch_client_manager.get.return_value = mock_twitch_client_instance

    client = await client_manager.get_twitch_client()

    assert client is mock_twitch_client_instance
    client_manager._twitch_client_manager.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_twitch_client_none(client_manager: ClientManager) -> None:
    """Twitch クライアントが存在しない場合の取得をテストします。"""
    # ProcessManager モックのデフォルト動作は None を返すことです
    client = await client_manager.get_twitch_client()
    assert client is None
    client_manager._twitch_client_manager.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_run(
    client_manager: ClientManager, mock_token_manager_cls: MagicMock, mock_close_event: MagicMock
) -> None:
    """メインの実行ループがボットトークンマネージャーを開始し、待機することをテストします。"""
    with patch("features.communicator.client_manager.TokenManager", mock_token_manager_cls):
        # wait をアサートできるように、別のタスクで実行します
        run_task = asyncio.create_task(client_manager.run())
        await asyncio.sleep(0)  # run タスクを開始させます

        # Bot TokenManager が作成され、更新されたことをアサートします
        mock_token_manager_cls.assert_called_once_with(
            client_manager._logger,
            TokenTag.BOT,
            communicator_constants.BOT_SCOPES,
            TEST_TOKEN_FILE_DIR,
            client_manager._start_verification_bot,
            client_manager._initialize_twitch_client,
        )
        client_manager._twitch_token_manager.update.assert_awaited_once_with(mock_token_manager_cls.return_value)

        # close イベントで待機することをアサートします
        mock_close_event.wait.assert_awaited_once()

        # タスクをクリーンアップします
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task


@pytest.mark.asyncio
async def test_close(client_manager: ClientManager, mock_close_event: MagicMock) -> None:
    """クライアントマネージャーのクローズをテストします。"""
    await client_manager.close()

    # すべてのプロセスマネージャーがクリアされたことをアサートします
    client_manager._twitch_client_manager.update.assert_awaited_once_with(None)
    client_manager._twitch_token_manager.update.assert_awaited_once_with(None)
    client_manager._stream_info_manager.update.assert_awaited_once_with(None)
    client_manager._stream_info_token_manager.update.assert_awaited_once_with(None)

    # close イベントが設定されたことをアサートします
    mock_close_event.set.assert_called_once()


@pytest.mark.asyncio
async def test_start_verification_bot(
    client_manager: ClientManager, mock_event_publisher: AsyncMock, mock_verification: models.TwitchVerification
) -> None:
    """ボット検証コールバックをテストします。"""
    await client_manager._start_verification_bot(mock_verification)
    mock_event_publisher.publish.assert_awaited_once_with(
        events.StartTwitchVerification(tag=TokenTag.BOT, verification=mock_verification)
    )


@pytest.mark.asyncio
async def test_start_verification_streamer(
    client_manager: ClientManager, mock_event_publisher: AsyncMock, mock_verification: models.TwitchVerification
) -> None:
    """ストリーマー検証コールバックをテストします。"""
    await client_manager._start_verification_streamer(mock_verification)
    mock_event_publisher.publish.assert_awaited_once_with(
        events.StartTwitchVerification(tag=TokenTag.STREAMER, verification=mock_verification)
    )


@pytest.mark.asyncio
@patch.object(ClientManager, "_run_client", new_callable=AsyncMock)
async def test_initialize_twitch_client_success(
    mock_run_client: AsyncMock,
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
    mock_event_publisher: AsyncMock,
    mock_connection_event: MagicMock,  # TwitchClient モック内で使用されます
) -> None:
    """TwitchClient の正常な初期化をテストします。"""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance

    with (
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        await client_manager._initialize_twitch_client(mock_token)

    # TwitchClient がインスタンス化されたことをアサートします
    mock_twitch_client_cls.assert_called_once_with(
        client_manager._logger,
        mock_token.access_token,
        TEST_CHANNEL,
        client_manager._event_publisher,
        mock_connection_event,
    )

    # _run_client がクライアントインスタンスで呼び出されたことをアサートします
    mock_run_client.assert_called_once_with(mock_twitch_client_instance)

    mock_connection_event.wait.assert_awaited_once()
    # クライアントが保存されたことをアサートします
    client_manager._twitch_client_manager.store.assert_awaited_once_with(
        mock_twitch_client_instance,
        ANY,  # クライアントインスタンスと *何らかの* タスクが渡されたことを確認します
    )

    # イベントが発行されたことをアサートします
    mock_event_publisher.publish.assert_awaited_once_with(
        events.TwitchChannelConnected(
            connection_info=models.ConnectionInfo(
                bot_user=mock_twitch_client_instance.nick,
                channel=TEST_CHANNEL,
            ),
        ),
    )


@pytest.mark.asyncio
@patch.object(ClientManager, "_run_client", new_callable=AsyncMock)
async def test_initialize_twitch_client_timeout(
    mock_run_client: AsyncMock,
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
    mock_event_publisher: AsyncMock,
) -> None:
    """TwitchClient の初期化タイムアウトをテストします。"""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance

    with (
        patch("features.communicator.client_manager.CLIENT_LOGIN_TIMEOUT", datetime.timedelta(seconds=0.1)),
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
    ):
        await client_manager._initialize_twitch_client(mock_token)

    # TwitchClient がインスタンス化されたことをアサートします
    mock_twitch_client_cls.assert_called_once()

    # タイムアウト時にクライアントがクローズされたことをアサートします
    mock_twitch_client_instance.close.assert_awaited_once()

    # _run_client (モック) が呼び出されたことをアサートします
    mock_run_client.assert_called_once_with(mock_twitch_client_instance)

    # クライアントが保存されなかったことをアサートします
    client_manager._twitch_client_manager.store.assert_not_called()
    client_manager._twitch_client_manager.store.assert_not_awaited()
    # イベントが発行されなかったことをアサートします
    mock_event_publisher.publish.assert_not_called()
    mock_event_publisher.publish.assert_not_awaited()


@pytest.mark.asyncio
@patch.object(ClientManager, "_run_client", new_callable=AsyncMock)
async def test_initialize_twitch_client_is_streamer_feature_enabled(
    mock_run_client: AsyncMock,
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
    mock_stream_info_manager_cls: MagicMock,  # これをパッチする必要があります
    mock_stream_info_manager_instance: MagicMock,
    mock_connection_event: MagicMock,
) -> None:
    """ボットがストリーマーであり、機能が有効な場合の _initialize_twitch_client をテストします。"""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance
    mock_twitch_client_instance.is_streamer = True  # ボットはストリーマーです
    client_manager._enable_stream_info_command = True  # 機能は有効です

    # 直接呼び出しのために StreamInfoManager の init をパッチします
    with (
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
        patch(
            "features.communicator.client_manager.StreamInfoManager", mock_stream_info_manager_cls
        ) as patched_sim_cls,
        patch("features.communicator.client_manager.TokenManager"),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        # 直接呼び出しの戻り値をモックします
        patched_sim_cls.return_value = mock_stream_info_manager_instance

        await client_manager._initialize_twitch_client(mock_token)

    # ストリーマートークンマネージャーがクリアされたことをアサートします
    client_manager._stream_info_token_manager.update.assert_awaited_once_with(None)
    # StreamInfoManager が直接初期化されたことをアサートします (_initialize_twitch_client 内)
    mock_stream_info_manager_cls.assert_called_once()
    # _run_client の呼び出しをアサートします
    expected_calls = [
        call(mock_twitch_client_instance),
        call(mock_stream_info_manager_instance),
    ]
    mock_run_client.assert_has_calls(expected_calls, any_order=False)
    assert mock_run_client.call_count == 2
    # StreamInfoManager が保存されたことをアサートします
    client_manager._stream_info_manager.store.assert_awaited_once_with(
        mock_stream_info_manager_instance,
        ANY,  # インスタンスと *何らかの* タスクが渡されたことを確認します
    )
    # TwitchClient も保存されたことをアサートします
    client_manager._twitch_client_manager.store.assert_awaited_once_with(
        mock_twitch_client_instance,
        ANY,
    )

    # *正しい* イベントモックの wait メソッドが2回 await されたことをアサートします
    assert mock_connection_event.wait.await_count == 2
    mock_connection_event.wait.assert_has_awaits([call(), call()])


@pytest.mark.asyncio
async def test_initialize_twitch_client_not_streamer_feature_enabled(
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
    mock_token_manager_cls: MagicMock,
    mock_connection_event: MagicMock,  # 引数を追加
) -> None:
    """ボットがストリーマーではなく、機能が有効な場合の _initialize_twitch_client をテストします。"""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance
    mock_twitch_client_instance.is_streamer = False  # ボットはストリーマーではありません
    client_manager._enable_stream_info_command = True  # 機能は有効です

    with (
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
        patch("features.communicator.client_manager.TokenManager", mock_token_manager_cls) as patched_tm_cls,
        patch("features.communicator.client_manager.StreamInfoManager"),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        await client_manager._initialize_twitch_client(mock_token)

    # ストリーマートークンマネージャーが初期化されたことをアサートします
    patched_tm_cls.assert_called_once_with(
        client_manager._logger,
        TokenTag.STREAMER,
        communicator_constants.STREAM_UPDATE_SCOPES,
        TEST_TOKEN_FILE_DIR,
        client_manager._start_verification_streamer,
        client_manager._initialize_stream_info_manager,
    )
    client_manager._stream_info_token_manager.update.assert_awaited_once_with(patched_tm_cls.return_value)
    # StreamInfoManager が直接初期化されなかったことをアサートします
    client_manager._stream_info_manager.store.assert_not_called()
    # 正しいイベントモックの wait メソッドが await されたことをアサートします
    mock_connection_event.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialize_twitch_client_feature_disabled(
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
    mock_connection_event: MagicMock,  # 引数を追加
) -> None:
    """ストリーム情報コマンド機能が無効な場合の _initialize_twitch_client をテストします。"""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance
    client_manager._enable_stream_info_command = False  # 機能は無効です

    with (
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
        patch("features.communicator.client_manager.TokenManager") as patched_tm_cls,
        patch("features.communicator.client_manager.StreamInfoManager") as patched_sim_cls,
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        await client_manager._initialize_twitch_client(mock_token)

    # ストリーマートークンマネージャーが初期化されなかったことをアサートします
    patched_tm_cls.assert_not_called()
    client_manager._stream_info_token_manager.update.assert_not_called()
    # StreamInfoManager が初期化されなかったことをアサートします
    patched_sim_cls.assert_not_called()
    client_manager._stream_info_manager.store.assert_not_called()


@pytest.mark.asyncio
@patch.object(ClientManager, "_run_client", new_callable=AsyncMock)
async def test_initialize_stream_info_manager_success(
    mock_run_client: AsyncMock,
    client_manager: ClientManager,
    mock_stream_info_manager_cls: MagicMock,
    mock_stream_info_manager_instance: MagicMock,
    mock_token: models.Token,
    mock_connection_event: MagicMock,
) -> None:
    """StreamInfoManager の正常な初期化をテストします。"""
    mock_stream_info_manager_cls.return_value = mock_stream_info_manager_instance

    with (
        patch("features.communicator.client_manager.StreamInfoManager", mock_stream_info_manager_cls),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        await client_manager._initialize_stream_info_manager(mock_token)

    # StreamInfoManager がインスタンス化されたことをアサートします
    mock_stream_info_manager_cls.assert_called_once_with(
        client_manager._logger,
        mock_token.access_token,
        TEST_CHANNEL,
        TEST_STREAM_INFO_DIR,
        client_manager._event_publisher,
        mock_connection_event,
    )

    # _run_client が StreamInfoManager で呼び出されたことをアサートします
    mock_run_client.assert_called_once_with(mock_stream_info_manager_instance)

    # mock_connection_event.wait が await されたことを確認します
    mock_connection_event.wait.assert_awaited_once()

    # StreamInfoManager が ANY タスクで保存されたことをアサートします
    client_manager._stream_info_manager.store.assert_awaited_once_with(
        mock_stream_info_manager_instance,
        ANY,  # インスタンスと *何らかの* タスクが渡されたことを確認します
    )


@pytest.mark.asyncio
@patch.object(ClientManager, "_run_client", new_callable=AsyncMock)
async def test_initialize_stream_info_manager_timeout(
    mock_run_client: AsyncMock,
    client_manager: ClientManager,
    mock_stream_info_manager_cls: MagicMock,
    mock_stream_info_manager_instance: MagicMock,
    mock_token: models.Token,
    mock_token_manager_instance: MagicMock,
) -> None:
    """StreamInfoManager の初期化タイムアウトとトークンマネージャーのクリアをテストします。"""
    mock_stream_info_manager_cls.return_value = mock_stream_info_manager_instance
    mock_stream_info_manager_instance.is_connected = False  # タイムアウト時は False になります

    # _stream_info_token_manager.get の戻り値を設定します
    client_manager._stream_info_token_manager.get.return_value = mock_token_manager_instance

    with (
        patch("features.communicator.client_manager.CLIENT_LOGIN_TIMEOUT", datetime.timedelta(seconds=0.1)),
        patch("features.communicator.client_manager.StreamInfoManager", mock_stream_info_manager_cls),
    ):
        await client_manager._initialize_stream_info_manager(mock_token)

    # StreamInfoManager がインスタンス化されたことをアサートします
    mock_stream_info_manager_cls.assert_called_once()

    mock_run_client.assert_awaited_once_with(mock_stream_info_manager_instance)
    # マネージャーがクローズされたことをアサートします
    mock_stream_info_manager_instance.close.assert_awaited_once()
    # マネージャーが保存されなかったことをアサートします
    client_manager._stream_info_manager.store.assert_not_called()
    client_manager._stream_info_manager.store.assert_not_awaited()

    # TokenManager の clear が呼び出されたことをアサートします
    client_manager._stream_info_token_manager.get.assert_awaited_once()
    mock_token_manager_instance.clear.assert_called_once()


@pytest.mark.asyncio
@patch.object(ClientManager, "_run_client", new_callable=AsyncMock)
async def test_initialize_stream_info_manager_not_streamer(
    mock_run_client: AsyncMock,
    client_manager: ClientManager,
    mock_stream_info_manager_cls: MagicMock,
    mock_stream_info_manager_instance: MagicMock,
    mock_token: models.Token,
    mock_connection_event: MagicMock,
    mock_token_manager_instance: MagicMock,
) -> None:
    """StreamInfoManager の初期化失敗 (ストリーマーではない) とトークンマネージャーのクリアをテストします。"""
    mock_stream_info_manager_cls.return_value = mock_stream_info_manager_instance
    mock_stream_info_manager_instance.is_connected = True  # 接続は成功します
    mock_stream_info_manager_instance.is_streamer = False  # ストリーマーではありません

    client_manager._stream_info_token_manager.get.return_value = mock_token_manager_instance

    with (
        patch("features.communicator.client_manager.StreamInfoManager", mock_stream_info_manager_cls),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        await client_manager._initialize_stream_info_manager(mock_token)

    # StreamInfoManager がインスタンス化されたことをアサートします
    mock_stream_info_manager_cls.assert_called_once()
    mock_connection_event.wait.assert_awaited_once()

    # _run_client が呼び出されたことをアサートします
    mock_run_client.assert_awaited_once_with(mock_stream_info_manager_instance)
    # マネージャーがクローズされたことをアサートします
    mock_stream_info_manager_instance.close.assert_awaited_once()
    # マネージャーが保存されなかったことをアサートします
    client_manager._stream_info_manager.store.assert_not_called()
    client_manager._stream_info_manager.store.assert_not_awaited()

    # TokenManager の clear が呼び出されたことをアサートします
    client_manager._stream_info_token_manager.get.assert_awaited_once()
    mock_token_manager_instance.clear.assert_called_once()


@pytest.mark.asyncio
async def test_run_client_success(client_manager: ClientManager) -> None:
    """_run_client がクライアントを正常に実行することをテストします。"""
    mock_client = MagicMock(spec=Process)
    mock_client.run = AsyncMock()

    await client_manager._run_client(mock_client)

    mock_client.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_client_auth_error(client_manager: ClientManager, mock_event_publisher: AsyncMock) -> None:
    """_run_client が AuthenticationError を処理することをテストします。"""
    mock_client = MagicMock(spec=Process)
    auth_error = AuthenticationError("Invalid token")
    mock_client.run = AsyncMock(side_effect=auth_error)

    await client_manager._run_client(mock_client)

    mock_client.run.assert_awaited_once()
    mock_event_publisher.publish.assert_awaited_once_with(errors.TwitchAuthenticationError())


@pytest.mark.asyncio
async def test_run_client_unhandled_error(client_manager: ClientManager, mock_event_publisher: AsyncMock) -> None:
    """_run_client が他の BaseException を処理することをテストします。"""
    mock_client = MagicMock(spec=Process)
    other_error = ValueError("Something unexpected")
    mock_client.run = AsyncMock(side_effect=other_error)

    await client_manager._run_client(mock_client)
    mock_event_publisher.publish.assert_awaited_once()

    # 実際に publish に渡された引数を取得
    # await_args は (args, kwargs) のタプルなので、最初の位置引数を取得
    assert mock_event_publisher.publish.await_args is not None  # None でないことを確認
    published_args, published_kwargs = mock_event_publisher.publish.await_args
    assert len(published_args) == 1  # 位置引数が1つであることを確認
    published_error = published_args[0]  # UnhandledError インスタンスを取得

    # 取得したエラーインスタンスの属性を個別にアサート
    assert isinstance(published_error, errors.UnhandledError)
    assert published_error.message == str(other_error)  # メッセージが一致するか
    assert published_error.file_name == "client_manager.py"  # 呼び出し元のファイル名
    # 行番号は変更される可能性があるため、具体的な数値ではなく型や範囲で確認する方が堅牢
    assert isinstance(published_error.line, int)
    assert published_error.line > 0  # 正の行番号であること
    # --- 修正箇所ここまで ---
