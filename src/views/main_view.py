import flet

from views.constants import Route

from .controls.connection_indicator import ConnectionIndicator, ConnectionStatus
from .controls.time_line import TimeLine
from .router import Router


class Header(flet.Row):  # type: ignore[misc]
    def __init__(self) -> None:
        self.connection_indicator = ConnectionIndicator()
        self.settings_icon = flet.IconButton(
            icon=flet.Icons.SETTINGS_OUTLINED,
            tooltip="設定",
            icon_size=30,
        )

        super().__init__(
            controls=[
                self.connection_indicator,
                self.settings_icon,
            ],
            alignment=flet.MainAxisAlignment.END,
        )

    def update_status(self, status: ConnectionStatus) -> None:
        self.connection_indicator.update_status(status)


class MainView:
    def __init__(self, router: Router) -> None:
        self.padding = 10

        self.header = Header()
        self.header.connection_indicator.on_click = lambda _: router.go_connection()
        self.header.settings_icon.on_click = lambda _: router.go_settings()

        self.time_line = TimeLine()

    def build_view(self) -> flet.View:
        return flet.View(
            Route.MAIN,
            controls=[
                # --- Header ---
                flet.Container(
                    content=self.header,
                    padding=flet.padding.only(
                        left=self.padding,
                        top=self.padding,
                        right=self.padding,
                        bottom=self.padding,
                    ),
                ),
                # --- Activity Feed ---
                flet.Container(
                    content=self.time_line,
                    expand=True,
                    padding=10,
                    margin=flet.margin.only(left=self.padding, right=self.padding),
                ),
            ],
            # View全体のpaddingは0にする
            padding=0,
            # Viewのalignment設定
            vertical_alignment=flet.MainAxisAlignment.START,
            horizontal_alignment=flet.CrossAxisAlignment.STRETCH,
        )
