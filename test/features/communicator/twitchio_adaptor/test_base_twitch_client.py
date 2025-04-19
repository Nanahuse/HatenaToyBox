import asyncio
import datetime
import logging
from collections.abc import Generator
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import twitchio.errors as twitchio_errors
from freezegun import freeze_time
from pydantic import SecretStr
from twitchio.ext import commands

from features.communicator.twitchio_adaptor import exceptions
from features.communicator.twitchio_adaptor.base_twitch_client import BaseTwitchClient
from features.communicator.twitchio_adaptor.utils import twitchio_models
from schemas import models

# --- Constants ---
TEST_CHANNEL_NAME = "testchannel"
TEST_TOKEN_VALUE = "testtoken123"
TEST_BOT_USER_ID = 123
TEST_STREAMER_USER_ID = 456
TEST_STREAMER_NAME = "teststreamer"
TEST_BOT_NAME = "testbot"
NOW = datetime.datetime(2023, 10, 27, 12, 0, 0, tzinfo=UTC)

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
def mock_connection_event() -> AsyncMock:
    """モックされた接続イベントを提供します。"""
    event = AsyncMock(spec=asyncio.Event)
    event.is_set.return_value = False  # 初期状態は未接続
    event.set = Mock()  # set メソッドをモック
    return event


@pytest.fixture
def mock_twitchio_channel() -> AsyncMock:
    """モックされた twitchio の Channel オブジェクトを提供します。"""
    channel = AsyncMock(spec=twitchio_models.Channel)
    channel.name = TEST_CHANNEL_NAME
    channel.user = AsyncMock()  # user() メソッドをモック
    return channel


@pytest.fixture
def mock_twitchio_streamer_user() -> AsyncMock:
    """モックされた twitchio のストリーマーユーザーオブジェクトを提供します。"""
    user = AsyncMock(spec=twitchio_models.User)
    user.id = TEST_STREAMER_USER_ID
    user.name = TEST_STREAMER_NAME
    user.display_name = "TestStreamer"
    user.fetch_clips = AsyncMock(return_value=[])
    return user


@pytest.fixture
def mock_twitchio_bot_user() -> AsyncMock:
    """モックされた twitchio のボットユーザーオブジェクトを提供します。"""
    user = AsyncMock(spec=twitchio_models.User)
    user.id = TEST_BOT_USER_ID
    user.name = TEST_BOT_NAME
    user.display_name = "TestBot"
    return user


@pytest.fixture
def mock_context() -> MagicMock:
    """twitchio.ext.commands.Context をモックします。"""
    return MagicMock(spec=commands.Context)


@pytest.fixture
def mock_channel_info() -> MagicMock:
    """モックされたチャンネル情報オブジェクトを提供します。"""
    # 利用可能であれば twitchio.models.ChannelInfo を spec に使用し、そうでなければ MagicMock を使用
    try:
        spec = twitchio_models.ChannelInfo
    except AttributeError:
        spec = MagicMock  # ChannelInfo が twitchio_models にない場合のフォールバック
    info = MagicMock(spec=spec)
    info.game_id = "12345"
    info.game_name = "Test Game"
    info.title = "Test Stream Title"
    info.tags = ["tag1", "tag2"]
    return info


@pytest.fixture
def mock_twitchio_clip() -> MagicMock:
    """モックされた twitchio の Clip オブジェクトを提供します。"""
    clip = MagicMock(spec=twitchio_models.Clip)
    clip.url = "http://clip.test/1"
    clip.title = "Test Clip 1"
    clip.creator = MagicMock(spec=twitchio_models.User)
    clip.creator.name = "ClipCreator"
    return clip


