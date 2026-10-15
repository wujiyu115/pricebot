"""PriceBot 入口：python main.py --host 0.0.0.0 --port 6106"""

from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="PriceBot - 国内金价监控推送系统")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "6106")))
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    from app.server.app import create_app
    from app.utils.logger import setup_logger

    setup_logger()

    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()

