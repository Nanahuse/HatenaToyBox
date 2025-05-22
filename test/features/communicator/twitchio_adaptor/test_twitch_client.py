import asyncio
import datetime
import logging
from collections.abc import Generator
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import twitchio
import twitchio.errors as twitchio_errors
from pydantic import SecretStr
from twitchio.ext import commands, eventsub
from twitchio.ext.eventsub import EventSubWSClient as RealEventSubWSClient

from common.core import EventPublisher
from features.communicator.twitchio_adaptor import exceptions
from features.communicator.twitchio_adaptor.base_twitch_client import BaseTwitchClient
from features.communicator.twitchio_adaptor.twitch_client import TwitchClient
from features.communicator.twitchio_adaptor.utils import twitchio_models
from schemas import events, models

# --- Constants ---
TEST_CHANNEL_NAME = "testchannel"
TEST_TOKEN_VALUE = "testtoken123"
TEST_BOT_USER_ID = 123
TEST_BOT_USER_NAME = "test_bot"
TEST_BOT_USER_DISPLAY_NAME = "Test_Bot"
TEST_STREAMER_USER_ID = "streamer456"
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
def mock_publisher() -> AsyncMock:
    """モックされた EventPublisher を提供します。"""
    return AsyncMock(spec=EventPublisher)


@pytest.fixture
def mock_connection_event() -> AsyncMock:
    """モックされた接続イベントを提供します。"""
    event = AsyncMock(spec=asyncio.Event)
    event.is_set.return_value = False  # 未接続状態で開始
    return event


@pytest.fixture
def mock_twitchio_channel() -> AsyncMock:
    """モックされた twitchio の Channel オブジェクトを提供します。"""
    channel = AsyncMock(spec=twitchio_models.Channel)
    channel.name = TEST_CHANNEL_NAME
    channel.send = AsyncMock()
    channel.user = AsyncMock()  # user() メソッドをモック
    return channel


@pytest.fixture
def mock_twitchio_streamer_user() -> AsyncMock:
    """モックされた twitchio のストリーマーユーザーオブジェクトを提供します。"""
    user = AsyncMock(spec=twitchio_models.User)
    user.id = TEST_STREAMER_USER_ID
    user.name = TEST_CHANNEL_NAME
    user.chat_announcement = AsyncMock()
    user.shoutout = AsyncMock()
    user.fetch = AsyncMock(return_value=user)  # ユーザーオブジェクトに対する fetch() 呼び出し用
    return user


@pytest.fixture
def mock_twitchio_bot_user() -> MagicMock:
    """モックされた twitchio のボットユーザーオブジェクトを提供します。"""
    user = MagicMock(spec=twitchio_models.User)
    user.id = TEST_BOT_USER_ID  # 整数 ID を使用
    user.name = TEST_BOT_USER_NAME
    user.display_name = TEST_BOT_USER_DISPLAY_NAME
    user.fetch = AsyncMock(return_value=user)
    return user


@pytest.fixture
def mock_eventsub_client() -> MagicMock:
    """モックされた EventSubWSClient インスタンスを提供します。"""
    # このフィクスチャは、他の場所で事前に設定されたインスタンスモックが必要な場合に依然として役立つ可能性があります
    client = MagicMock(spec=RealEventSubWSClient)  # ここでも実際のクラスを使用
    client.subscribe_channel_stream_start = AsyncMock()
    client.subscribe_channel_raid = AsyncMock()
    client.subscribe_channel_follows_v2 = AsyncMock()
    return client


@pytest.fixture
def mock_http_client() -> MagicMock:
    """モックされた twitchio.http.TwitchHTTP オブジェクトを提供します。"""
    http = MagicMock(spec=twitchio.http.TwitchHTTP)
    http.token = TEST_TOKEN_VALUE  # トークンアクセスをシミュレート
    return http


