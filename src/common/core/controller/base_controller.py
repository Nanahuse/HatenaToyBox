from __future__ import annotations

import logging

logger = logging.getLogger("Core")


class BaseController:
    def __init__(self) -> None:
        self.logger = logger.getChild(type(self).__name__)
