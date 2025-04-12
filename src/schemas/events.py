from common.base_model import BaseEvent

from . import models


class TwitchChannelConnected(BaseEvent):
    """Signifies that a connection to a Twitch channel has been established."""

    connection_info: models.ConnectionInfo


class NewMessageReceived(BaseEvent):
    """A new message has been received in the chat."""

    message: models.Message


class MessageFiltered(BaseEvent):
    """A message has been filtered by the filter."""

    message: models.Message


class MessageTranslated(BaseEvent):
    """A message has been translated."""

    message: models.Message


class AnnouncementPosted(BaseEvent):
    """An announcement has been posted in the chat."""

    announcement: models.Announcement


class ClipFound(BaseEvent):
    """A clip has been found."""

    clip: models.Clip


class StreamInfoChanged(BaseEvent):
    """The stream information has changed."""

    stream_info: models.StreamInfo


class RaidDetected(BaseEvent):
    """A raid has been detected."""

    raider: models.User


class FollowDetected(BaseEvent):
    """A follow has been detected."""

    user: models.User


class StreamWentOnline(BaseEvent):
    """The stream has gone online."""


class StartTwitchVerification(BaseEvent):
    """Start to verify the twitch token"""

    tag: str
    verification: models.TwitchVerification
