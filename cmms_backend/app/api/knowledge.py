"""
Router: /knowledge

Endpoints for the Knowledge Agent:
  POST /knowledge/search   — semantic vector search
  POST /knowledge/docs     — ingest a new document into ChromaDB
  GET  /knowledge/docs     — list all knowledge_doc records
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge_agent import KnowledgeAgent
from app.db.models import KnowledgeDoc
from app.db.session import get_db
from app.schemas.agents import KnowledgeInput, KnowledgeOutput
from app.schemas.knowledge_doc import KnowledgeDocCreate, KnowledgeDocRead

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])
log = structlog.get_logger(__name__)

# Lazy singleton — not created at import time so app starts even if ChromaDB is down
_knowledge: KnowledgeAgent | None = None


def _get_knowledge_agent() -> KnowledgeAgent:
    global _knowledge
    if _knowledge is None:
        _knowledge = KnowledgeAgent()
    return _knowledge


@router.post("/search", response_model=KnowledgeOutput)
async def search_knowledge(payload: KnowledgeInput) -> KnowledgeOutput:
    """Semantic search over the knowledge base."""
    return await _get_knowledge_agent().run(payload)


@router.post("/docs", response_model=KnowledgeDocRead, status_code=status.HTTP_201_CREATED)
async def ingest_document(
    payload: KnowledgeDocCreate,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeDocRead:
    """
    Ingest a new document: embed it into ChromaDB and save a reference in postgres.
    """
    import uuid
    from openai import AsyncOpenAI
    from app.core.config import get_settings

    settings = get_settings()
    oai = AsyncOpenAI(api_key=settings.openai_api_key)

    if not payload.raw_content:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="raw_content is required for ingestion")

    # Embed
    response = await oai.embeddings.create(
        model="text-embedding-3-small", input=[payload.raw_content[:2000]]
    )
    vector = response.data[0].embedding
    chroma_id = str(uuid.uuid4())

    # Upsert into ChromaDB
    _get_knowledge_agent()._get_collection().upsert(
        ids=[chroma_id],
        embeddings=[vector],
        documents=[payload.raw_content],
        metadatas=[{
            "title": payload.title,
            "source_type": payload.source_type,
            "asset_id": payload.asset_id or "",
        }],
    )

    # Save reference in postgres
    doc = KnowledgeDoc(
        doc_id=chroma_id,
        asset_id=payload.asset_id,
        source_type=payload.source_type,
        title=payload.title,
        raw_content=payload.raw_content,
        embedding_ref=chroma_id,
    )
    db.add(doc)
    await db.flush()
    log.info("knowledge_doc_ingested", doc_id=chroma_id, title=payload.title)
    return KnowledgeDocRead.model_validate(doc)


@router.get("/docs", response_model=list[KnowledgeDocRead])
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[KnowledgeDocRead]:
    result = await db.execute(
        select(KnowledgeDoc).order_by(KnowledgeDoc.created_at.desc()).limit(200)
    )
    docs = result.scalars().all()
    return [KnowledgeDocRead.model_validate(d) for d in docs]
