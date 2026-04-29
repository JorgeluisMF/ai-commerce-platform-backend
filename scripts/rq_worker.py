#!/usr/bin/env python3
"""Run: python scripts/rq_worker.py  (queues: emails, embeddings, post_checkout)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from redis import Redis  # noqa: E402
from rq import Queue, Worker  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    conn = Redis.from_url(settings.redis_url)
    names = ["emails", "embeddings", "post_checkout"]
    queues = [Queue(n, connection=conn) for n in names]
    Worker(queues, connection=conn).work()


if __name__ == "__main__":
    main()
