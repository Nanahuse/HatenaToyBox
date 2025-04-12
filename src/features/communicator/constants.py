# client config
BOT_SCOPES = [
    "chat:read",
    "chat:edit",
    "channel:manage:broadcast",  # for stream_info update
    "moderator:manage:announcements",  # for announcement
    "moderator:manage:shoutouts",  # for shoutout
    "moderator:read:followers",  # for follow notification
]

STREAM_UPDATE_SCOPES = [
    "chat:read",
    "channel:manage:broadcast",  # for stream_info update
]
