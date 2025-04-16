import logging
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from common.core import EventPublisher
from features.communicator.update_detector import UpdateDetector
from schemas import events, models


@pytest.fixture
def mock_logger() -> MagicMock:
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    return AsyncMock(spec=EventPublisher)


@pytest.fixture
def initial_stream_info() -> models.StreamInfo:
    return models.StreamInfo(
        title="Initial Stream Title",
        game_name="Initial Game",
        is_live=True,
        viewer_count=100,
    )


@pytest.fixture
def initial_clips() -> list[models.Clip]:
    return [
        models.Clip(
            title="Clip 1",
            url="http://clip1.com",
            creator="Creator A",
            created_at="2023-01-01T00:00:00Z",
        ),
        models.Clip(
            title="Clip 2",
            url="http://clip2.com",
            creator="Creator B",
            created_at="2023-01-01T00:01:00Z",
        ),
    ]


@pytest.fixture
def new_stream_info() -> models.StreamInfo:
    return models.StreamInfo(
        title="New Stream Title",
        game_name="New Game",
        is_live=True,
        viewer_count=150,
    )


@pytest.fixture
def new_clip() -> models.Clip:
    return models.Clip(
        title="New Clip",
        url="http://newclip.com",
        creator="Creator C",
        created_at="2023-01-01T00:05:00Z",
    )


def test_init(mock_logger: MagicMock, mock_event_publisher: AsyncMock) -> None:
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    assert detector._logger is mock_logger
    assert detector._event_publisher is mock_event_publisher
    assert detector._current_stream_info is None
    assert detector._handled_clips == set()
    assert detector._stream_titles == set()


def test_initialize_first_time(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
) -> None:
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    assert detector._current_stream_info == initial_stream_info
    assert detector._stream_titles == {initial_stream_info.title}
    assert detector._handled_clips == {clip.url for clip in initial_clips}


def test_initialize_already_initialized(  # noqa: PLR0913
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
    new_stream_info: models.StreamInfo,
    new_clip: models.Clip,
) -> None:
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    # Store initial state for comparison
    original_stream_info = detector._current_stream_info
    original_titles = detector._stream_titles.copy()
    original_clips = detector._handled_clips.copy()

    # Attempt to initialize again
    detector.initialize(new_stream_info, [new_clip])

    # Assert state hasn't changed
    assert detector._current_stream_info == original_stream_info
    assert detector._stream_titles == original_titles
    assert detector._handled_clips == original_clips


@pytest.mark.asyncio
async def test_update_no_changes(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
) -> None:
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    await detector.update(initial_stream_info, initial_clips)

    assert detector._current_stream_info == initial_stream_info
    assert detector._stream_titles == {initial_stream_info.title}
    assert detector._handled_clips == {clip.url for clip in initial_clips}
    mock_event_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_update_stream_info_changed(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
    new_stream_info: models.StreamInfo,
) -> None:
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    await detector.update(new_stream_info, initial_clips)

    assert detector._current_stream_info == new_stream_info
    assert detector._stream_titles == {initial_stream_info.title, new_stream_info.title}
    assert detector._handled_clips == {clip.url for clip in initial_clips}
    mock_event_publisher.publish.assert_called_once_with(events.StreamInfoChanged(stream_info=new_stream_info))


@pytest.mark.asyncio
async def test_update_new_clip_found(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
    new_clip: models.Clip,
) -> None:
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    updated_clips = [*initial_clips, new_clip]
    await detector.update(initial_stream_info, updated_clips)

    assert detector._current_stream_info == initial_stream_info
    assert detector._stream_titles == {initial_stream_info.title}
    assert detector._handled_clips == {clip.url for clip in updated_clips}
    mock_event_publisher.publish.assert_called_once_with(events.ClipFound(clip=new_clip))


@pytest.mark.asyncio
async def test_update_new_clip_found_title_matches_stream(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
) -> None:
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    clip_with_stream_title = models.Clip(
        title=initial_stream_info.title,  # Title matches stream
        url="http://titlematchclip.com",
        creator="Creator D",
        created_at="2023-01-01T00:10:00Z",
    )
    updated_clips = [*initial_clips, clip_with_stream_title]

    await detector.update(initial_stream_info, updated_clips)

    assert detector._current_stream_info == initial_stream_info
    assert detector._stream_titles == {initial_stream_info.title}
    # The new clip's URL should NOT be added because its title matched the stream title
    assert detector._handled_clips == {clip.url for clip in initial_clips}
    mock_event_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_update_new_clip_found_url_already_handled(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
) -> None:
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    clip_with_handled_url = models.Clip(
        title="Different Title Same URL",
        url=initial_clips[0].url,  # URL matches an already handled clip
        creator="Creator E",
        created_at="2023-01-01T00:15:00Z",
    )
    updated_clips = [*initial_clips, clip_with_handled_url]

    await detector.update(initial_stream_info, updated_clips)

    assert detector._current_stream_info == initial_stream_info
    assert detector._stream_titles == {initial_stream_info.title}
    # The handled clips set should remain unchanged
    assert detector._handled_clips == {clip.url for clip in initial_clips}
    mock_event_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_update_stream_info_and_clip_changed(  # noqa: PLR0913
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
    new_stream_info: models.StreamInfo,
    new_clip: models.Clip,
) -> None:
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    updated_clips = [*initial_clips, new_clip]
    await detector.update(new_stream_info, updated_clips)

    # Verify stream info update
    assert detector._current_stream_info == new_stream_info
    assert detector._stream_titles == {initial_stream_info.title, new_stream_info.title}

    # Verify clip update
    assert detector._handled_clips == {clip.url for clip in updated_clips}

    # Verify events published
    expected_calls = [
        call(events.StreamInfoChanged(stream_info=new_stream_info)),
        call(events.ClipFound(clip=new_clip)),
    ]
    mock_event_publisher.publish.assert_has_calls(expected_calls, any_order=True)
