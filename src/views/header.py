import flet

from .router import Router


class Header(flet.Row):  # type: ignore[misc]
    def __init__(self, router: Router, title: str) -> None:
        self.back_button = flet.IconButton(
            icon=flet.Icons.ARROW_BACK_IOS_NEW_OUTLINED,
            tooltip="戻る",
            icon_size=30,
            on_click=lambda _: router.go_back(),
        )

        super().__init__(
            [self.back_button, flet.Text(title, style=flet.TextThemeStyle.HEADLINE_MEDIUM)],
            alignment=flet.MainAxisAlignment.START,
        )
