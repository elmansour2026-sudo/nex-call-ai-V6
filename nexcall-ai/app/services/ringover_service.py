"""
NexCall AI v2 — Service Ringover (mis a jour avec appels sortants)
"""
import logging
from typing import Any, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)
RINGOVER_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class RingoverService:
    def __init__(self):
        self._api_key  = settings.RINGOVER_API_KEY
        self._base_url = settings.RINGOVER_API_URL.rstrip("/")

    def set_api_key(self, api_key: Optional[str]) -> None:
        """Met a jour la cle API Ringover a chaud (depuis la config BDD).
        Permet d'activer Ringover sans redemarrer le serveur."""
        self._api_key = api_key or None

    def _headers(self) -> dict:
        return {
            "Authorization": self._api_key or "",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    def _is_ready(self) -> bool:
        return bool(self._api_key)

    async def test_connection(self) -> dict:
        if not self._is_ready():
            return {"success": False, "connected": False, "error": "Cle API Ringover manquante"}
        async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
            try:
                r = await client.get(f"{self._base_url}/users", headers=self._headers())
                if r.status_code == 200:
                    return {"success": True, "connected": True, "data": r.json()}
                return {"success": False, "connected": False, "error": f"HTTP {r.status_code}"}
            except Exception as e:
                return {"success": False, "connected": False, "error": str(e)}

    async def get_calls(self, limit: int = 50, offset: int = 0) -> dict:
        if not self._is_ready():
            return {"success": False, "data": [], "error": "API non configuree"}
        async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
            try:
                r = await client.get(
                    f"{self._base_url}/calls",
                    headers=self._headers(),
                    params={"limit_count": limit, "start_offset": offset},
                )
                r.raise_for_status()
                return {"success": True, "data": r.json()}
            except Exception as e:
                return {"success": False, "data": [], "error": str(e)}

    async def transfer_call(self, call_id: str, to_number: str) -> dict:
        if not self._is_ready():
            return {"success": False, "error": "API non configuree"}
        async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
            try:
                r = await client.post(
                    f"{self._base_url}/calls/{call_id}/transfer",
                    headers=self._headers(),
                    json={"to": to_number},
                )
                r.raise_for_status()
                return {"success": True, "data": r.json()}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def make_outbound_call(self, from_number: str, to_number: str, webhook_url: str = "") -> dict:
        """
        Version corrigée suite au diagnostic de l'Agent Railway.
        Utilisation des clés explicites 'from_number' et 'to_number'.
        """
        if not self._is_ready():
            logger.error("[RINGOVER ERROR] Cle API manquante")
            return {"success": False, "error": "Cle API Ringover manquante"}

        # Formatage strict des numéros
        caller = from_number.strip() if from_number else settings.RINGOVER_PHONE_NUMBER
        if caller and not caller.startswith('+'):
            caller = f"+{caller}"

        target = to_number.strip() if to_number else ""
        if target and not target.startswith('+'):
            target = f"+{target}"

        # PAYLOAD SELON LE REQUISITION DE L'API V2
        payload = {
            "from_number": caller,
            "to_number": target
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url

        url = f"{self._base_url.rstrip('/')}/callback"
        
        logger.info(f"[RINGOVER CALL START] Sending payload to {url} : {payload}")

        async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
            try:
                r = await client.post(url, headers=self._headers(), json=payload)
                body_text = r.text
                
                logger.info(f"[RINGOVER RESPONSE] Status: {r.status_code} | Body: {body_text or '(vide)'}")
                
                if 200 <= r.status_code < 300:
                    return {"success": True, "status_code": r.status_code, "data": r.json() if body_text else {}}
                
                return {
                    "success": False,
                    "status_code": r.status_code,
                    "error": f"HTTP {r.status_code}: {body_text or 'reponse vide'}"
                }
            except Exception as e:
                logger.error(f"[RINGOVER EXCEPTION]: {str(e)}")
                return {"success": False, "error": str(e)}
    async def hangup_call(self, call_id: str) -> dict:
        if not self._is_ready():
            return {"success": False, "error": "API non configuree"}
        async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
            try:
                r = await client.delete(f"{self._base_url}/calls/{call_id}", headers=self._headers())
                r.raise_for_status()
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def get_numbers(self) -> dict:
        if not self._is_ready():
            return {"success": False, "data": [], "error": "API non configuree"}
        async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
            try:
                r = await client.get(f"{self._base_url}/numbers", headers=self._headers())
                r.raise_for_status()
                return {"success": True, "data": r.json()}
            except Exception as e:
                return {"success": False, "data": [], "error": str(e)}

    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        import hmac, hashlib
        secret = settings.RINGOVER_WEBHOOK_SECRET
        if not secret:
            return True
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


ringover_service = RingoverService()
