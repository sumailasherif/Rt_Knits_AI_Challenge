"""
Agent 5 — Knowledge Agent

Responsibilities:
  - Run semantic vector search over ChromaDB (manuals, SOPs, history)
  - Return ranked snippets with relevance scores
  - Pre-format a combined context string for injection into Triage Agent
"""
from __future__ import annotations

import structlog

import chromadb
from openai import AsyncOpenAI

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.schemas.agents import KnowledgeInput, KnowledgeOutput, KnowledgeSnippet

log = structlog.get_logger(__name__)
settings = get_settings()

EMBED_MODEL = "text-embedding-3-small"


class KnowledgeAgent(BaseAgent):
    name = "KnowledgeAgent"

    def __init__(self) -> None:
        super().__init__()
        self._chroma = chromadb.HttpClient(
            host=settings.chroma_host, port=settings.chroma_port
        )
        self._collection = self._chroma.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Knowledge Agent for a factory CMMS.
You summarise retrieved maintenance documents into actionable repair guidance.
Keep summaries under 3 bullet points. Be factual and technical."""

    async def _embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=EMBED_MODEL, input=[text]
        )
        return response.data[0].embedding

    async def run(self, inp: KnowledgeInput) -> KnowledgeOutput:
        log.info("knowledge_agent_query", query=inp.query[:80], top_k=inp.top_k)

        # ── Step 1: Embed the query ───────────────────────────────────────────
        query_vector = await self._embed(inp.query)

        # ── Step 2: Vector search ─────────────────────────────────────────────
        where: dict | None = None
        if inp.asset_id:
            where = {"asset_id": inp.asset_id}

        try:
            results = self._collection.query(
                query_embeddings=[query_vector],
                n_results=inp.top_k,
                where=where if where else None,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            log.warning("knowledge_chroma_query_failed", error=str(exc))
            return KnowledgeOutput(snippets=[], combined_context="No relevant documents found.")

        snippets: list[KnowledgeSnippet] = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, dists):
            # Cosine distance → similarity score (lower dist = more similar)
            score = max(0.0, 1.0 - float(dist))
            snippets.append(
                KnowledgeSnippet(
                    doc_id=meta.get("doc_id", "unknown"),
                    title=meta.get("title", "Untitled"),
                    source_type=meta.get("source_type", "manual"),
                    snippet=doc[:400],
                    relevance_score=round(score, 3),
                )
            )

        # ── Step 3: Summarise for Triage injection ────────────────────────────
        if snippets:
            context_parts = [
                f"[{s.source_type.upper()}] {s.title}:\n{s.snippet}"
                for s in snippets
            ]
            combined_raw = "\n\n---\n\n".join(context_parts)

            summary_prompt = (
                f"Summarise the following maintenance documents into 3 concise "
                f"bullet points relevant to this fault query: '{inp.query}'\n\n"
                f"{combined_raw}"
            )
            try:
                combined_context = await self._chat(summary_prompt, json_mode=False, max_tokens=300)
            except Exception as exc:
                log.warning("knowledge_summary_failed", error=str(exc))
                combined_context = combined_raw[:600]
        else:
            combined_context = "No relevant documents found in the knowledge base."

        log.info("knowledge_agent_done", snippets_found=len(snippets))
        return KnowledgeOutput(snippets=snippets, combined_context=combined_context)
