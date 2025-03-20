from __future__ import annotations

from typing import TYPE_CHECKING

from schemas import events, models

if TYPE_CHECKING:
    import logging

    from common.core import EventPublisher


class UpdateDetector:
    def __init__(self, logger: logging.Logger, event_publisher: EventPublisher) -> None:
        self._logger = logger.getChild(self.__class__.__name__)
        self._event_publisher = event_publisher

        self._current_stream_info: models.StreamInfo | None = None
        self._handled_clips = set[str]()
        self._stream_titles = set[str]()

    def initialize(self, stream_info: models.StreamInfo, clips: list[models.Clip]) -> None:
        if self._current_stream_info is not None:
            self._logger.debug("Already initialized.")
            return

        self._current_stream_info = stream_info
        self._stream_titles.add(stream_info.title)
        for clip in clips:
            self._handled_clips.add(clip.url)

        self._logger.debug("Initialized. clips: num = %s", len(clips))

    async def update(self, stream_info: models.StreamInfo, clips: list[models.Clip]) -> None:
        if stream_info != self._current_stream_info:
            self._current_stream_info = stream_info
            await self._event_publisher.publish(events.StreamInfoChanged(stream_info=stream_info))

        if stream_info.title not in self._stream_titles:
            self._stream_titles.add(stream_info.title)

        for clip in clips:
            if clip.title in self._stream_titles:
                continue

            if clip.url in self._handled_clips:
                continue

            self._handled_clips.add(clip.url)

            self._logger.info("New clip found: %s created by '%s', %s", clip.title, clip.creator, clip.url)

            await self._event_publisher.publish(events.ClipFound(clip=clip))
