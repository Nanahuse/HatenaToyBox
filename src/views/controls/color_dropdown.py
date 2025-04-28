import flet


class ColorDropdown(flet.Dropdown):
    """色を選択するためのドロップダウンメニュー"""

    def __init__(self, width: int) -> None:
        super().__init__(
            label="色",
            options=[
                flet.dropdown.Option("Blue"),
                flet.dropdown.Option("Green"),
                flet.dropdown.Option("Orange"),
                flet.dropdown.Option("Purple"),
            ],
            value="Blue",
            width=width,
        )