@pytest.fixture
def base_twitch_client(
    mock_logger: MagicMock,
    mock_token: SecretStr,
    mock_connection_event: AsyncMock,
) -> Generator[BaseTwitchClient, None, None]:
    """BaseTwitchClient のインスタンスを提供します。"""
    # commands.Bot.__init__ をパッチして、初期化時の複雑さを回避
    with patch.object(commands.Bot, "__init__", return_value=None) as mock_bot_init:
        client = BaseTwitchClient(
            logger=mock_logger,
            token=mock_token,
            channel=TEST_CHANNEL_NAME,
            connection_event=mock_connection_event,
        )
        # commands.Bot や後で設定される属性を手動で設定
        client._logger = mock_logger  # ロガーが正しく設定されていることを確認
        client._BaseTwitchClient__token = mock_token
        client._connection_event = mock_connection_event
        # commands.Bot.__init__ によって設定される属性をシミュレート
        client._prefix = "!"
        client._initial_channels = [TEST_CHANNEL_NAME]

        # 後で設定されるか、Bot の一部である属性をモック
        client._connection = MagicMock()  # connection オブジェクトをモック
        client._http = MagicMock()  # http オブジェクトをモック
        # commands.Bot から来る user_id プロパティをモック
        # 通常は _http.user_id から読み取るので、それをモック
        client._http.user_id = TEST_BOT_USER_ID

        # 内部状態の属性をモック
        client._BaseTwitchClient__channel = None
        client._BaseTwitchClient__user = None
        client._BaseTwitchClient__bot_user = None

        yield client

    # BaseTwitchClient の init によって Bot の init が正しく呼び出されたかを確認
    mock_bot_init.assert_called_once_with(
        mock_token.get_secret_value(), client_secret="", prefix="!", initial_channels=[TEST_CHANNEL_NAME]
    )


# --- Test Cases ---


def test_init(
    base_twitch_client: BaseTwitchClient,
    mock_logger: MagicMock,
    mock_token: SecretStr,
    mock_connection_event: AsyncMock,
) -> None:
    """BaseTwitchClient の初期化をテストします。"""
    assert base_twitch_client._logger is mock_logger
    assert base_twitch_client._BaseTwitchClient__token is mock_token
    assert base_twitch_client._connection_event is mock_connection_event
    assert base_twitch_client._BaseTwitchClient__channel is None
    assert base_twitch_client._BaseTwitchClient__user is None
    assert base_twitch_client._BaseTwitchClient__bot_user is None
    # Bot の init 呼び出しはフィクスチャのティアダウンで確認


# --- プロパティテスト ---


def test_channel_property_not_connected(base_twitch_client: BaseTwitchClient) -> None:
    """未接続時に _channel プロパティが ImplementationError を発生させることをテストします。"""
    with pytest.raises(exceptions.ImplementationError, match="Not connected yet"):
        _ = base_twitch_client._channel


def test_channel_property_connected(base_twitch_client: BaseTwitchClient, mock_twitchio_channel: AsyncMock) -> None:
    """接続時に _channel プロパティがチャンネルを返すことをテストします。"""
    base_twitch_client._BaseTwitchClient__channel = mock_twitchio_channel
    assert base_twitch_client._channel is mock_twitchio_channel


def test_user_property_not_connected(base_twitch_client: BaseTwitchClient) -> None:
    """未接続時に _user プロパティが ImplementationError を発生させることをテストします。"""
    with pytest.raises(exceptions.ImplementationError, match="Not connected yet"):
        _ = base_twitch_client._user


def test_user_property_connected(base_twitch_client: BaseTwitchClient, mock_twitchio_streamer_user: AsyncMock) -> None:
    """接続時に _user プロパティがユーザーを返すことをテストします。"""
    base_twitch_client._BaseTwitchClient__user = mock_twitchio_streamer_user
    assert base_twitch_client._user is mock_twitchio_streamer_user


def test_bot_user_property_not_connected(base_twitch_client: BaseTwitchClient) -> None:
    """未接続時に _bot_user プロパティが ImplementationError を発生させることをテストします。"""
    with pytest.raises(exceptions.ImplementationError, match="Not connected yet"):
        _ = base_twitch_client._bot_user


def test_bot_user_property_connected(base_twitch_client: BaseTwitchClient, mock_twitchio_bot_user: AsyncMock) -> None:
    """接続時に _bot_user プロパティがボットユーザーを返すことをテストします。"""
    base_twitch_client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
    assert base_twitch_client._bot_user is mock_twitchio_bot_user


def test_token_property(base_twitch_client: BaseTwitchClient, mock_token: SecretStr) -> None:
    """_token プロパティがトークンを返すことをテストします。"""
    assert base_twitch_client._token is mock_token


def test_is_connected_property(
    base_twitch_client: BaseTwitchClient,
    mock_twitchio_channel: AsyncMock,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
) -> None:
    """is_connected プロパティのロジックをテストします。"""
    assert not base_twitch_client.is_connected  # 初期状態は False

    base_twitch_client._BaseTwitchClient__channel = mock_twitchio_channel
    assert not base_twitch_client.is_connected

    base_twitch_client._BaseTwitchClient__user = mock_twitchio_streamer_user
    assert not base_twitch_client.is_connected

    base_twitch_client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
    assert base_twitch_client.is_connected  # 全て設定されたので True になるはず


