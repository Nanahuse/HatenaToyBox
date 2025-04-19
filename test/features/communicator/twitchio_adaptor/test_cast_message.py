from unittest.mock import MagicMock

import pytest

from features.communicator.twitchio_adaptor.utils import cast_message, twitchio_models
from features.communicator.twitchio_adaptor.utils.cast_message import (
    EmoteTag,
    split_by_emote,
)
from schemas import models

# --- Constants ---
BOT_USER_ID = 123
BOT_USER_NAME = "test_bot"
BOT_USER_DISPLAY_NAME = "Test_Bot"

CHATTER_ID = 456
CHATTER_NAME = "test_user"
CHATTER_DISPLAY_NAME = "Test_User"

PARTIAL_CHATTER_ID = 789
PARTIAL_CHATTER_NAME = "partial_user"


# --- Fixtures ---


@pytest.fixture
def mock_bot_user() -> MagicMock:
    """ボットを表す twitchio_models.User をモックします。"""
    user = MagicMock(spec=twitchio_models.User)
    user.id = BOT_USER_ID
    user.name = BOT_USER_NAME
    user.display_name = BOT_USER_DISPLAY_NAME
    return user


@pytest.fixture
def mock_chatter() -> MagicMock:
    """twitchio_models.Chatter をモックします。"""
    chatter = MagicMock(spec=twitchio_models.Chatter)
    chatter.id = str(CHATTER_ID)  # Chatter ID は通常タグでは文字列
    chatter.name = CHATTER_NAME
    chatter.display_name = CHATTER_DISPLAY_NAME
    return chatter


@pytest.fixture
def mock_partial_chatter() -> MagicMock:
    """twitchio_models.PartialChatter をモックします。"""
    chatter = MagicMock(spec=twitchio_models.PartialChatter)
    chatter.id = str(PARTIAL_CHATTER_ID)  # PartialChatter ID も文字列の場合がある
    chatter.name = PARTIAL_CHATTER_NAME
    # PartialChatter は直接 display_name を持たない
    return chatter


@pytest.fixture
def mock_message_base() -> MagicMock:
    """twitchio_models.Message のベースとなる MagicMock を提供します。"""
    msg = MagicMock(spec=twitchio_models.Message)
    msg.content = "Default message content"
    msg.echo = False
    msg.author = None
    msg.tags = {}  # デフォルトは空のタグ
    return msg


# --- Tests for EmoteTag.parse_tags ---


@pytest.mark.parametrize(
    ("emotes_tag", "expected_tags"),
    [
        ("", []),
        (
            "25:0-4",
            [EmoteTag(id="25", begin=0, end=4)],
        ),
        (
            "25:0-4,6-10",
            [EmoteTag(id="25", begin=0, end=4), EmoteTag(id="25", begin=6, end=10)],
        ),
        (
            "25:0-4/300:6-9",
            [EmoteTag(id="25", begin=0, end=4), EmoteTag(id="300", begin=6, end=9)],
        ),
        (
            "1902:7-11,26-30/25:13-17",
            [
                EmoteTag(id="1902", begin=7, end=11),
                EmoteTag(id="1902", begin=26, end=30),
                EmoteTag(id="25", begin=13, end=17),
            ],
        ),
    ],
)
def test_emote_tag_parse_tags(emotes_tag: str, expected_tags: list[EmoteTag]) -> None:
    """生の emotes タグ文字列のパースをテストします。"""
    result = list(EmoteTag.parse_tags(emotes_tag))
    # 一貫した比較のために、両方のリストを開始インデックスでソート
    result.sort(key=lambda x: x.begin)
    expected_tags.sort(key=lambda x: x.begin)
    assert result == expected_tags


# --- Tests for split_by_emote ---


