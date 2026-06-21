from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.db.session import make_engine, make_sessionmaker
from app.rag.embeddings import FastEmbedBackend
from app.rag.reembed import reembed_directory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-embed all Meridian source documents with FastEmbed.")
    parser.add_argument("--source-dir", default="sl_docs")
    parser.add_argument("--allow-fallback", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    backend = FastEmbedBackend(allow_fallback_embeddings=args.allow_fallback or settings.allow_fallback_embeddings)
    with sessionmaker() as db:
        summary = reembed_directory(Path(args.source_dir), db=db, backend=backend)
        print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