def test_is_streamer_property(
    base_twitch_client: BaseTwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
) -> None:
    """is_streamer プロパティのロジックをテストします。"""
    # ケース 1: ボットがストリーマーである
    mock_twitchio_streamer_user.id = TEST_BOT_USER_ID  # ストリーマーIDをボットIDと一致させる
    base_twitch_client._BaseTwitchClient__user = mock_twitchio_streamer_user
    base_twitch_client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
    assert base_twitch_client.is_streamer

    # ケース 2: ボットがストリーマーではない
    mock_twitchio_streamer_user.id = TEST_STREAMER_USER_ID  # 異なるID
    base_twitch_client._BaseTwitchClient__user = mock_twitchio_streamer_user
    base_twitch_client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
    assert not base_twitch_client.is_streamer


# --- コマンドメソッドテスト ---


@pytest.mark.asyncio
async def test_info_command_called(base_twitch_client: BaseTwitchClient, mock_context: MagicMock) -> None:
    """info コマンドのコールバックがエラーなしで呼び出せることをテストします。"""
    action = "test_action"
    name = "test_name"

    # info コマンドの基底関数 (_callback) を呼び出す
    # BaseTwitchClient の info メソッドの実装は pass なので、
    # エラーが発生しないことを確認するのが主な目的
    try:
        await base_twitch_client.info._callback(base_twitch_client, mock_context, action, name)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"info コマンドのコールバック呼び出しで予期せぬ例外が発生しました: {e}")


# --- メソッドテスト ---


@pytest.mark.asyncio
async def test_run_success(base_twitch_client: BaseTwitchClient) -> None:
    """run が super().start() を正常に呼び出すことをテストします。"""
    with patch.object(commands.Bot, "start", new_callable=AsyncMock) as mock_start:
        await base_twitch_client.run()
        mock_start.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_auth_error(base_twitch_client: BaseTwitchClient) -> None:
    """run が AuthenticationError をラップすることをテストします。"""
    auth_error = twitchio_errors.AuthenticationError("Invalid token")
    with patch.object(commands.Bot, "start", side_effect=auth_error) as mock_start:
        with pytest.raises(exceptions.UnauthorizedError) as exc_info:
            await base_twitch_client.run()
        mock_start.assert_awaited_once()
        assert "Twitch authentication failed" in str(exc_info.value)
        assert exc_info.value.__cause__ is auth_error


@pytest.mark.asyncio
async def test_run_other_error(base_twitch_client: BaseTwitchClient) -> None:
    """run が他の BaseException をラップすることをテストします。"""
    other_error = ValueError("Something went wrong")
    with patch.object(commands.Bot, "start", side_effect=other_error) as mock_start:
        with pytest.raises(exceptions.UnhandledError) as exc_info:
            await base_twitch_client.run()
        mock_start.assert_awaited_once()
        assert str(other_error) in str(exc_info.value)
        assert exc_info.value.__cause__ is other_error


@pytest.mark.asyncio
async def test_close(base_twitch_client: BaseTwitchClient) -> None:
    """close が super().close() を呼び出すことをテストします。"""
    with patch.object(commands.Bot, "close", new_callable=AsyncMock) as mock_close:
        await base_twitch_client.close()
        mock_close.assert_awaited_once()


# --- イベントハンドラテスト ---


@pytest.mark.asyncio
async def test_event_channel_joined_already_connected(
    base_twitch_client: BaseTwitchClient, mock_twitchio_channel: AsyncMock, mock_connection_event: AsyncMock
) -> None:
    """既に接続されている場合、event_channel_joined が何もしないことをテストします。"""
    # 接続状態をシミュレート
    base_twitch_client._BaseTwitchClient__channel = mock_twitchio_channel
    base_twitch_client._BaseTwitchClient__user = MagicMock()
    base_twitch_client._BaseTwitchClient__bot_user = MagicMock()
    assert base_twitch_client.is_connected

    with patch.object(base_twitch_client, "fetch_users", new_callable=AsyncMock) as mock_fetch:
        await base_twitch_client.event_channel_joined(mock_twitchio_channel)

    mock_twitchio_channel.user.assert_not_awaited()
    mock_fetch.assert_not_awaited()
    mock_connection_event.set.assert_not_called()