@pytest.fixture
def twitch_client(
    mock_logger: MagicMock,
    mock_token: SecretStr,
    mock_publisher: AsyncMock,
    mock_connection_event: AsyncMock,
    mock_twitchio_channel: AsyncMock,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: MagicMock,
    mock_http_client: MagicMock,
) -> Generator[TwitchClient, None, None]:
    """TwitchClient のインスタンスを提供します。"""
    # BaseTwitchClient.__init__ をパッチして、初期化時の複雑さを回避
    # EventSubWSClient のインスタンス化をパッチ
    with (
        patch.object(BaseTwitchClient, "__init__", return_value=None) as mock_base_init,
        patch("features.communicator.twitchio_adaptor.twitch_client.eventsub.EventSubWSClient") as mock_eventsub_cls,
    ):
        mock_eventsub_cls.return_value = MagicMock(spec=RealEventSubWSClient)

        client = TwitchClient(
            logger=mock_logger,
            token=mock_token,
            channel=TEST_CHANNEL_NAME,
            publisher=mock_publisher,
            connection_event=mock_connection_event,
        )

        # BaseTwitchClient によって通常設定されるか、接続後に存在すると仮定される属性を手動で設定
        client._logger = mock_logger
        client._BaseTwitchClient__token = mock_token  # 必要に応じて名前マングリングを使用
        client._publisher = mock_publisher
        client._connection_event = mock_connection_event
        client._ws_client = None  # None で開始

        # メソッドテストのために event_channel_joined で設定される属性をモック
        client._BaseTwitchClient__channel = mock_twitchio_channel
        client._BaseTwitchClient__user = mock_twitchio_streamer_user
        client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
        client._http = mock_http_client  # モックされた http クライアントを設定

        client._http.user_id = TEST_BOT_USER_ID
        client._events = {}
        client.registered_callbacks = {}
        client._waiting = []  # これも初期化、後で必要になる可能性あり

        # チャンネルモックの user() メソッドの戻り値をモック
        mock_twitchio_channel.user.return_value = mock_twitchio_streamer_user

        yield client

    mock_base_init.assert_called_once_with(mock_logger, mock_token, TEST_CHANNEL_NAME, mock_connection_event)


# --- Test Cases ---


def test_init(twitch_client: TwitchClient, mock_logger: MagicMock, mock_publisher: AsyncMock) -> None:
    """TwitchClient の初期化をテストします。"""
    assert twitch_client._logger is mock_logger
    assert twitch_client._publisher is mock_publisher
    assert twitch_client._ws_client is None
    # ベースの init 呼び出しはフィクスチャのティアダウンで確認


def test_is_connected(twitch_client: TwitchClient, mock_eventsub_client: MagicMock) -> None:
    """is_connected プロパティをテストします。"""
    # 初期状態: Base は未接続、ws_client は None
    with patch.object(BaseTwitchClient, "is_connected", False, create=True):
        assert not twitch_client.is_connected

    # Base 接続済み、ws_client は None
    with patch.object(BaseTwitchClient, "is_connected", True, create=True):
        assert not twitch_client.is_connected

    # Base 接続済み、ws_client が設定されている
    with patch.object(BaseTwitchClient, "is_connected", True, create=True):
        twitch_client._ws_client = mock_eventsub_client
        assert twitch_client.is_connected

    # Base 未接続、ws_client が設定されている (発生すべきではないがロジックをテスト)
    with patch.object(BaseTwitchClient, "is_connected", False, create=True):
        twitch_client._ws_client = mock_eventsub_client
        assert not twitch_client.is_connected


