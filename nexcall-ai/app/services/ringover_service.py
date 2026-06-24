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
        """Lance un VRAI appel sortant via le mecanisme callback de Ringover.
        
        CORRECTION CRITIQUE : Ringover V2 exige un 'device_id' ou un 'user_id' 
        dans le champ 'from', et non un numéro de téléphone au format string.
        """
        if not self._is_ready():
            logger.error("[RINGOVER ERROR] Ringover non configure (cle API manquante)")
            return {"success": False, "error": "Cle API Ringover manquante"}

        # 1. Récupérer dynamiquement le premier Device ID ou User ID disponible
        from_id = None
        async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
            try:
                user_res = await client.get(f"{self._base_url}/users", headers=self._headers())
                if user_res.status_code == 200:
                    users_data = user_res.json().get("users", [])
                    if users_data:
                        # On cherche un device actif ou on prend l'ID du premier utilisateur
                        first_user = users_data[0]
                        from_id = first_user.get("user_id")
                        # Si l'utilisateur a des devices, on prend le premier device_id
                        if first_user.get("devices"):
                            from_id = first_user["devices"][0].get("device_id")
            except Exception as e:
                logger.warning(f"[RINGOVER] Impossible de lister les users/devices: {e}")

        # Si on n'a pas trouvé d'ID via l'API, on tente une valeur par défaut ou le numéro brut
        if not from_id:
            # Nettoyage au cas où
            from_id = from_number.strip() if from_number else settings.RINGOVER_PHONE_NUMBER
            if from_id and not from_id.startswith('+') and from_id.isdigit():
                # Si c'est juste des chiffres, on laisse passer, mais l'API préfère l'ID numérique
                pass

        # 2. Formater le numéro de destination (le prospect)
        target = to_number.strip() if to_number else ""
        if target and not target.startswith('+'):
            target = f"+{target}"

        endpoint = (settings.RINGOVER_CALL_ENDPOINT or "/callback").strip()
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        url = f"{self._base_url}{endpoint}"

        # PAYLOAD OFFICIEL V2
        payload = {
            "from": from_id,  # C'est l'ID du device/user qui va sonner en premier
            "to": target      # Le numéro du prospect
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url

        logger.info(f"[RINGOVER CALL START] target={target} from_id={from_id} url={url}")

        async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
            try:
                r = await client.post(url, headers=self._headers(), json=payload)
            except Exception as e:
                logger.error(f"[RINGOVER ERROR] exception reseau vers Ringover: {e}")
                return {"success": False, "error": f"Erreur reseau Ringover: {e}"}

            body_text = ""
            try:
                body_text = r.text[:1000]
            except Exception:
                pass

            if 200 <= r.status_code < 300:
                data = {}
                try:
                    data = r.json()
                except Exception:
                    pass
                call_id = None
                if isinstance(data, dict):
                    call_id = (data.get("call_id") or data.get("id")
                               or data.get("call_uuid") or data.get("uuid"))
                logger.info(
                    f"[RINGOVER RESPONSE] status={r.status_code} "
                    f"call_id={call_id} response={body_text or '(vide)'}"
                )
                return {"success": True, "status_code": r.status_code,
                        "call_id": str(call_id) if call_id else None, "data": data}

            logger.error(
                f"[RINGOVER ERROR] status={r.status_code} response={body_text or '(vide)'} "
                f"(appel depuis ID {from_id} -> {target} REFUSE)"
            )
            return {
                "success": False,
                "status_code": r.status_code,
                "error": f"HTTP {r.status_code}: {body_text or 'reponse vide'}",
            }
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
