import flet


class VolumeSliderRow(flet.Row):  # type: ignore[misc]
    """音量調整のためのTextとSliderを持つRow"""

    def __init__(
        self,
        value: int = 50,
    ) -> None:
        self.slider = flet.Slider(
            label="{value}%",
            min=0,
            max=100,
            value=value,
            divisions=20,
            expand=True,
        )
        super().__init__(controls=[flet.Text("音量"), self.slider])

    @property
    def value(self) -> float | None:
        return self.slider.value  # type: ignore[no-any-return]

    @value.setter
    def value(self, new_value: float | None) -> None:
        self.slider.value = new_value
