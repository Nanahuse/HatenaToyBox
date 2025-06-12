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

    dlg_modal = flet.AlertDialog(
        modal=True,
        title=flet.Text("Please confirm"),
        content=flet.Text(
            spans=[
                flet.TextSpan("以下のリンクをクリックしてください:\n"),
                flet.TextSpan(
                    "https://www.google.com/",
                    url="https://www.google.com/",
                    style=flet.TextStyle(color=flet.Colors.BLUE),
                ),
            ]
        ),
        actions=[
            flet.TextButton("Yes", on_click=lambda e: page.close(dlg_modal)),
            flet.TextButton("No", on_click=lambda e: page.close(dlg_modal)),
        ],
        actions_alignment=flet.MainAxisAlignment.END,
        on_dismiss=lambda e: print("Modal dialog dismissed!"),
    )

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

    chat_page.time_line.add_system("アプリケーションが起動しました。")
    chat_page.time_line.add_chat("Test", "Hello World")
    chat_page.time_line.add_clip("Hoge", "Google", "https://www.google.com/")
    chat_page.time_line.add_raid("Piyo", "Google", "Google")
    chat_page.time_line.add_follower("Nyan")

    chat_page.header.update_status(ConnectionStatus.CONNECTED)

    page.open(dlg_modal)

    page.update()


flet.app(target=main)