@pytest.mark.parametrize(
    ("content", "emotes_tag", "expected_output"),
    [
        ("Hello world", "", ["Hello world"]),
        ("Hello world", None, ["Hello world"]),  # タグがない場合に None ケースを処理
        ("Kappa", "25:0-4", [models.Emote(id="25", text="Kappa")]),
        (
            "Kappa Keepo",
            "25:0-4/1902:6-10",
            [models.Emote(id="25", text="Kappa"), models.Emote(id="1902", text="Keepo")],
        ),
        (
            "Hello Kappa world",
            "25:6-10",
            ["Hello", models.Emote(id="25", text="Kappa"), " world"],
        ),
        (
            "Hello Kappa",
            "25:6-10",
            ["Hello", models.Emote(id="25", text="Kappa")],
        ),
        (
            "Kappa world",
            "25:0-4",
            [models.Emote(id="25", text="Kappa"), " world"],
        ),
        (
            "Hello Kappa Keepo world",
            "25:6-10/1902:12-16",
            [
                "Hello",
                models.Emote(id="25", text="Kappa"),
                models.Emote(id="1902", text="Keepo"),
                " world",
            ],
        ),
        (
            " Spaces Kappa around ",
            "25:8-12",
            ["Spaces", models.Emote(id="25", text="Kappa"), " around "],
        ),
        (
            "No emotes here",
            "12345:100-105",  # エモートのインデックスが範囲外
            ["No emotes here", models.Emote(id="12345", text="")],
        ),
    ],
)
def test_split_by_emote(content: str, emotes_tag: str | None, expected_output: list[str | models.Emote]) -> None:
    """メッセージの内容をエモートで分割するテスト。"""
    if emotes_tag is None:  # noqa: SIM108
        # 'emotes' キーがない場合をシミュレート
        result = list(split_by_emote(content, ""))  # None の場合は空文字列を渡す
    else:
        result = list(split_by_emote(content, emotes_tag))
    assert result == expected_output


# --- Tests for cast_message ---


def test_cast_message_echo(mock_message_base: MagicMock, mock_bot_user: MagicMock) -> None:
    """エコーメッセージ（ボットからのメッセージ）のキャストをテストします。"""
    mock_message_base.content = "Bot message"
    mock_message_base.echo = True
    mock_message_base.author = None  # エコーの場合、author は無関係
    mock_message_base.tags = {}  # エモートなし

    result = cast_message(mock_message_base, mock_bot_user)

    assert isinstance(result, models.Message)
    assert result.content == "Bot message"
    assert result.is_echo is True
    assert result.author.id == BOT_USER_ID
    assert result.author.name == BOT_USER_NAME
    assert result.author.display_name == BOT_USER_DISPLAY_NAME
    assert result.parsed_content == ["Bot message"]


def test_cast_message_chatter(mock_message_base: MagicMock, mock_bot_user: MagicMock, mock_chatter: MagicMock) -> None:
    """通常の Chatter からのメッセージのキャストをテストします。"""
    mock_message_base.content = "User message"
    mock_message_base.echo = False
    mock_message_base.author = mock_chatter
    mock_message_base.tags = {}  # エモートなし

    result = cast_message(mock_message_base, mock_bot_user)

    assert isinstance(result, models.Message)
    assert result.content == "User message"
    assert result.is_echo is False
    assert result.author.id == CHATTER_ID
    assert result.author.name == CHATTER_NAME
    assert result.author.display_name == CHATTER_DISPLAY_NAME
    assert result.parsed_content == ["User message"]


def test_cast_message_partial_chatter(
    mock_message_base: MagicMock, mock_bot_user: MagicMock, mock_partial_chatter: MagicMock
) -> None:
    """PartialChatter からのメッセージのキャストをテストします。"""
    mock_message_base.content = "Partial user message"
    mock_message_base.echo = False
    mock_message_base.author = mock_partial_chatter
    mock_message_base.tags = {}  # エモートなし

    result = cast_message(mock_message_base, mock_bot_user)

    assert isinstance(result, models.Message)
    assert result.content == "Partial user message"
    assert result.is_echo is False
    assert result.author.id == PARTIAL_CHATTER_ID
    assert result.author.name == PARTIAL_CHATTER_NAME
    assert result.author.display_name == PARTIAL_CHATTER_NAME  # name にフォールバック
    assert result.parsed_content == ["Partial user message"]


def test_cast_message_unknown_author(mock_message_base: MagicMock, mock_bot_user: MagicMock) -> None:
    """未知の author タイプを持つメッセージのキャストをテストします（Anonymous にフォールバック）。"""
    mock_message_base.content = "Unknown author message"
    mock_message_base.echo = False
    mock_message_base.author = object()  # 何か予期しない型
    mock_message_base.tags = {}

    result = cast_message(mock_message_base, mock_bot_user)

    assert isinstance(result, models.Message)
    assert result.content == "Unknown author message"
    assert result.is_echo is False
    assert result.author.id == 0  # デフォルト ID
    assert result.author.name == "anonymous"  # デフォルト名
    assert result.author.display_name == "Anonymous"  # デフォルト表示名
    assert result.parsed_content == ["Unknown author message"]