@pytest.mark.asyncio
async def test_event_channel_joined_already_connected(
    twitch_client: TwitchClient,
    mock_twitchio_channel: AsyncMock,
) -> None:
    """既に接続されている場合、event_channel_joined が何もしないことをテストします。"""
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.event_channel_joined(mock_twitchio_channel)
        # 主要なセットアップメソッドが再度呼び出されなかったことを確認
        assert twitch_client._ws_client is None  # 設定されていないはず
        mock_twitchio_channel.user.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_channel_joined_success(
    twitch_client: TwitchClient,
    mock_twitchio_channel: AsyncMock,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
    mock_eventsub_client: MagicMock,
    mock_token: SecretStr,
    mock_connection_event: AsyncMock,
) -> None:
    """event_channel_joined での正常な初期化をテストします。"""
    # ベースクラスが最初は未接続であると見なすようにする
    with (
        patch.object(BaseTwitchClient, "is_connected", False, create=True),
        patch(
            "features.communicator.twitchio_adaptor.twitch_client.eventsub.EventSubWSClient",
            return_value=mock_eventsub_client,
        ) as mock_eventsub_cls,
        # --- 修正: このパッチを削除 ---
        # patch.object(BaseTwitchClient, "event_channel_joined", new_callable=AsyncMock) as mock_base_event_joined,
        # --- 修正終了 ---
        patch.object(TwitchClient, "add_event") as mock_add_event,
        patch.object(
            # テスト対象の TwitchClient インスタンス上の fetch_users をパッチし続ける
            TwitchClient,
            "fetch_users",
            new_callable=AsyncMock,
            return_value=[mock_twitchio_bot_user],
        ) as mock_fetch_users,
    ):
        # channel.user() 呼び出しをモック
        mock_twitchio_channel.user.return_value = mock_twitchio_streamer_user

        # ベースクラスメソッドが使用するために user_id が設定されていることを確認
        # (フィクスチャで client._http.user_id を設定することで既に完了)

        await twitch_client.event_channel_joined(mock_twitchio_channel)

        # EventSubWSClient が作成されたことを確認
        mock_eventsub_cls.assert_called_once_with(twitch_client)

        # 通知用に add_event が呼び出されたことを確認
        expected_add_event_calls = [
            call(twitch_client._notification_stream_start, name="event_eventsub_notification_stream_start"),
            call(twitch_client._notification_raid, name="event_eventsub_notification_raid"),
            call(twitch_client._notification_followV2, name="event_eventsub_notification_followV2"),
        ]
        mock_add_event.assert_has_calls(expected_add_event_calls, any_order=True)

        # サブスクリプションが呼び出されたことを確認
        token_val = mock_token.get_secret_value()
        mock_eventsub_client.subscribe_channel_stream_start.assert_awaited_once_with(
            token=token_val, broadcaster=mock_twitchio_streamer_user
        )
        mock_eventsub_client.subscribe_channel_raid.assert_awaited_once_with(
            token=token_val, to_broadcaster=mock_twitchio_streamer_user
        )
        mock_eventsub_client.subscribe_channel_follows_v2.assert_awaited_once_with(
            token=token_val, broadcaster=mock_twitchio_streamer_user, moderator=TEST_BOT_USER_ID
        )

        # ws_client が設定されたことを確認
        assert twitch_client._ws_client is mock_eventsub_client

        # *実際の* ベースクラスメソッドによって設定される属性が設定されたことを確認
        assert twitch_client._BaseTwitchClient__channel is mock_twitchio_channel
        assert twitch_client._BaseTwitchClient__user is mock_twitchio_streamer_user
        assert twitch_client._BaseTwitchClient__bot_user is mock_twitchio_bot_user

        # *実際の* ベースクラスメソッドによって fetch_users が呼び出されたことを確認
        mock_fetch_users.assert_awaited_once_with(ids=[TEST_BOT_USER_ID])

        # *実際の* ベースクラスメソッドによって接続イベントが設定されたことを確認
        mock_connection_event.set.assert_called_once()


@pytest.mark.asyncio
async def test_event_channel_joined_eventsub_unauthorized(
    twitch_client: TwitchClient,
    mock_twitchio_channel: AsyncMock,
    mock_twitchio_streamer_user: AsyncMock,
) -> None:
    """event_channel_joined が eventsub セットアップ中の UnauthorizedError を処理することをテストします。"""
    auth_error = twitchio_errors.Unauthorized("Eventsub auth failed")
    with (
        patch.object(BaseTwitchClient, "is_connected", False, create=True),
        patch("features.communicator.twitchio_adaptor.twitch_client.eventsub.EventSubWSClient") as mock_eventsub_cls,
        patch.object(BaseTwitchClient, "event_channel_joined", new_callable=AsyncMock) as mock_base_event_joined,
    ):
        # subscribe 呼び出しの 1 つを失敗させる
        mock_ws_instance = MagicMock()
        mock_ws_instance.subscribe_channel_stream_start.side_effect = auth_error
        mock_eventsub_cls.return_value = mock_ws_instance

        # channel.user() 呼び出しをモック
        mock_twitchio_channel.user.return_value = mock_twitchio_streamer_user

        await twitch_client.event_channel_joined(mock_twitchio_channel)

        # ws_client が設定されなかったことを確認
        assert twitch_client._ws_client is None

        # ベースクラスメソッドが依然として呼び出されたことを確認
        mock_base_event_joined.assert_awaited_once_with(mock_twitchio_channel)


