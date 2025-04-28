import flet
import flet.core.types as flet_types


class ActivityControl(flet.Container):
    def __init__(
        self,
        who: str,
        span: list[flet.TextSpan],
        name_color: flet_types.ColorValue,
        activity_color: flet_types.ColorValue,
    ) -> None:
        padding = 3
        radius = 3
        spacing = 2

        activity_side_padding = 6

        super().__init__(
            content=flet.Row(
                [
                    flet.Container(
                        flet.Text(who, weight="bold", selectable=True),
                        width=120,
                        padding=padding,
                        bgcolor=name_color,
                        border_radius=flet.border_radius.all(radius),
                        alignment=flet.alignment.center_left,
                    ),
                    flet.Container(
                        flet.Text(spans=span, selectable=True),
                        padding=flet.padding.only(
                            left=activity_side_padding, right=activity_side_padding, top=padding, bottom=padding
                        ),
                        bgcolor=activity_color,
                        border_radius=flet.border_radius.all(radius),
                    ),
                ],
                spacing=spacing,
            ),
            margin=flet.margin.symmetric(vertical=spacing),
        )
