import datetime
from pathlib import Path

from pydantic import BaseModel, SecretStr

from . import enums


class Emote(BaseModel, frozen=True):
    id: str
    text: str


class User(BaseModel, frozen=True):
    id: int
    name: str
    display_name: str


class Game(BaseModel, frozen=True):
    game_id: str
    name: str


class StreamInfo(BaseModel, frozen=True):
    title: str
    game: Game | None = None
    tags: list[str] = []


class Message(BaseModel, frozen=True):
    content: str
    parsed_content: list[str | Emote]
    author: User
    is_echo: bool = False


class Announcement(BaseModel, frozen=True):
    content: str
    color: enums.AnnouncementColor | None = None


class Clip(BaseModel, frozen=True):
    url: str
    title: str
    creator: str


class Sound(BaseModel, frozen=True):
    path: Path


class ConnectionInfo(BaseModel, frozen=True):
    bot_user: str
    channel: str


class Token(BaseModel, frozen=True):
    name: str
    access_token: SecretStr


class TwitchVerification(BaseModel, frozen=True):
    device_code: str
    interval: datetime.timedelta
    user_code: str
    uri: str
    expires_at: datetime.datetime


class Comment(BaseModel, frozen=True):
    content: str
    is_italic: bool = False