@pytest.mark.asyncio
async def test_event_message_not_connected(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """接続されていない場合、event_message が何もしないことをテストします。"""
    mock_message = MagicMock(spec=twitchio_models.Message)
    with patch.object(TwitchClient, "is_connected", False, create=True):
        await twitch_client.event_message(mock_message)
        mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_event_message_no_content(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """メッセージの内容が None の場合、event_message が何もしないことをテストします。"""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = None
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.event_message(mock_message)
        mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_event_message_is_command(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """メッセージがコマンドの場合、event_message がコマンドハンドラを呼び出すことをテストします。"""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = "!hello"
    mock_message.echo = False
    mock_context = MagicMock(spec=commands.Context)
    mock_context.prefix = "!"

    with (
        patch.object(TwitchClient, "is_connected", True, create=True),
        patch.object(
            TwitchClient, "get_context", new_callable=AsyncMock, return_value=mock_context
        ) as mock_get_context,
        patch.object(TwitchClient, "invoke", new_callable=AsyncMock) as mock_invoke,
    ):
        await twitch_client.event_message(mock_message)

        mock_get_context.assert_awaited_once_with(mock_message)
        mock_invoke.assert_awaited_once_with(mock_context)
        mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_event_message_is_echo(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """event_message がエコーメッセージを無視することをテストします。"""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = "hello"
    mock_message.echo = True  # エコーメッセージ
    mock_message.author = None  # author を None で設定
    mock_message.tags = {}  # tags を空辞書で設定

    with (
        patch.object(TwitchClient, "is_connected", True, create=True),
        patch.object(TwitchClient, "get_context", new_callable=AsyncMock) as mock_get_context,
        patch.object(TwitchClient, "invoke", new_callable=AsyncMock) as mock_invoke,
    ):
        await twitch_client.event_message(mock_message)

        mock_get_context.assert_not_called()
        mock_invoke.assert_not_called()
        mock_publisher.publish.assert_awaited_once_with(
            events.NewMessageReceived(
                message=models.Message(
                    content=mock_message.content,
                    parsed_content=[mock_message.content],
                    author=models.User(
                        id=TEST_BOT_USER_ID, name=TEST_BOT_USER_NAME, display_name=TEST_BOT_USER_DISPLAY_NAME
                    ),
                    is_echo=mock_message.echo,
                )
            )
        )


@pytest.mark.asyncio
async def test_event_message_publishes_event(
    twitch_client: TwitchClient,
    mock_publisher: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
) -> None:
    """通常のメッセージに対して event_message が NewMessageReceived を発行することをテストします。"""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = "hello world"
    mock_message.echo = False
    mock_context = MagicMock(spec=commands.Context)
    mock_context.prefix = None  # コマンドではない

    mock_model_message = models.Message(
        content=mock_message.content,
        parsed_content=[mock_message.content],
        author=models.User(id=1, name="a", display_name="A"),
        is_italic=False,
    )

    with (
        patch.object(TwitchClient, "is_connected", True, create=True),
        patch.object(
            TwitchClient, "get_context", new_callable=AsyncMock, return_value=mock_context
        ) as mock_get_context,
        patch.object(TwitchClient, "invoke", new_callable=AsyncMock) as mock_invoke,
        patch(
            "features.communicator.twitchio_adaptor.twitch_client.cast_message", return_value=mock_model_message
        ) as mock_cast_message,
    ):
        await twitch_client.event_message(mock_message)

        mock_get_context.assert_awaited_once_with(mock_message)
        mock_invoke.assert_not_called()  # prefix が None なので呼び出されない
        mock_cast_message.assert_called_once_with(mock_message, mock_twitchio_bot_user)
        mock_publisher.publish.assert_awaited_once_with(events.NewMessageReceived(message=mock_model_message))


@pytest.mark.asyncio
async def test_event_message_publish_exception(
    twitch_client: TwitchClient,
    mock_publisher: AsyncMock,
) -> None:
    """発行中に event_message が例外を処理することをテストします。"""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = "hello world"
    mock_message.echo = False
    mock_context = MagicMock(spec=commands.Context)
    mock_context.prefix = None  # コマンドではない

    mock_model_message = models.Message(
        content=mock_message.content,
        parsed_content=[mock_message.content],
        author=models.User(id=1, name="a", display_name="A"),
        is_italic=False,
    )

    publish_error = ValueError("Publish failed")
    mock_publisher.publish.side_effect = publish_error

    with (
        patch.object(TwitchClient, "is_connected", True, create=True),
        patch.object(TwitchClient, "get_context", new_callable=AsyncMock, return_value=mock_context),
        patch.object(TwitchClient, "invoke", new_callable=AsyncMock),
        patch("features.communicator.twitchio_adaptor.twitch_client.cast_message", return_value=mock_model_message),
    ):
        with pytest.raises(exceptions.UnhandledError) as exc_info:
            await twitch_client.event_message(mock_message)

        assert str(publish_error) in str(exc_info.value)
        assert exc_info.value.__cause__ is publish_error
        mock_publisher.publish.assert_awaited_once()  # 呼び出されたことを確認


@pytest.mark.asyncio
async def test_notification_stream_start(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """_notification_stream_start が StreamWentOnline を発行することをテストします。"""
    mock_event_data = MagicMock(spec=eventsub.models.StreamOnlineData)
    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = mock_event_data

    await twitch_client._notification_stream_start(mock_event)

    mock_publisher.publish.assert_awaited_once_with(events.StreamWentOnline())


@pytest.mark.asyncio
async def test_notification_stream_start_wrong_type(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """_notification_stream_start が間違ったタイプのイベントを無視することをテストします。"""
    mock_event_data = MagicMock()  # StreamOnlineData ではない
    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = mock_event_data

    await twitch_client._notification_stream_start(mock_event)

    mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_notification_raid(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """_notification_raid が RaidDetected を発行することをテストします。"""
    mock_raider_user = MagicMock(spec=twitchio_models.User)
    mock_raider_user.id = 123
    mock_raider_user.name = "raider1"
    mock_raider_user.display_name = "RaiderOne"
    mock_raider_user.fetch = AsyncMock(return_value=mock_raider_user)  # ユーザー自身に対する fetch をモック

    mock_event_data = MagicMock(spec=eventsub.models.ChannelRaidData)
    mock_event_data.raider = mock_raider_user  # モックユーザーを割り当て

    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = mock_event_data

    expected_model_user = models.User(
        id=mock_raider_user.id, name=mock_raider_user.name, display_name=mock_raider_user.display_name
    )

    await twitch_client._notification_raid(mock_event)

    mock_publisher.publish.assert_awaited_once_with(events.RaidDetected(raider=expected_model_user))


@pytest.mark.asyncio
async def test_notification_raid_invalid_event(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """_notification_raid が無効なイベントを無視することをテストします。"""
    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = None

    await twitch_client._notification_raid(mock_event)

    mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_notification_follow(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """_notification_followV2 が FollowDetected を発行することをテストします。"""
    mock_follower_user = MagicMock(spec=twitchio_models.User)
    mock_follower_user.id = 1234
    mock_follower_user.name = "follower1"
    mock_follower_user.display_name = "FollowerOne"
    mock_follower_user.fetch = AsyncMock(return_value=mock_follower_user)

    mock_event_data = MagicMock(spec=eventsub.models.ChannelFollowData)
    mock_event_data.user = mock_follower_user

    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = mock_event_data

    expected_model_user = models.User(
        id=mock_follower_user.id, name=mock_follower_user.name, display_name=mock_follower_user.display_name
    )

    await twitch_client._notification_followV2(mock_event)

    mock_publisher.publish.assert_awaited_once_with(events.FollowDetected(user=expected_model_user))


@pytest.mark.asyncio
async def test_notification_follow_invalid_event(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """_notification_followV2 が無効なイベントを無視することをテストします。"""
    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = None

    await twitch_client._notification_followV2(mock_event)
    mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_send_comment_not_connected(twitch_client: TwitchClient, mock_twitchio_channel: AsyncMock) -> None:
    """接続されていない場合、send_comment が何もしないことをテストします。"""
    comment = models.Comment(content="hello", is_italic=False)
    with patch.object(TwitchClient, "is_connected", False, create=True):
        await twitch_client.send_comment(comment)
        mock_twitchio_channel.send.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_italic", "expected_content"),
    [
        (False, "hello there"),
        (True, "/me hello italic"),
    ],
)
async def test_send_comment_success(
    twitch_client: TwitchClient,
    mock_twitchio_channel: AsyncMock,
    is_italic: bool,  # noqa: FBT001
    expected_content: str,
) -> None:
    """send_comment が正しい内容を送信することをテストします。"""
    content = expected_content.replace("/me ", "") if is_italic else expected_content
    comment = models.Comment(content=content, is_italic=is_italic)
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.send_comment(comment)
        mock_twitchio_channel.send.assert_awaited_once_with(expected_content)


@pytest.mark.asyncio
async def test_send_comment_unauthorized(twitch_client: TwitchClient, mock_twitchio_channel: AsyncMock) -> None:
    """send_comment が UnauthorizedError をラップすることをテストします。"""
    comment = models.Comment(content="hello", is_italic=False)
    auth_error = twitchio_errors.Unauthorized("Send failed")
    mock_twitchio_channel.send.side_effect = auth_error
    with patch.object(TwitchClient, "is_connected", True, create=True):
        with pytest.raises(exceptions.UnauthorizedError) as exc_info:
            await twitch_client.send_comment(comment)
        assert auth_error.message in str(exc_info.value)
        assert exc_info.value.__cause__ is auth_error


@pytest.mark.asyncio
async def test_send_comment_unhandled_error(twitch_client: TwitchClient, mock_twitchio_channel: AsyncMock) -> None:
    """send_comment が他のエラーをラップすることをテストします。"""
    comment = models.Comment(content="hello", is_italic=False)
    other_error = ValueError("Something else failed")
    mock_twitchio_channel.send.side_effect = other_error
    with patch.object(TwitchClient, "is_connected", True, create=True):
        with pytest.raises(exceptions.UnhandledError) as exc_info:
            await twitch_client.send_comment(comment)
        assert str(other_error) in str(exc_info.value)
        assert exc_info.value.__cause__ is other_error


@pytest.mark.asyncio
async def test_post_announcement_not_connected(
    twitch_client: TwitchClient, mock_twitchio_streamer_user: AsyncMock
) -> None:
    """接続されていない場合、post_announcement が何もしないことをテストします。"""
    announcement = models.Announcement(content="hello", color="orange")
    with patch.object(TwitchClient, "is_connected", False, create=True):
        await twitch_client.post_announcement(announcement)
        mock_twitchio_streamer_user.chat_announcement.assert_not_called()


@pytest.mark.asyncio
async def test_post_announcement_success(
    twitch_client: TwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
    mock_http_client: MagicMock,
) -> None:
    """post_announcement が正しい API を呼び出すことをテストします。"""
    announcement = models.Announcement(content="Test Announce", color="purple")
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.post_announcement(announcement)
        mock_twitchio_streamer_user.chat_announcement.assert_awaited_once_with(
            mock_http_client.token,  # http クライアントからのアクセストークン
            mock_twitchio_bot_user.id,
            message=announcement.content,
            color=announcement.color,
        )


@pytest.mark.asyncio
async def test_post_announcement_unauthorized(
    twitch_client: TwitchClient, mock_twitchio_streamer_user: AsyncMock
) -> None:
    """post_announcement が UnauthorizedError をラップすることをテストします。"""
    announcement = models.Announcement(content="hello", color="blue")
    auth_error = twitchio_errors.Unauthorized("Announce failed")
    mock_twitchio_streamer_user.chat_announcement.side_effect = auth_error
    with patch.object(TwitchClient, "is_connected", True, create=True):
        with pytest.raises(exceptions.UnauthorizedError) as exc_info:
            await twitch_client.post_announcement(announcement)
        assert auth_error.message in str(exc_info.value)
        assert exc_info.value.__cause__ is auth_error


@pytest.mark.asyncio
async def test_post_announcement_unhandled_error(
    twitch_client: TwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
) -> None:
    """post_announcement が他のエラーを UnhandledError にラップすることをテストします。"""
    announcement = models.Announcement(content="Test Announce", color="green")
    original_error = ValueError("Simulated unexpected error during chat_announcement")
    mock_twitchio_streamer_user.chat_announcement.side_effect = original_error

    with patch.object(TwitchClient, "is_connected", True, create=True):  # noqa: SIM117
        with pytest.raises(exceptions.UnhandledError) as exc_info:
            await twitch_client.post_announcement(announcement)

    assert isinstance(exc_info.value, exceptions.UnhandledError)
    assert str(original_error) in str(exc_info.value)
    assert exc_info.value.__cause__ is original_error


@pytest.mark.asyncio
async def test_shoutout_not_connected(twitch_client: TwitchClient, mock_twitchio_streamer_user: AsyncMock) -> None:
    """接続されていない場合、shoutout が何もしないことをテストします。"""
    user = models.User(id=1234, name="shoutout1", display_name="ShoutUser")
    with patch.object(TwitchClient, "is_connected", False, create=True):
        await twitch_client.shoutout(user)
        mock_twitchio_streamer_user.shoutout.assert_not_called()


@pytest.mark.asyncio
async def test_shoutout_success(
    twitch_client: TwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
    mock_http_client: MagicMock,
) -> None:
    """shoutout が正しい API を呼び出すことをテストします。"""
    user = models.User(id=1234, name="shoutout1", display_name="ShoutUser")
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.shoutout(user)
        mock_twitchio_streamer_user.shoutout.assert_awaited_once_with(
            mock_http_client.token,
            user.id,
            mock_twitchio_bot_user.id,
        )


@pytest.mark.asyncio
async def test_shoutout_unauthorized(twitch_client: TwitchClient, mock_twitchio_streamer_user: AsyncMock) -> None:
    """shoutout が UnauthorizedError をラップすることをテストします。"""
    user = models.User(id=1234, name="shoutout1", display_name="ShoutUser")
    auth_error = twitchio_errors.Unauthorized("Shoutout failed")
    mock_twitchio_streamer_user.shoutout.side_effect = auth_error
    with patch.object(TwitchClient, "is_connected", True, create=True):
        with pytest.raises(exceptions.UnauthorizedError) as exc_info:
            await twitch_client.shoutout(user)
        assert auth_error.message in str(exc_info.value)
        assert exc_info.value.__cause__ is auth_error


@pytest.mark.asyncio
async def test_shoutout_unhandled_error(
    twitch_client: TwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
) -> None:
    """shoutout が他のエラーを UnhandledError にラップすることをテストします。"""
    user = models.User(id=1234, name="shoutout1", display_name="ShoutUser")
    original_error = ValueError("Simulated unexpected error during shoutout")
    mock_twitchio_streamer_user.shoutout.side_effect = original_error

    with patch.object(TwitchClient, "is_connected", True, create=True):  # noqa: SIM117
        with pytest.raises(exceptions.UnhandledError) as exc_info:
            await twitch_client.shoutout(user)

    assert isinstance(exc_info.value, exceptions.UnhandledError)
    assert str(original_error) in str(exc_info.value)
    assert exc_info.value.__cause__ is original_error

    mock_twitchio_streamer_user.shoutout.assert_awaited_once()