def test_cast_message_with_emotes(
    mock_message_base: MagicMock, mock_bot_user: MagicMock, mock_chatter: MagicMock
) -> None:
    """エモートを含むメッセージのキャストをテストします。"""
    content = "Hello Kappa world LUL"
    emotes_tag = "25:6-10/425618:18-20"
    mock_message_base.content = content
    mock_message_base.echo = False
    mock_message_base.author = mock_chatter
    mock_message_base.tags = {"emotes": emotes_tag}

    result = cast_message(mock_message_base, mock_bot_user)

    expected_parsed = [
        "Hello",
        models.Emote(id="25", text="Kappa"),
        "world",
        models.Emote(id="425618", text="LUL"),
    ]

    assert isinstance(result, models.Message)
    assert result.content == content
    assert result.is_echo is False
    assert result.author.id == CHATTER_ID
    assert result.parsed_content == expected_parsed


def test_cast_message_no_emotes_tag(
    mock_message_base: MagicMock, mock_bot_user: MagicMock, mock_chatter: MagicMock
) -> None:
    """tags 辞書に 'emotes' キーがないメッセージのキャストをテストします。"""
    content = "Simple message"
    mock_message_base.content = content
    mock_message_base.echo = False
    mock_message_base.author = mock_chatter
    mock_message_base.tags = {"some_other_tag": "value"}  # 'emotes' キーがない

    result = cast_message(mock_message_base, mock_bot_user)

    assert isinstance(result, models.Message)
    assert result.content == content
    assert result.is_echo is False
    assert result.author.id == CHATTER_ID
    assert result.parsed_content == [content]  # 生の内容のみになるはず


def test_cast_message_empty_emotes_tag(
    mock_message_base: MagicMock, mock_bot_user: MagicMock, mock_chatter: MagicMock
) -> None:
    """'emotes' タグの値が空文字列であるメッセージのキャストをテストします。"""
    content = "Another simple message"
    mock_message_base.content = content
    mock_message_base.echo = False
    mock_message_base.author = mock_chatter
    mock_message_base.tags = {"emotes": ""}  # 空の emotes タグ

    result = cast_message(mock_message_base, mock_bot_user)

    assert isinstance(result, models.Message)
    assert result.content == content
    assert result.is_echo is False
    assert result.author.id == CHATTER_ID
    assert result.parsed_content == [content]  # 生の内容のみになるはず


def test_cast_message_chatter_name_fallback(mock_message_base: MagicMock, mock_bot_user: MagicMock) -> None:
    """Chatter の display_name が None で、name にフォールバックするキャストをテストします。"""
    mock_chatter_no_display = MagicMock(spec=twitchio_models.Chatter)
    mock_chatter_no_display.id = str(CHATTER_ID)
    mock_chatter_no_display.name = CHATTER_NAME
    mock_chatter_no_display.display_name = None  # 表示名なし

    mock_message_base.content = "User message"
    mock_message_base.echo = False
    mock_message_base.author = mock_chatter_no_display
    mock_message_base.tags = {}

    result = cast_message(mock_message_base, mock_bot_user)

    assert result.author.id == CHATTER_ID
    assert result.author.name == CHATTER_NAME
    assert result.author.display_name == CHATTER_NAME  # name にフォールバック


def test_cast_message_bot_name_fallback(mock_message_base: MagicMock) -> None:
    """ボットの display_name が None で、name にフォールバックするエコーメッセージのキャストをテストします。"""
    mock_bot_no_display = MagicMock(spec=twitchio_models.User)
    mock_bot_no_display.id = BOT_USER_ID
    mock_bot_no_display.name = BOT_USER_NAME
    mock_bot_no_display.display_name = None  # 表示名なし

    mock_message_base.content = "Bot message"
    mock_message_base.echo = True
    mock_message_base.author = None
    mock_message_base.tags = {}

    result = cast_message(mock_message_base, mock_bot_no_display)

    assert result.author.id == BOT_USER_ID
    assert result.author.name == BOT_USER_NAME
    assert result.author.display_name == BOT_USER_NAME  # name にフォールバック
