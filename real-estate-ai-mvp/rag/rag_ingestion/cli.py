import argparse
import logging
import time
from .config import Settings
from .database import Database
from .storage import LocalStorage
from .service import Service
from .worker import Worker


def main():
    parser = argparse.ArgumentParser(description='EstraOS ingestion (not voice retrieval)')
    parser.add_argument('command', choices=['migrate', 'api', 'worker', 'reembed'])
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--workspace')
    parser.add_argument('--actor', type=int)
    parser.add_argument('--model')
    parser.add_argument('--revision')
    args = parser.parse_args()
    settings = Settings.from_env()
    databases = {ws: Database(dsn, ws) for ws, dsn in settings.stores.items()}
    if args.command == 'migrate':
        for ws, db in databases.items():
            db.migrate()
            print(f'Initialized knowledge schema for workspace {ws}')
    elif args.command == 'api':
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
    elif args.command == 'reembed':
        if args.workspace not in databases or not args.actor or args.actor <= 0:
            parser.error('reembed needs a configured --workspace and existing positive CRM --actor ID')
        result = Service(databases[args.workspace], LocalStorage(settings.storage_path)).reembed(args.actor, args.model, args.revision)
        print(result)
    else:
        from concurrent.futures import ThreadPoolExecutor
        from .interpretation import MistralInterpreter
        interpreter = MistralInterpreter(settings.mistral_key, settings.mistral_model) if settings.mistral_key else None
        # One thread per database prevents a long client job from blocking another client.
        # Database locks also serialize multiple worker processes safely.
        def run(db):
            worker = Worker(db, LocalStorage(settings.storage_path), settings.embedder, interpreter)
            while True:
                try:
                    worked = worker.run_once()
                except Exception as error:
                    logging.error('Worker for workspace %s unavailable (%s)', db.workspace, type(error).__name__)
                    worked = False
                if args.once:
                    return
                if not worked:
                    time.sleep(settings.poll_seconds)
        with ThreadPoolExecutor(max_workers=len(databases)) as pool:
            list(pool.map(run, databases.values()))


if __name__ == '__main__':
    main()
