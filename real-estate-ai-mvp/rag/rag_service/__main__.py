"""python -m rag_service {migrate|api|worker} — one image, three roles."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from rag_service.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="rag_service")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    api = sub.add_parser("api")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8090)
    sub.add_parser("worker")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()

    if args.command == "migrate":
        from rag_service.migrate import migrate

        applied = migrate(settings)
        logging.getLogger("rag_service").info("migrations applied: %s", applied or "none (up to date)")
    elif args.command == "api":
        import uvicorn

        from rag_service.api import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port, workers=1)
    else:
        from rag_service.services import build_services
        from rag_service.worker import run

        async def go() -> None:
            services = build_services(settings)
            await services.db.open()
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop.set)
            try:
                await run(services, stop)
            finally:
                await services.db.close()
                await services.http.aclose()

        asyncio.run(go())


if __name__ == "__main__":
    main()
