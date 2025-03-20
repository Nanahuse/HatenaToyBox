from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from schemas import models

from . import twitchio_models

if TYPE_CHECKING:
    from collections.abc import Generator


class EmoteTag(BaseModel):
    id: str
    begin: int
    end: int

    @classmethod
    def parse_tags(cls, emotes_tag: str) -> Generator[EmoteTag]:
        if emotes_tag == "":
            return

        for tag in emotes_tag.split("/"):
            emote_id, positions = tag.split(":")
            for position in positions.split(","):
                begin, end = position.split("-")
                yield EmoteTag(id=emote_id, begin=begin, end=end)


def split_by_emote(content: str, emotes_tag: str) -> Generator[str | models.Emote]:
    emotes = list(EmoteTag.parse_tags(emotes_tag))
    emotes.sort(key=lambda emote: emote.begin)

    begin = 0
    for emote in emotes:
        section = content[begin : emote.begin].strip()
        if len(section):
            yield section

        yield models.Emote(id=emote.id, text=content[emote.begin : emote.end + 1].strip())

        begin = emote.end + 1

    if begin < len(content):
        yield content[begin:]


def cast_message(message: twitchio_models.Message, bot_user: twitchio_models.User) -> models.Message:
    content = cast("str", message.content)
    is_echo = cast("bool", message.echo)

    display_name = "Anonymous"  # これって発生しうるのかな
    name = "anonymous"
    author_id = 0

    match is_echo, message.author:
        case True, _:
            display_name = bot_user.display_name or bot_user.name or display_name
            name = bot_user.name or name
            author_id = bot_user.id
        case _, twitchio_models.Chatter() as chatter:
            display_name = chatter.display_name or chatter.name or display_name
            name = chatter.name or name
            author_id = int(chatter.id)
        case _, twitchio_models.PartialChatter() as chatter:
            display_name = cast("str", chatter.name) or display_name
            name = cast("str", chatter.name) or name
            author_id = int(chatter.id)
        case _:
            pass

    parsed_content = list(split_by_emote(content, message.tags["emotes"])) if "emotes" in message.tags else [content]

    return models.Message(
        content=content,
        parsed_content=parsed_content,
        author=models.User(
            id=author_id,
            name=name,
            display_name=display_name,
        ),
        is_echo=is_echo,
    )
