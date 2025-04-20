# mypy: disable-error-code="attr-defined"

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.base_model import BaseEvent, BaseService
from common.core.controller import EventController, ServiceController
from common.core.event_publisher import EventPublisher
from common.core.hub import Hub
from common.core.service_caller import ServiceCaller


@pytest.fixture
def mock_event_controller() -> MagicMock:
    """モックされた EventController を提供します。"""
    controller = MagicMock(spec=EventController)
    controller.add_handler = MagicMock()
    controller.run = AsyncMock()
    controller.close = AsyncMock()  # close メソッドもモックに追加 (Hub.close から呼ばれるため)
    return controller


@pytest.fixture
def mock_service_controller() -> MagicMock:
    """モックされた ServiceController を提供します。"""
    controller = MagicMock(spec=ServiceController)
    controller.add_handler = MagicMock()
    # ServiceController に run/close があれば同様に追加
    return controller


class DummyEvent(BaseEvent):
    """テスト用のダミーイベントクラス"""


class DummyService(BaseService[str, int]):
    """テスト用のダミーサービスクラス"""


# モックハンドラを定義
MockEventHandler = MagicMock(spec=Callable[[DummyEvent], Coroutine[Any, Any, None]])
MockServiceHandler = MagicMock(spec=Callable[[str], Coroutine[Any, Any, int]])


# --- フィクスチャ ---


@pytest.fixture
def mocked_hub(mock_event_controller: MagicMock, mock_service_controller: MagicMock) -> Hub:
    """
    内部コントローラーがモックに置き換えられた Hub インスタンスを提供します。
    これにより、Hub がコントローラーに呼び出しを正しく委譲するかどうかを確認できます。
    """
    # Hub の __init__ 内でコントローラーがインスタンス化される箇所をパッチ
    with (
        patch("common.core.hub.EventController", return_value=mock_event_controller),
        patch("common.core.hub.ServiceController", return_value=mock_service_controller),
    ):
        return Hub()


# --- テストケース ---


def test_create_publisher(mocked_hub: Hub) -> None:
    """create_publisher が正しいコントローラーにリンクされた EventPublisher を返すことをテストします。"""
    # コンストラクタ呼び出しを確認するために EventPublisher をパッチ
    with patch("common.core.hub.EventPublisher", spec=EventPublisher) as MockEventPublisher:  # noqa: N806
        publisher = mocked_hub.create_publisher()

        # EventPublisher が正しくインスタンス化されたことを確認
        MockEventPublisher.assert_called_once_with(mocked_hub._event_controller)
        # 返されたオブジェクトがモックによって作成されたインスタンスであることを確認
        assert publisher is MockEventPublisher.return_value


def test_create_caller(mocked_hub: Hub) -> None:
    """create_caller が正しいコントローラーにリンクされた ServiceCaller を返すことをテストします。"""
    # コンストラクタ呼び出しを確認するために ServiceCaller をパッチ
    with patch("common.core.hub.ServiceCaller", spec=ServiceCaller) as MockServiceCaller:  # noqa: N806
        caller = mocked_hub.create_caller()

        # ServiceCaller が正しくインスタンス化されたことを確認
        MockServiceCaller.assert_called_once_with(mocked_hub._service_controller)
        # 返されたオブジェクトがモックによって作成されたインスタンスであることを確認
        assert caller is MockServiceCaller.return_value


def test_add_service_handler_delegates(mocked_hub: Hub) -> None:
    """add_service_handler が ServiceController に委譲することをテストします。"""
    mock_handler = MockServiceHandler()
    service_type = DummyService

    mocked_hub.add_service_handler(service_type, mock_handler)

    # サービスコントローラーの add_handler が正しい引数で呼び出されたことをアサート
    mocked_hub._service_controller.add_handler.assert_called_once_with(service_type, mock_handler)


def test_add_event_handler_delegates(mocked_hub: Hub) -> None:
    """add_event_handler が EventController に委譲することをテストします。"""
    mock_handler = MockEventHandler()
    event_type = DummyEvent

    mocked_hub.add_event_handler(event_type, mock_handler)

    # イベントコントローラーの add_handler が正しい引数で呼び出されたことをアサート
    mocked_hub._event_controller.add_handler.assert_called_once_with(event_type, mock_handler)


@pytest.mark.asyncio
async def test_run() -> None:
    """終了のテスト"""

    hub = Hub()

    await asyncio.wait_for(asyncio.gather(hub.run(), hub.close()), timeout=1.0)
