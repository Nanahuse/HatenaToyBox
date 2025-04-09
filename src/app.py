from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from rich.logging import RichHandler

from common.core import Hub, controller
from common.feature import feature
from features import FeatureManager

logger = logging.getLogger("HatenaToyBox")

if __debug__:
    logger.setLevel(logging.DEBUG)
    feature.logger.setLevel(logging.DEBUG)
    controller.logger.setLevel(logging.DEBUG)
    system_config_file = Path("C:/HatenaToyBox/system_config.json")
else:
    logger.setLevel(logging.INFO)
    feature.logger.setLevel(logging.INFO)
    controller.logger.setLevel(logging.INFO)
    system_config_file = Path("./system_config.json")


if __name__ == "__main__":
    handler = RichHandler(
        rich_tracebacks=True,
        log_time_format="%H:%M:%S",
        show_path=__debug__,
        enable_link_path=__debug__,
    )
    handler.setFormatter(logging.Formatter("%(name)-22s - %(message)s"))

    logger.addHandler(handler)
    feature.logger.addHandler(handler)
    controller.logger.addHandler(handler)

    hub = Hub()
    feature_manager = FeatureManager(hub, system_config_file)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(asyncio.gather(hub.run(), feature_manager.run()))
    loop.close()