@pytest.mark.asyncio
async def test_event_channel_joined_success(
    base_twitch_client: BaseTwitchClient,
    mock_twitchio_channel: AsyncMock,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
    mock_connection_event: AsyncMock,
) -> None:
    """event_channel_joined が成功時に属性とイベントを設定することをテストします。"""
    assert not base_twitch_client.is_connected
    mock_twitchio_channel.user.return_value = mock_twitchio_streamer_user

    # インスタンス上で fetch_users メソッドを直接モック
    base_twitch_client.fetch_users = AsyncMock(return_value=[mock_twitchio_bot_user])

    await base_twitch_client.event_channel_joined(mock_twitchio_channel)

    assert base_twitch_client._BaseTwitchClient__channel is mock_twitchio_channel
    mock_twitchio_channel.user.assert_awaited_once()
    assert base_twitch_client._BaseTwitchClient__user is mock_twitchio_streamer_user
    base_twitch_client.fetch_users.assert_awaited_once_with(ids=[TEST_BOT_USER_ID])
    assert base_twitch_client._BaseTwitchClient__bot_user is mock_twitchio_bot_user
    mock_connection_event.set.assert_called_once()
    assert base_twitch_client.is_connected


@pytest.mark.asyncio
async def test_event_channel_join_failure(
    base_twitch_client: BaseTwitchClient, mock_connection_event: AsyncMock
) -> None:
    """event_channel_join_failure がエラーをログに記録し、イベントを設定することをテストします。"""
    failed_channel = "failed_channel"
    await base_twitch_client.event_channel_join_failure(failed_channel)

    mock_connection_event.set.assert_called_once()


@pytest.mark.asyncio
async def test_event_command_error_not_found(base_twitch_client: BaseTwitchClient, mock_context: MagicMock) -> None:
    """event_command_error が CommandNotFound の警告をログに記録することをテストします。"""
    error = commands.CommandNotFound("Unknown command", name="unknown")
    await base_twitch_client.event_command_error(mock_context, error)


@pytest.mark.asyncio
async def test_event_command_error_other(base_twitch_client: BaseTwitchClient, mock_context: MagicMock) -> None:
    """event_command_error が他の例外のエラーをログに記録することをテストします。"""
    error = ValueError("Some other error")
    await base_twitch_client.event_command_error(mock_context, error)


# --- Fetch Method Tests ---


@pytest.mark.asyncio
async def test_fetch_stream_info_not_connected(base_twitch_client: BaseTwitchClient) -> None:
    """未接続時に fetch_stream_info が UnauthorizedError を発生させることをテストします。"""
    assert not base_twitch_client.is_connected
    with pytest.raises(exceptions.UnauthorizedError, match="Not connected yet"):
        await base_twitch_client.fetch_stream_info(None)


@pytest.mark.asyncio
async def test_fetch_stream_info_success_with_user(
    base_twitch_client: BaseTwitchClient,
    mock_channel_info: MagicMock,
    mock_twitchio_streamer_user: AsyncMock,  # 接続状態の設定に必要
    mock_twitchio_bot_user: AsyncMock,  # 接続状態の設定に必要
    mock_twitchio_channel: AsyncMock,  # 接続状態の設定に必要
) -> None:
    """fetch_stream_info が特定のユーザーに対してフェッチすることをテストします。"""
    # 接続状態を設定
    base_twitch_client._BaseTwitchClient__channel = mock_twitchio_channel
    base_twitch_client._BaseTwitchClient__user = mock_twitchio_streamer_user
    base_twitch_client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
    assert base_twitch_client.is_connected

    target_user = models.User(id=987, name="targetuser", display_name="TargetUser")

    # インスタンス上で fetch_channel を直接モック
    base_twitch_client.fetch_channel = AsyncMock(return_value=mock_channel_info)

    stream_info = await base_twitch_client.fetch_stream_info(target_user)

    base_twitch_client.fetch_channel.assert_awaited_once_with(target_user.name)
    assert isinstance(stream_info, models.StreamInfo)
    assert stream_info.title == mock_channel_info.title
    assert stream_info.game is not None
    assert stream_info.game.game_id == mock_channel_info.game_id
    assert stream_info.game.name == mock_channel_info.game_name
    assert stream_info.tags == mock_channel_info.tags


