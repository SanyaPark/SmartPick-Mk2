from __future__ import annotations

import argparse

from .pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk and embed card disclosures")
    parser.add_argument(
        "--cards",
        nargs="*",
        help="Optional list of card names to process (default: all)",
    )
    parser.add_argument(
        "--chunks-only",
        action="store_true",
        help="Generate chunk files without embeddings",
    )
    parser.add_argument(
        "--embed-only",
        action="store_true",
        help="Embed existing chunks without regenerating chunk files",
    )

    args = parser.parse_args()

    if args.chunks_only and args.embed_only:
        parser.error("--chunks-only and --embed-only cannot be used together")

    run_pipeline(
        card_filter=args.cards,
        chunks_only=args.chunks_only,
        embed_only=args.embed_only,
    )


if __name__ == "__main__":
    main()
