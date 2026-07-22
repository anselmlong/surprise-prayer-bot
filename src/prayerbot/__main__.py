"""Entry point: python -m prayerbot."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update

from .config import Config
from .storage import Storage


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("prayerbot")

    config = Config()
    storage = Storage(config.db_path)

    from .bot import build_application

    app = build_application(config, storage)
    app.bot_data["startup_time"] = datetime.now(timezone.utc)

    log.info(
        "prayer bot starting — pool has %d member(s)",
        storage.get_pool_size(),
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()