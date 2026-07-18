"""
Agent 1 — Intake Agent

Responsibilities:
  - Transcribe voice notes (Whisper API)
  - Analyse photos (GPT-4o vision)
  - Translate multilingual messages (EN / FR / HI / BN)
  - Extract structured FaultDetail from raw text/audio/image
  - Detect missing info and formulate a clarification question
"""
from __future__ import annotations

import base64
from typing import Optional

import httpx
import structlog

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.schemas.agents import FaultDetail, IntakeInput, IntakeOutput

log = structlog.get_logger(__name__)
settings = get_settings()

# Languages spoken on the RT Knits factory floor
SUPPORTED_LANGUAGES = {
    "en": "English",
    "fr": "French (Mauritian Creole)",
    "hi": "Hindi",
    "bn": "Bengali/Bangladeshi",
}


class IntakeAgent(BaseAgent):
    name = "IntakeAgent"

    @property
    def system_prompt(self) -> str:
        return """You are the Intake Agent for an AI-powered factory CMMS at RT Knits, Mauritius.

Your job is to process incoming maintenance reports from factory floor workers via WhatsApp.
Workers may send text, voice notes, or photos. They speak English, French/Creole, Hindi, or Bengali.

TASKS:
1. If the input is in a language other than English, translate it to English first.
2. Extract a structured fault report with these fields:
   - asset_name: the machine/equipment mentioned (null if unclear)
   - fault_description: clear English description of the problem
   - location: where on the factory floor (null if not mentioned)
   - urgency_signal: any words suggesting immediate danger or production stop
   - detected_language: ISO code of the original language
   - translated_text: English translation (null if already English)
3. Determine if the report has enough information to proceed:
   - is_complete: true if we know WHAT is broken and WHERE
   - clarification_needed: a concise question to ask the worker if is_complete=false

RULES:
- Never invent asset names — use null if not mentioned.
- Keep fault_description factual and concise (1-2 sentences).
- urgency_signal examples: "machine stopped", "fire", "sparks", "water flooding", "smell of burning".
- Always respond in JSON matching the FaultDetail + is_complete + clarification_needed schema.
"""

    async def _fetch_whatsapp_media(self, media_id: str) -> bytes:
        """Fetch raw media bytes from the WhatsApp Cloud API."""
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: get download URL
            url_resp = await client.get(
                f"{settings.whatsapp_api_base}/{settings.whatsapp_api_version}/{media_id}",
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            )
            url_resp.raise_for_status()
            download_url = url_resp.json()["url"]

            # Step 2: download the actual file
            media_resp = await client.get(
                download_url,
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            )
            media_resp.raise_for_status()
            return media_resp.content

    async def _transcribe_audio(self, media_id: str) -> str:
        """Download voice note and transcribe via Whisper API."""
        log.info("intake_transcribing_audio", media_id=media_id)
        audio_bytes = await self._fetch_whatsapp_media(media_id)

        # Write to a temporary buffer with a .ogg extension (WhatsApp audio format)
        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "voice_note.ogg"

        response = await self._client.audio.transcriptions.create(
            model=settings.openai_whisper_model,
            file=audio_file,
        )
        return response.text

    async def _analyse_image(self, media_id: str) -> str:
        """Download image and get GPT-4o vision analysis."""
        log.info("intake_analysing_image", media_id=media_id)
        image_bytes = await self._fetch_whatsapp_media(media_id)
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        response = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You are a factory maintenance expert. "
                                "Describe the fault or damage visible in this image. "
                                "Be specific: identify the equipment type, visible damage, "
                                "and any safety concerns. Keep your response under 100 words."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=200,
        )
        return response.choices[0].message.content or ""

    async def run(self, inp: IntakeInput, requester_id: str, request_id: str) -> IntakeOutput:
        log.info("intake_agent_start", request_id=request_id, phone=inp.sender_phone)

        audio_transcript: Optional[str] = None
        photo_analysis: Optional[str] = None

        # ── Step 1: Multimodal preprocessing ─────────────────────────────────
        if inp.audio_media_id:
            try:
                audio_transcript = await self._transcribe_audio(inp.audio_media_id)
                log.info("intake_transcribed", chars=len(audio_transcript))
            except Exception as exc:
                log.error("intake_transcription_failed", error=str(exc))

        if inp.image_media_id:
            try:
                photo_analysis = await self._analyse_image(inp.image_media_id)
                log.info("intake_image_analysed", chars=len(photo_analysis))
            except Exception as exc:
                log.error("intake_image_analysis_failed", error=str(exc))

        # ── Step 2: Build the extraction prompt ───────────────────────────────
        parts: list[str] = []
        if inp.raw_text:
            parts.append(f"Worker message: {inp.raw_text}")
        if audio_transcript:
            parts.append(f"Voice note transcription: {audio_transcript}")
        if photo_analysis:
            parts.append(f"Photo analysis: {photo_analysis}")
        if inp.language_hint and inp.language_hint != "en":
            parts.append(f"Detected language hint: {SUPPORTED_LANGUAGES.get(inp.language_hint, inp.language_hint)}")

        combined_input = "\n".join(parts) or "No message content provided."

        prompt = f"""Extract structured fault details from this factory maintenance report.

{combined_input}

Respond ONLY with a JSON object with these exact keys:
{{
  "asset_name": string or null,
  "fault_description": string,
  "location": string or null,
  "urgency_signal": string or null,
  "detected_language": string (ISO 639-1 code),
  "translated_text": string or null,
  "is_complete": boolean,
  "clarification_needed": string or null
}}"""

        # ── Step 3: LLM extraction ─────────────────────────────────────────────
        raw = await self._chat(prompt, json_mode=True)
        data = self._parse_json(raw)

        fault = FaultDetail(
            asset_name=data.get("asset_name"),
            asset_id=None,  # resolved later by Triage against DB
            fault_description=data.get("fault_description", combined_input[:200]),
            location=data.get("location"),
            urgency_signal=data.get("urgency_signal"),
            photo_analysis=photo_analysis,
            audio_transcript=audio_transcript,
            detected_language=data.get("detected_language", inp.language_hint or "en"),
            translated_text=data.get("translated_text"),
        )

        output = IntakeOutput(
            request_id=request_id,
            requester_id=requester_id,
            fault=fault,
            is_complete=data.get("is_complete", True),
            clarification_needed=data.get("clarification_needed"),
        )

        log.info(
            "intake_agent_complete",
            request_id=request_id,
            is_complete=output.is_complete,
            asset=fault.asset_name,
        )
        return output
