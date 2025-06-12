from enum import StrEnum

import flet


class Route(StrEnum):
    """アプリケーションのビューを定義する列挙型"""

    MAIN = "/"
    SETTINGS = "/settings"
    CONNECTION = "/connection"
    ABOUT = "/about"


class Router:
    def __init__(self, page: flet.Page) -> None:
        self.page = page
        self.history = list[Route]()

    def _go(self, route: Route) -> None:
        self.history.append(route)
        self.page.go(route)

    def go_main(self) -> None:
        self._go(Route.MAIN)

    def go_settings(self) -> None:
        self._go(Route.SETTINGS)

    def go_connection(self) -> None:
        self._go(Route.CONNECTION)

    def go_about(self) -> None:
        self._go(Route.ABOUT)

    def go_back(self) -> None:
        if len(self.history) >= 1:
            self.history.pop()

        if len(self.history) >= 1:
            self.page.go(self.history[-1])
        else:
            self.go_main()
