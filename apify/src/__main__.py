"""Package entrypoint — ``python -m src`` (what `apify run` and the image invoke)."""

from __future__ import annotations

import asyncio

from .main import main

asyncio.run(main())