@pytest.mark.asyncio
async def test_fetch_stream_info_success_no_user(
    base_twitch_client: BaseTwitchClient,
    mock_channel_info: MagicMock,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
    mock_twitchio_channel: AsyncMock,
) -> None:
    """user が None の場合、fetch_stream_info が現在のチャンネルユーザーに対してフェッチすることをテストします。"""
    base_twitch_client._BaseTwitchClient__channel = mock_twitchio_channel
    base_twitch_client._BaseTwitchClient__user = mock_twitchio_streamer_user
    base_twitch_client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
    assert base_twitch_client.is_connected

    base_twitch_client.fetch_channel = AsyncMock(return_value=mock_channel_info)

    stream_info = await base_twitch_client.fetch_stream_info(None)

    base_twitch_client.fetch_channel.assert_awaited_once_with(
        mock_twitchio_streamer_user.name
    )  # _user.name に対してフェッチする
    assert isinstance(stream_info, models.StreamInfo)
    assert stream_info.title == mock_channel_info.title


@pytest.mark.asyncio
async def test_fetch_stream_info_no_game(
    base_twitch_client: BaseTwitchClient,
    mock_channel_info: MagicMock,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
    mock_twitchio_channel: AsyncMock,
) -> None:
    """fetch_stream_info が空の game_id を正しく処理することをテストします。"""
    base_twitch_client._BaseTwitchClient__channel = mock_twitchio_channel
    base_twitch_client._BaseTwitchClient__user = mock_twitchio_streamer_user
    base_twitch_client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
    assert base_twitch_client.is_connected

    mock_channel_info.game_id = ""  # ゲームが設定されていない状態をシミュレート

    base_twitch_client.fetch_channel = AsyncMock(return_value=mock_channel_info)

    stream_info = await base_twitch_client.fetch_stream_info(None)

    base_twitch_client.fetch_channel.assert_awaited_once_with(mock_twitchio_streamer_user.name)
    assert isinstance(stream_info, models.StreamInfo)
    assert stream_info.game is None  # None になるはず


@pytest.mark.asyncio
async def test_fetch_clips_not_connected(base_twitch_client: BaseTwitchClient) -> None:
    """未接続時に fetch_clips が UnauthorizedError を発生させることをテストします。"""
    assert not base_twitch_client.is_connected
    duration = datetime.timedelta(minutes=5)
    with pytest.raises(exceptions.UnauthorizedError, match="Not connected yet"):
        await base_twitch_client.fetch_clips(duration)


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_fetch_clips_success(
    base_twitch_client: BaseTwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,  # 接続状態に必要
    mock_twitchio_channel: AsyncMock,  # 接続状態に必要
    mock_twitchio_clip: MagicMock,
) -> None:
    """fetch_clips がクリップを正しくフェッチし、変換することをテストします。"""
    base_twitch_client._BaseTwitchClient__channel = mock_twitchio_channel
    base_twitch_client._BaseTwitchClient__user = mock_twitchio_streamer_user
    base_twitch_client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
    assert base_twitch_client.is_connected

    duration = datetime.timedelta(minutes=10)
    expected_started_at = NOW - duration

    # 匿名クリエイターを持つ別のクリップをモック
    mock_clip_anon = MagicMock(spec=twitchio_models.Clip)
    mock_clip_anon.url = "http://clip.test/anon"
    mock_clip_anon.title = "Anon Clip"
    mock_clip_anon.creator = MagicMock(spec=twitchio_models.User)
    mock_clip_anon.creator.name = None  # 匿名

    mock_twitchio_streamer_user.fetch_clips.return_value = [mock_twitchio_clip, mock_clip_anon]

    result = await base_twitch_client.fetch_clips(duration)

    mock_twitchio_streamer_user.fetch_clips.assert_awaited_once()
    # started_at が正しく渡されたかを確認
    call_args, call_kwargs = mock_twitchio_streamer_user.fetch_clips.call_args
    assert "started_at" in call_kwargs
    assert call_kwargs["started_at"] == expected_started_at

    assert len(result) == 2
    assert isinstance(result[0], models.Clip)
    assert result[0].url == mock_twitchio_clip.url
    assert result[0].title == mock_twitchio_clip.title
    assert result[0].creator == mock_twitchio_clip.creator.name

    assert isinstance(result[1], models.Clip)
    assert result[1].url == mock_clip_anon.url
    assert result[1].title == mock_clip_anon.title
    assert result[1].creator == "Anonymous"  # 匿名処理を確認
