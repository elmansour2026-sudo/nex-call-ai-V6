"""
NexCall AI v2 — Agent IA (mis a jour)
Support multi-agents : chaque session est lie a un Agent specifique.
Extraction QUALIFICATION en plus du LEAD_DATA.
"""
import json
import logging
import re
from io import BytesIO
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ConversationSession:
    def __init__(self, call_id: str, agent=None, ivr_choice: Optional[str] = None,
                 campaign_prompt: Optional[str] = None, prospect_name: str = ""):
        self.call_id          = call_id
        self.agent            = agent          # Objet Agent SQLAlchemy
        self.ivr_choice       = ivr_choice
        self.campaign_prompt  = campaign_prompt
        self.prospect_name    = prospect_name
        self.messages: list[dict[str, str]] = []
        self.lead_data: Optional[dict[str, Any]] = None
        self.qualification: Optional[dict[str, Any]] = None
        self.turn_count: int = 0

    def add_user_message(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})
        self.turn_count += 1

    def add_assistant_message(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})


class AIAgentService:
    def __init__(self):
        self._client = None              # client OpenAI par defaut (retrocompat)
        self._clients: dict = {}         # cache de clients par fournisseur
        self._sessions: dict[str, ConversationSession] = {}
        self._api_key_override: Optional[str] = None  # cle issue de la config BDD

    def set_api_key(self, api_key: Optional[str]) -> None:
        """Met a jour la cle OpenAI a chaud (depuis la config BDD) et invalide
        les clients en cache pour qu'ils soient recrees avec la nouvelle cle."""
        self._api_key_override = api_key or None
        self._client = None
        self._clients = {}

    def _effective_openai_key(self) -> Optional[str]:
        from app.config import settings
        return self._api_key_override or settings.OPENAI_API_KEY

    def is_openai_configured(self) -> bool:
        return bool(self._effective_openai_key())

    def _get_client(self):
        """Client OpenAI par defaut (utilise quand aucun agent/provider precise)."""
        if self._client is not None:
            return self._client
        from openai import AsyncOpenAI
        key = self._effective_openai_key()
        if not key:
            return None
        self._client = AsyncOpenAI(api_key=key)
        return self._client

    def _get_provider_client(self, provider: str):
        """Retourne un client adapte au fournisseur de l'agent.
        Les fournisseurs compatibles OpenAI (openai, mistral, azure, custom via
        base_url) utilisent le SDK openai. Anthropic utilise son propre SDK.
        Le design permet d'ajouter d'autres fournisseurs sans casser l'existant."""
        from app.config import settings
        provider = (provider or "openai").lower()

        if provider in self._clients:
            return self._clients[provider]

        client = None
        try:
            if provider == "anthropic":
                key = getattr(settings, "ANTHROPIC_API_KEY", None)
                if key:
                    from anthropic import AsyncAnthropic
                    client = AsyncAnthropic(api_key=key)
            elif provider == "mistral":
                key = getattr(settings, "MISTRAL_API_KEY", None) or self._effective_openai_key()
                if key:
                    from openai import AsyncOpenAI
                    client = AsyncOpenAI(api_key=key, base_url="https://api.mistral.ai/v1")
            elif provider == "custom":
                base = getattr(settings, "CUSTOM_AI_BASE_URL", None)
                key = getattr(settings, "CUSTOM_AI_API_KEY", None) or self._effective_openai_key()
                if base and key:
                    from openai import AsyncOpenAI
                    client = AsyncOpenAI(api_key=key, base_url=base)
            else:  # openai (defaut) et azure compatible
                client = self._get_client()
        except Exception as e:
            logger.error(f"[ai_agent] init client provider={provider}: {e}")
            client = None

        # Repli sur OpenAI si le provider demande n'est pas configurable
        if client is None and provider != "openai":
            client = self._get_client()

        self._clients[provider] = client
        return client

    def _build_system_prompt(self, session: ConversationSession) -> str:
        from app.config import settings
        from app.services.agent_service import agent_service

        if session.agent:
            # Utiliser le prompt de l'agent specifique
            return agent_service.build_system_prompt(
                agent=session.agent,
                prospect_name=session.prospect_name or "Madame/Monsieur",
                company_name=settings.AI_COMPANY_NAME,
            )

        # Fallback: prompt generique si pas d'agent assigne
        ivr_labels = {
            "1": "Assurance Auto",
            "2": "Mutuelle Sante",
            "3": "Transfert conseiller",
            "assurance_auto":   "Assurance Auto",
            "assurance_sante":  "Mutuelle Sante",
            "mutuelle_sante":   "Mutuelle Sante",
        }
        ivr_context = ivr_labels.get(session.ivr_choice or "", "Service general")
        campaign_ctx = f"\nContexte campagne :\n{session.campaign_prompt}" if session.campaign_prompt else ""

        return f"""\
Tu es {settings.AI_AGENT_NAME}, conseiller(e) IA pour {settings.AI_COMPANY_NAME}.
IMPORTANT : Tu es une intelligence artificielle. Mentionne-le toujours en debut d'appel.
Contexte IVR : {ivr_context}{campaign_ctx}

Objectifs : accueillir, comprendre le besoin, qualifier, proposer transfert si interesse.
Reponses courtes (2-3 phrases max). Ne jamais prétendre être humain(e).

<QUALIFICATION>
{{
  "intent": "interested|not_interested|callback|wrong_number",
  "lead_score": 0,
  "prospect_name": null,
  "need_summary": null,
  "budget": null,
  "urgency": null,
  "action": "transfer_agent|callback|close",
  "should_transfer": false
}}
</QUALIFICATION>"""

    # ── Sessions ────────────────────────────────────────────────────────────
    def create_session(self, call_id: str, agent=None, ivr_choice: Optional[str] = None,
                       campaign_prompt: Optional[str] = None, prospect_name: str = "") -> ConversationSession:
        session = ConversationSession(call_id, agent, ivr_choice, campaign_prompt, prospect_name)
        self._sessions[call_id] = session
        return session

    def get_session(self, call_id: str) -> Optional[ConversationSession]:
        return self._sessions.get(call_id)

    def end_session(self, call_id: str) -> Optional[ConversationSession]:
        return self._sessions.pop(call_id, None)

    # ── Chat ─────────────────────────────────────────────────────────────────
    async def chat(self, call_id: str, user_message: str, agent=None,
                   ivr_choice: Optional[str] = None, campaign_prompt: Optional[str] = None,
                   prospect_name: str = "") -> dict[str, Any]:
        from app.config import settings

        # Choix du fournisseur selon l'agent (defaut: OpenAI)
        provider = (getattr(agent, "ai_provider", None) or "openai").lower()
        client = self._get_provider_client(provider)
        if not client:
            name = agent.name if agent else settings.AI_AGENT_NAME
            return {
                "text": f"Bonjour, je suis {name}. Le service IA n'est pas encore configure.",
                "lead_data": None, "qualification": None,
                "error": f"Fournisseur IA '{provider}' non configure",
            }

        session = self.get_session(call_id) or self.create_session(
            call_id, agent=agent, ivr_choice=ivr_choice,
            campaign_prompt=campaign_prompt, prospect_name=prospect_name,
        )
        if agent and not session.agent:
            session.agent = agent
        if prospect_name and not session.prospect_name:
            session.prospect_name = prospect_name

        session.add_user_message(user_message)
        system_prompt = self._build_system_prompt(session)
        messages_for_api = [{"role": "system", "content": system_prompt}] + session.messages

        model = (getattr(agent, "ai_model", None) or settings.OPENAI_MODEL)
        temp  = (getattr(agent, "ai_temperature", None) if agent else None)
        if temp is None:
            temp = settings.AI_TEMPERATURE
        max_tokens = settings.OPENAI_MAX_TOKENS

        try:
            if provider == "anthropic":
                # API Anthropic : system separe, pas de role system dans messages
                resp = await client.messages.create(
                    model=model, max_tokens=max_tokens, temperature=temp,
                    system=system_prompt, messages=session.messages,
                )
                raw_text = "".join(
                    block.text for block in resp.content if getattr(block, "type", "") == "text"
                ) or ""
            else:
                # Fournisseurs compatibles OpenAI (openai, mistral, azure, custom)
                response = await client.chat.completions.create(
                    model=model, messages=messages_for_api,
                    max_tokens=max_tokens, temperature=temp,
                )
                raw_text = response.choices[0].message.content or ""

            qualification = self._extract_qualification(raw_text)
            lead_data = self._extract_lead_data(raw_text)
            clean_text = self._strip_all_blocks(raw_text).strip()

            session.add_assistant_message(raw_text)

            if qualification:
                if session.qualification:
                    session.qualification.update({k: v for k, v in qualification.items() if v is not None})
                else:
                    session.qualification = qualification

            if lead_data:
                if session.lead_data:
                    session.lead_data.update({k: v for k, v in lead_data.items() if v is not None})
                else:
                    session.lead_data = lead_data

            return {
                "text": clean_text, "lead_data": session.lead_data,
                "qualification": session.qualification, "error": None,
            }

        except Exception as e:
            logger.exception(f"[ai_agent] chat error call={call_id} provider={provider}: {e}")
            return {
                "text": "Je suis desole, je rencontre une difficulte technique.",
                "lead_data": session.lead_data, "qualification": session.qualification,
                "error": str(e),
            }

    # ── TTS ──────────────────────────────────────────────────────────────────
    async def text_to_speech(self, text: str, voice: str = "nova") -> Optional[bytes]:
        from app.config import settings
        client = self._get_client()
        if not client:
            return None
        try:
            response = await client.audio.speech.create(
                model=settings.OPENAI_TTS_MODEL, voice=voice, input=text,
            )
            return response.content
        except Exception as e:
            logger.error(f"[ai_agent] TTS error: {e}")
            return None

    # ── STT ──────────────────────────────────────────────────────────────────
    async def speech_to_text(self, audio_bytes: bytes, language: str = "fr") -> Optional[str]:
        from app.config import settings
        client = self._get_client()
        if not client:
            return None
        try:
            buf = BytesIO(audio_bytes)
            buf.name = "audio.wav"
            transcript = await client.audio.transcriptions.create(
                model=settings.OPENAI_STT_MODEL, file=buf, language=language,
            )
            return transcript.text
        except Exception as e:
            logger.error(f"[ai_agent] STT error: {e}")
            return None

    # ── Resume ───────────────────────────────────────────────────────────────
    async def summarize_call(self, transcript: str, agent_name: str = "Agent IA") -> str:
        from app.config import settings
        client = self._get_client()
        if not client:
            return "Resume non disponible (OpenAI non configure)"
        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": f"Tu resumes des appels du centre d'appels de {agent_name}. Sois concis, structure, en francais. 3-5 points cles avec emojis."},
                    {"role": "user", "content": f"Resumes cet appel :\n\n{transcript}"},
                ],
                max_tokens=300, temperature=0.3,
            )
            return response.choices[0].message.content or "Resume vide"
        except Exception as e:
            return f"Erreur resume : {e}"

    # ── Helpers prives ───────────────────────────────────────────────────────
    @staticmethod
    def _extract_qualification(text: str) -> Optional[dict]:
        match = re.search(r"<QUALIFICATION>\s*(.*?)\s*</QUALIFICATION>", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_lead_data(text: str) -> Optional[dict]:
        match = re.search(r"<LEAD_DATA>\s*(.*?)\s*</LEAD_DATA>", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _strip_all_blocks(text: str) -> str:
        text = re.sub(r"\s*<QUALIFICATION>.*?</QUALIFICATION>\s*", "", text, flags=re.DOTALL)
        text = re.sub(r"\s*<LEAD_DATA>.*?</LEAD_DATA>\s*", "", text, flags=re.DOTALL)
        return text


ai_agent = AIAgentService()
