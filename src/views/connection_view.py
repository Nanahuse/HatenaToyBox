import flet

from .constants import Route
from .header import Header
from .router import Router


class ConnectionView:
    def __init__(self, router: Router) -> None:
        self.padding = 10

        self.header = Header(router, "接続")

    def build_view(self) -> flet.View:
        return flet.View(
            Route.SETTINGS,
            controls=[
                self.header,
                flet.Column(
                    [
                        flet.Text("Botアカウント", style=flet.TextThemeStyle.HEADLINE_SMALL),
                        flet.Row([flet.Text("接続状態:", width=100), flet.Text("接続済み")]),
                        flet.Row([flet.Text("アカウント名:", width=100), flet.Text("Nanahuse")]),
                        flet.Row([flet.Text("属性:", width=100), flet.Text("Streamer")]),
                        flet.Button("切断", icon=flet.icons.CANCEL_OUTLINED, width=100),
                    ]
                ),
                flet.Column(
                    controls=[
                        flet.Text("Streamerアカウント", style=flet.TextThemeStyle.HEADLINE_SMALL),
                        flet.Row([flet.Text("接続状態:", width=100), flet.Text("未接続")]),
                        flet.Row([flet.Text("アカウント名:", width=100), flet.Text("???")]),
                        flet.Row([flet.Text("属性:", width=100), flet.Text("???")]),
                        flet.Button("接続", icon=flet.icons.LINK_OUTLINED, width=100),
                    ]
                ),
            ],
            vertical_alignment=flet.MainAxisAlignment.START,
            padding=self.padding,
        )
