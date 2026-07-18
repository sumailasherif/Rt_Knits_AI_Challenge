"""
Knowledge base seeder — embeds factory SOPs, asset manuals, and historical
repair summaries into ChromaDB for the Knowledge Agent vector search.

Usage:
    python -m app.db.seed.seed_knowledge

The script reads from:
    data/knowledge/manuals/  *.txt  *.pdf (text extracted)
    data/knowledge/sops/     *.txt
    data/knowledge/history/  *.txt  (auto-generated from completed work orders)

If those directories don't exist, it falls back to generating synthetic
starter documents from the seeded work_orders and assets.
"""
import asyncio
import uuid
from pathlib import Path

import chromadb
import structlog
from openai import AsyncOpenAI
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import Asset, KnowledgeDoc, WorkOrder
from app.db.session import db_context

configure_logging()
log = structlog.get_logger(__name__)
settings = get_settings()

EMBED_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 512   # characters per chunk


def chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split text into overlapping chunks of ~size characters."""
    words = text.split()
    chunks, current = [], []
    total = 0
    for word in words:
        current.append(word)
        total += len(word) + 1
        if total >= size:
            chunks.append(" ".join(current))
            # 20% overlap
            overlap = max(1, len(current) // 5)
            current = current[-overlap:]
            total = sum(len(w) + 1 for w in current)
    if current:
        chunks.append(" ".join(current))
    return chunks or [text]


async def embed_texts(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """Batch embed using OpenAI text-embedding-3-small."""
    response = await client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]


async def seed_knowledge() -> None:
    chroma_client = chromadb.HttpClient(
        host=settings.chroma_host, port=settings.chroma_port
    )
    collection = chroma_client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )

    oai = AsyncOpenAI(api_key=settings.openai_api_key)

    docs_to_embed: list[dict] = []

    # ── 1. Load files from data/knowledge/ if present ─────────────────────────
    knowledge_dir = Path(settings.seed_data_dir) / "knowledge"
    for source_type, subdir in [("manual", "manuals"), ("SOP", "sops"), ("history", "history")]:
        folder = knowledge_dir / subdir
        if not folder.exists():
            continue
        for fpath in folder.glob("*.txt"):
            content = fpath.read_text(encoding="utf-8", errors="ignore").strip()
            if not content:
                continue
            docs_to_embed.append({
                "title": fpath.stem,
                "source_type": source_type,
                "asset_id": None,
                "raw_content": content,
            })
            log.debug("knowledge_file_loaded", file=str(fpath))

    # ── 2. Generate history docs from completed work orders in DB ─────────────
    async with db_context() as db:
        result = await db.execute(
            select(WorkOrder, Asset)
            .outerjoin(Asset, WorkOrder.asset_id == Asset.asset_id)
            .where(WorkOrder.status == "Completed")
            .where(WorkOrder.description.isnot(None))
            .limit(500)
        )
        rows = result.all()

    for wo, asset in rows:
        title = f"Repair history: {asset.name if asset else 'Unknown asset'} [{wo.wo_id[:8]}]"
        content = (
            f"Work Order: {wo.wo_id}\n"
            f"Asset: {asset.name if asset else 'N/A'}\n"
            f"Priority: {wo.priority}\n"
            f"Trade: {wo.required_trade or 'N/A'}\n"
            f"Description: {wo.description}\n"
            f"Status: {wo.status}\n"
            f"Estimated time: {wo.estimated_minutes} min\n"
        )
        docs_to_embed.append({
            "title": title,
            "source_type": "history",
            "asset_id": wo.asset_id,
            "raw_content": content,
        })

    # ── 3. Synthetic starter SOPs if nothing else available ───────────────────
    if not docs_to_embed:
        log.warning("no_knowledge_docs_found — inserting synthetic starter SOPs")
        docs_to_embed = _synthetic_sops()

    log.info("knowledge_docs_to_embed", total=len(docs_to_embed))

    # ── 4. Chunk, embed, and upsert into ChromaDB + postgres ─────────────────
    async with db_context() as db:
        for doc in docs_to_embed:
            chunks = chunk_text(doc["raw_content"])
            for i, chunk in enumerate(chunks):
                chroma_id = str(uuid.uuid4())
                # Embed
                try:
                    vectors = await embed_texts(oai, [chunk])
                    vector = vectors[0]
                except Exception as exc:
                    log.error("embed_failed", error=str(exc))
                    continue

                # Upsert into ChromaDB
                collection.upsert(
                    ids=[chroma_id],
                    embeddings=[vector],
                    documents=[chunk],
                    metadatas=[{
                        "title": doc["title"],
                        "source_type": doc["source_type"],
                        "asset_id": doc["asset_id"] or "",
                        "chunk_index": i,
                    }],
                )

                # Store reference in postgres
                db_doc = KnowledgeDoc(
                    doc_id=chroma_id,
                    asset_id=doc["asset_id"],
                    source_type=doc["source_type"],
                    title=f"{doc['title']} [chunk {i}]" if len(chunks) > 1 else doc["title"],
                    raw_content=chunk,
                    embedding_ref=chroma_id,
                )
                db.add(db_doc)

            log.debug("embedded_doc", title=doc["title"], chunks=len(chunks))

    log.info("knowledge_seed_complete", total_docs=len(docs_to_embed))


def _synthetic_sops() -> list[dict]:
    """Minimal starter SOPs when no files are provided."""
    return [
        {
            "title": "SOP-001: Knitting Machine Breakdown Procedure",
            "source_type": "SOP",
            "asset_id": None,
            "raw_content": (
                "1. Immediately stop the machine and set to manual mode.\n"
                "2. Record the error code displayed on the panel.\n"
                "3. Notify the Mechanical technician via CMMS.\n"
                "4. Do NOT restart until technician clears the fault.\n"
                "5. Document the fault with a photo attached to the work order.\n"
                "Typical resolution: bearing replacement or needle realignment. "
                "Estimated time: 45-90 minutes."
            ),
        },
        {
            "title": "SOP-002: Electrical Panel Trip Response",
            "source_type": "SOP",
            "asset_id": None,
            "raw_content": (
                "1. Identify the tripped breaker on the panel.\n"
                "2. DO NOT reset without Electrical technician sign-off.\n"
                "3. Isolate affected machinery.\n"
                "4. Log ticket as P0 if production is down, P1 otherwise.\n"
                "5. Electrical tech will inspect for overload or short circuit.\n"
                "Estimated resolution: 30-60 minutes for simple trips."
            ),
        },
        {
            "title": "SOP-003: Dyeing Vat Temperature Fault",
            "source_type": "SOP",
            "asset_id": None,
            "raw_content": (
                "1. Check the temperature sensor reading vs setpoint.\n"
                "2. If delta > 10°C, escalate to DyeTech pool immediately.\n"
                "3. Pause current batch if temperature is uncontrolled.\n"
                "4. Mechanical tech checks heating elements and thermostat.\n"
                "5. Do not drain the vat without supervisor approval.\n"
                "Common fix: thermostat replacement or sensor recalibration."
            ),
        },
        {
            "title": "Manual: Compressor Maintenance Schedule",
            "source_type": "manual",
            "asset_id": None,
            "raw_content": (
                "Weekly: Check oil level, drain condensate trap.\n"
                "Monthly: Replace air filter, inspect belt tension.\n"
                "Quarterly: Full service — oil change, valve inspection.\n"
                "Annual: Pressure vessel inspection by certified engineer.\n"
                "If pressure drops below 6 bar during operation: "
                "check for leaks in airline before calling technician."
            ),
        },
        {
            "title": "SOP-004: Water Leak Response",
            "source_type": "SOP",
            "asset_id": None,
            "raw_content": (
                "1. Identify source: supply pipe, drain, or machine coolant.\n"
                "2. Shut off nearest isolation valve if safe to do so.\n"
                "3. Log ticket as P1 (P0 if near electrical equipment).\n"
                "4. Civil/Plumbing technician to attend within 4 hours.\n"
                "5. Place warning signs and absorb standing water.\n"
                "Do not use electrical equipment in wet areas."
            ),
        },
    ]


if __name__ == "__main__":
    asyncio.run(seed_knowledge())
