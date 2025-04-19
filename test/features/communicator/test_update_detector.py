import logging
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from common.core import EventPublisher
from features.communicator.update_detector import UpdateDetector
from schemas import events, models


@pytest.fixture
def mock_logger() -> MagicMock:
    """ロガーのモックを提供します。"""
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """EventPublisher のモックを提供します。"""
    return AsyncMock(spec=EventPublisher)


@pytest.fixture
def initial_stream_info() -> models.StreamInfo:
    """初期の StreamInfo モデルを提供します。"""
    return models.StreamInfo(
        title="Initial Stream Title",
        game_name="Initial Game",
        is_live=True,
        viewer_count=100,
    )


@pytest.fixture
def initial_clips() -> list[models.Clip]:
    """初期の Clip モデルのリストを提供します。"""
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
    """新しい StreamInfo モデルを提供します。"""
    return models.StreamInfo(
        title="New Stream Title",
        game_name="New Game",
        is_live=True,
        viewer_count=150,
    )


@pytest.fixture
def new_clip() -> models.Clip:
    """新しい Clip モデルを提供します。"""
    return models.Clip(
        title="New Clip",
        url="http://newclip.com",
        creator="Creator C",
        created_at="2023-01-01T00:05:00Z",
    )


def test_init(mock_logger: MagicMock, mock_event_publisher: AsyncMock) -> None:
    """UpdateDetector の初期化をテストします。"""
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
    """初回 initialize の呼び出しをテストします。"""
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    # 状態が正しく初期化されたことを確認します
    assert detector._current_stream_info == initial_stream_info
    assert detector._stream_titles == {initial_stream_info.title}
    assert detector._handled_clips == {clip.url for clip in initial_clips}


def test_initialize_already_initialized(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
    new_stream_info: models.StreamInfo,
    new_clip: models.Clip,
) -> None:
    """すでに初期化されている場合に initialize を呼び出しても状態が変わらないことをテストします。"""
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    # 比較のために初期状態を保存します
    original_stream_info = detector._current_stream_info
    original_titles = detector._stream_titles.copy()
    original_clips = detector._handled_clips.copy()

    # 再度 initialize を試みます
    detector.initialize(new_stream_info, [new_clip])

    # 状態が変わっていないことをアサートします
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
    """update を呼び出しても変更がない場合の動作をテストします。"""
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    # 同じ情報で update を呼び出します
    await detector.update(initial_stream_info, initial_clips)

    # 状態が変わらず、イベントが発行されないことを確認します
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
    """StreamInfo が変更された場合の update の動作をテストします。"""
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    # 新しい StreamInfo で update を呼び出します
    await detector.update(new_stream_info, initial_clips)

    # StreamInfo が更新され、タイトルが追加され、イベントが発行されたことを確認します
    assert detector._current_stream_info == new_stream_info
    assert detector._stream_titles == {initial_stream_info.title, new_stream_info.title}
    assert detector._handled_clips == {clip.url for clip in initial_clips}  # クリップは変わらない
    mock_event_publisher.publish.assert_called_once_with(events.StreamInfoChanged(stream_info=new_stream_info))


@pytest.mark.asyncio
async def test_update_new_clip_found(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
    new_clip: models.Clip,
) -> None:
    """新しいクリップが見つかった場合の update の動作をテストします。"""
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    # 新しいクリップを含むリストで update を呼び出します
    updated_clips = [*initial_clips, new_clip]
    await detector.update(initial_stream_info, updated_clips)

    # StreamInfo は変わらず、新しいクリップの URL が追加され、イベントが発行されたことを確認します
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
    """新しいクリップのタイトルが現在の配信タイトルと一致する場合、イベントが発行されないことをテストします。"""
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    # 配信タイトルと同じタイトルのクリップを作成します
    clip_with_stream_title = models.Clip(
        title=initial_stream_info.title,  # タイトルが配信と一致します
        url="http://titlematchclip.com",
        creator="Creator D",
        created_at="2023-01-01T00:10:00Z",
    )
    updated_clips = [*initial_clips, clip_with_stream_title]

    # update を呼び出します
    await detector.update(initial_stream_info, updated_clips)

    # 状態は変わりますが、イベントは発行されません
    assert detector._current_stream_info == initial_stream_info
    assert detector._stream_titles == {initial_stream_info.title}
    # 新しいクリップの URL は、タイトルが一致したため追加 *されない* ことを確認します
    assert detector._handled_clips == {clip.url for clip in initial_clips}
    mock_event_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_update_new_clip_found_url_already_handled(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
) -> None:
    """新しいクリップの URL がすでに処理済みの場合、イベントが発行されないことをテストします。"""
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    # 処理済みの URL を持つクリップを作成します
    clip_with_handled_url = models.Clip(
        title="Different Title Same URL",
        url=initial_clips[0].url,  # URL が処理済みのクリップと一致します
        creator="Creator E",
        created_at="2023-01-01T00:15:00Z",
    )
    updated_clips = [*initial_clips, clip_with_handled_url]

    # update を呼び出します
    await detector.update(initial_stream_info, updated_clips)

    # 状態は変わらず、イベントは発行されません
    assert detector._current_stream_info == initial_stream_info
    assert detector._stream_titles == {initial_stream_info.title}
    # 処理済みクリップのセットは変わらないことを確認します
    assert detector._handled_clips == {clip.url for clip in initial_clips}
    mock_event_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_update_stream_info_and_clip_changed(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    initial_stream_info: models.StreamInfo,
    initial_clips: list[models.Clip],
    new_stream_info: models.StreamInfo,
    new_clip: models.Clip,
) -> None:
    """StreamInfo とクリップの両方が変更された場合の update の動作をテストします。"""
    detector = UpdateDetector(mock_logger, mock_event_publisher)
    detector.initialize(initial_stream_info, initial_clips)

    # 新しい StreamInfo と新しいクリップを含むリストで update を呼び出します
    updated_clips = [*initial_clips, new_clip]
    await detector.update(new_stream_info, updated_clips)

    # StreamInfo の更新を確認します
    assert detector._current_stream_info == new_stream_info
    assert detector._stream_titles == {initial_stream_info.title, new_stream_info.title}

    # クリップの更新を確認します
    assert detector._handled_clips == {clip.url for clip in updated_clips}

    # 両方のイベントが発行されたことを確認します
    expected_calls = [
        call(events.StreamInfoChanged(stream_info=new_stream_info)),
        call(events.ClipFound(clip=new_clip)),
    ]
    assert mock_event_publisher.publish.await_count == 2
    actual_calls = mock_event_publisher.publish.await_args_list
    # 期待される両方の呼び出しが実際の呼び出しリストに含まれているか確認します
    assert expected_calls[0] in actual_calls
    assert expected_calls[1] in actual_calls
