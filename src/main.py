from typing import cast

import flet

from views.connection_view import ConnectionView
from views.constants import Route
from views.controls.connection_indicator import ConnectionStatus
from views.main_view import MainView
from views.router import Router
from views.setting_view import SettingView


def main(page: flet.Page) -> None:
    router = Router(page)

    chat_page = MainView(router)
    settings_page = SettingView(router)
    connection_view = ConnectionView(router)

    # ページ設定
    page.title = "Hatena Toy Box"

    def route_change(e: flet.RouteChangeEvent) -> None:
        page = cast("flet.Page", e.page)
        page.views.clear()
        match e.route:
            case Route.MAIN:
                page.views.append(chat_page.build_view())
            case Route.SETTINGS:
                page.views.append(settings_page.build_view())
            case Route.CONNECTION:
                page.views.append(connection_view.build_view())
            case _:
                pass
        page.update()

    page.on_route_change = route_change

    router.go_main()

    chat_page.add_activity("System", "アプリケーションが起動しました。")
    chat_page.time_line.add_clip("System", "Google", "https://www.google.com/")
    chat_page.time_line.add_raid("System", "Google", "Google")

    chat_page.header.update_status(ConnectionStatus.CONNECTED)

    page.update()


if __name__ == "__main__":
    flet.app(target=main)
