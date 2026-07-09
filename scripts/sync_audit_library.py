#!/usr/bin/env python3
"""
Sync the proprietary audit-pattern corpus into Qdrant (tier 1 grounding).

Source of truth: the Notion "Audit Library — Rich Imports" page. The
extraction step turns those audits into structured pattern rows stored in
data/audit_library/*.json (one file per client). This script embeds those
rows and upserts them into QDRANT_AUDIT_COLLECTION.

Usage:
    python3 scripts/sync_audit_library.py            # embed + upsert corpus
    python3 scripts/sync_audit_library.py --dry-run  # validate corpus only

Required env (see .env.example):
    QDRANT_URL, QDRANT_API_KEY, EMBEDDING_API_KEY
    (EMBEDDING_PROVIDER / EMBEDDING_MODEL default to voyage / voyage-3.5-lite)

Refreshing after new audits land in Notion: re-run the extraction (a Claude
session over the Notion library, same JSON shape) to update data/audit_library/,
then re-run this script. Point IDs are deterministic (uuid5 of client+title),
so re-syncs update existing points instead of duplicating them.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from analyzer.pdp.knowledge import embed_texts  # noqa: E402

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "audit_library"
NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
REQUIRED_FIELDS = {"client", "category", "title", "issue", "recommendations"}
BATCH = 64


def load_corpus() -> list[dict]:
    rows = []
    files = sorted(CORPUS_DIR.glob("*.json"))
    if not files:
        sys.exit(f"No corpus files in {CORPUS_DIR} — run the Notion extraction first.")
    for path in files:
        data = json.loads(path.read_text())
        for i, row in enumerate(data):
            missing = REQUIRED_FIELDS - set(row)
            if missing:
                sys.exit(f"{path.name}[{i}] missing fields: {missing}")
            rows.append(row)
        print(f"  {path.name}: {len(data)} patterns")
    return rows


def doc_text(row: dict) -> str:
    """The text that gets embedded — mirrors what queries describe."""
    recs = " | ".join(row.get("recommendations") or [])
    return (
        f"ecommerce {row['category']}: {row['title']}\n"
        f"Issue: {row['issue']}\n"
        f"Why it matters: {row.get('why_it_matters') or ''}\n"
        f"Recommendations: {recs}"
    )


async def sync(rows: list[dict]) -> None:
    base = settings.QDRANT_URL.rstrip("/")
    headers = {"api-key": settings.QDRANT_API_KEY}
    collection = settings.QDRANT_AUDIT_COLLECTION

    async with httpx.AsyncClient(timeout=30) as client:
        # Embed in batches (documents, not queries)
        vectors: list[list[float]] = []
        for i in range(0, len(rows), BATCH):
            chunk = [doc_text(r) for r in rows[i : i + BATCH]]
            vectors.extend(
                await embed_texts(
                    client, chunk,
                    settings.EMBEDDING_PROVIDER, settings.EMBEDDING_MODEL,
                    settings.EMBEDDING_API_KEY, input_type="document",
                )
            )
            print(f"  embedded {min(i + BATCH, len(rows))}/{len(rows)}")

        dim = len(vectors[0])

        # Create the collection if it doesn't exist (idempotent PUT)
        exists = (await client.get(f"{base}/collections/{collection}", headers=headers)).status_code == 200
        if not exists:
            resp = await client.put(
                f"{base}/collections/{collection}",
                json={"vectors": {"size": dim, "distance": "Cosine"}},
                headers=headers,
            )
            resp.raise_for_status()
            print(f"  created collection {collection} (dim={dim}, cosine)")

        # Upsert with deterministic IDs so re-syncs update, not duplicate
        for i in range(0, len(rows), BATCH):
            points = []
            for row, vector in zip(rows[i : i + BATCH], vectors[i : i + BATCH]):
                points.append(
                    {
                        "id": str(uuid.uuid5(NAMESPACE, f"{row['client']}::{row['title']}")),
                        "vector": vector,
                        "payload": {
                            "client": row["client"],
                            "business_type": "ecommerce",
                            "category": row["category"],
                            "title": row["title"],
                            "issue": row["issue"],
                            "why_it_matters": row.get("why_it_matters", ""),
                            "recommendations": row.get("recommendations", []),
                            "impact": row.get("impact"),
                            "source": row["client"],
                            "source_page": row.get("source_page", ""),
                            "embedding_model": settings.EMBEDDING_MODEL,
                        },
                    }
                )
            resp = await client.put(
                f"{base}/collections/{collection}/points?wait=true",
                json={"points": points},
                headers=headers,
            )
            resp.raise_for_status()
            print(f"  upserted {min(i + BATCH, len(rows))}/{len(rows)}")

    print(f"Done: {len(rows)} audit patterns live in '{collection}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="validate corpus, no upload")
    args = parser.parse_args()

    print(f"Loading corpus from {CORPUS_DIR} ...")
    rows = load_corpus()
    clients = sorted({r["client"] for r in rows})
    print(f"{len(rows)} patterns across {len(clients)} clients: {', '.join(clients)}")

    if args.dry_run:
        print("Dry run — corpus is valid, nothing uploaded.")
        return

    if not (settings.QDRANT_URL and settings.QDRANT_API_KEY and settings.EMBEDDING_API_KEY):
        sys.exit("Set QDRANT_URL, QDRANT_API_KEY, and EMBEDDING_API_KEY (see .env.example)")

    asyncio.run(sync(rows))


if __name__ == "__main__":
    main()
