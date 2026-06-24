"""
NexCall AI v2 — Service Ringover (appels sortants robustes)

Cle de la correction :
  - L'appel sortant utilise le mecanisme *callback* de Ringover (POST /callback),
    et NON /calls (qui sert a lister les appels).
  - Le payload est envoye avec un fallback automatique sur plusieurs formats
    (numeros E.164 en chaine, puis entiers, puis cles from/to) car la v2 de
    Ringover est stricte sur le format des numeros — un 400 a corps vide vient
    quasi toujours de la.
  - Tout est encapsule dans des try/except qui renvoient TOUJOURS un dict :
    aucune exception ne peut remonter et faire tomber le worker Uvicorn.
"""
import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Timeout court par tentative pour ne jamais bloquer le worker.
RINGOVER_TIMEOUT = httpx.Timeout(12.0, connect=5.0)


class RingoverService:
    def __init__(self):
        self._api_key  = self._clean_key(settings.RINGOVER_API_KEY)
        self._base_url = (settings.RINGOVER_API_URL or "https://public-api.ringover.com/v2").rstrip("/")

    # ── Cle API ──────────────────────────────────────────────────────────────
    @staticmethod
    def _clean_key(key: Optional[str]) -> Optional[str]:
        """Nettoie la cle : retire espaces, retours-ligne et eventuels guillemets.
        (Une cle collee dans une variable Railway contient souvent un \\n final
        qui rend l'entete Authorization invalide et fait echouer la requete.)"""
        if not key:
            return None
        k = str(key).strip().strip('"').strip("'").strip()
        return k or None

    def set_api_key(self, api_key: Optional[str]) -> None:
        """Met a jour la cle API a chaud (depuis la config BDD), sans redemarrage."""
        self._api_key = self._clean_key(api_key)

    def _headers(self) -> dict:
        """Entetes Ringover. La cle brute va directement dans Authorization
        (PAS de prefixe 'Bearer'). Construit defensivement."""
        key = self._api_key or ""
        return {
            "Authorization": key,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    def _is_ready(self) -> bool:
        return bool(self._api_key)

    # ── Normalisation des numeros ────────────────────────────────────────────
    @staticmethod
    def _to_e164(num: Any) -> str:
        """Renvoie le numero au format E.164 avec '+'. FR : 0X… -> +33X…"""
        s = str(num or "").strip()
        digits = "".join(c for c in s if c.isdigit())
        if not digits:
            return ""
        if s.startswith("+"):
            return "+" + digits
        if digits.startswith("00"):
            return "+" + digits[2:]
        if digits.startswith("0") and len(digits) == 10:   # numero FR national
            return "+33" + digits[1:]
        return "+" + digits

    @staticmethod
    def _to_int(e164: str) -> Optional[int]:
        """Convertit '+33189701703' -> 33189701703 (entier, sans '+')."""
        digits = "".join(c for c in str(e164 or "") if c.isdigit())
        return int(digits) if digits else None

    # ── Diagnostics ──────────────────────────────────────────────────────────
    async def test_connection(self) -> dict:
        if not self._is_ready():
            return {"success": False, "connected": False, "error": "Cle API Ringover manquante"}
        try:
            async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
                r = await client.get(f"{self._base_url}/users", headers=self._headers())
                if 200 <= r.status_code < 300:
                    return {"success": True, "connected": True}
                return {"success": False, "connected": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "connected": False, "error": str(e)}

    async def get_calls(self, limit: int = 50, offset: int = 0) -> dict:
        if not self._is_ready():
            return {"success": False, "data": [], "error": "API non configuree"}
        try:
            async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
                r = await client.get(
                    f"{self._base_url}/calls",
                    headers=self._headers(),
                    params={"limit_count": limit, "start_offset": offset},
                )
                r.raise_for_status()
                return {"success": True, "data": r.json()}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    async def get_numbers(self) -> dict:
        if not self._is_ready():
            return {"success": False, "data": [], "error": "API non configuree"}
        try:
            async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
                r = await client.get(f"{self._base_url}/numbers", headers=self._headers())
                r.raise_for_status()
                return {"success": True, "data": r.json()}
        except Exception as e:
            return {"success": False, "data": [], "error": str(e)}

    async def transfer_call(self, call_id: str, to_number: str) -> dict:
        if not self._is_ready():
            return {"success": False, "error": "API non configuree"}
        try:
            async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
                r = await client.post(
                    f"{self._base_url}/calls/{call_id}/transfer",
                    headers=self._headers(),
                    json={"to": self._to_e164(to_number)},
                )
                r.raise_for_status()
                return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def hangup_call(self, call_id: str) -> dict:
        if not self._is_ready():
            return {"success": False, "error": "API non configuree"}
        try:
            async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
                r = await client.delete(f"{self._base_url}/calls/{call_id}", headers=self._headers())
                r.raise_for_status()
                return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Appel sortant (callback) ─────────────────────────────────────────────
    async def make_outbound_call(self, from_number: str, to_number: str, webhook_url: str = "") -> dict:
        """Lance un VRAI appel sortant via le callback Ringover.

        Fonctionnement en 2 temps :
          1. Ringover fait sonner le device associe a `from_number` (votre ligne).
          2. Des que c'est decroche, Ringover compose `to_number` (la cible).

        Robustesse :
          - Essaie plusieurs formats de payload jusqu'a obtenir un 2xx (fallback).
          - Succes UNIQUEMENT si Ringover repond 2xx.
          - Aucune exception ne remonte : on renvoie toujours un dict.
        """
        # ── Garde-fou global : rien ne peut faire crasher le worker ──────────
        try:
            if not self._is_ready():
                logger.error("[CALL ERROR] Ringover non configure (cle API manquante)")
                return {"success": False, "error": "Cle API Ringover manquante"}

            # Numero appelant : parametre, sinon variable d'environnement.
            caller_e164 = self._to_e164(from_number) or self._to_e164(settings.RINGOVER_PHONE_NUMBER)
            target_e164 = self._to_e164(to_number)

            if not caller_e164:
                logger.error("[CALL ERROR] Aucun numero appelant (from_number / RINGOVER_PHONE_NUMBER)")
                return {"success": False, "error": "Numero appelant manquant (RINGOVER_PHONE_NUMBER)"}
            if not target_e164:
                logger.error("[CALL ERROR] Numero cible invalide")
                return {"success": False, "error": "Numero cible invalide"}

            caller_int = self._to_int(caller_e164)
            target_int = self._to_int(target_e164)

            endpoint = (getattr(settings, "RINGOVER_CALL_ENDPOINT", None) or "/callback").strip()
            if not endpoint.startswith("/"):
                endpoint = "/" + endpoint
            url = f"{self._base_url}{endpoint}"

            # Variantes de payload essayees dans l'ordre. La premiere qui renvoie
            # un 2xx est retenue (les variantes refusees ne declenchent AUCUN appel).
            variants = [
                ("from_number/to_number (E164)", {"from_number": caller_e164, "to_number": target_e164}),
                ("from_number/to_number (int)",  {"from_number": caller_int,  "to_number": target_int}),
                ("from/to (E164)",               {"from": caller_e164,        "to": target_e164}),
            ]

            logger.info(f"[CALL START] from={caller_e164} to={target_e164} url={url}")

            last_status = None
            last_body = ""

            async with httpx.AsyncClient(timeout=RINGOVER_TIMEOUT) as client:
                for label, payload in variants:
                    if webhook_url:
                        payload = {**payload, "webhook_url": webhook_url}
                    try:
                        r = await client.post(url, headers=self._headers(), json=payload)
                    except Exception as e:
                        # Erreur reseau sur cette variante : on tente la suivante.
                        last_status, last_body = None, f"exception reseau: {e}"
                        logger.error(f"[CALL RESPONSE] variante='{label}' exception={e}")
                        continue

                    body_text = ""
                    try:
                        body_text = (r.text or "")[:1000]
                    except Exception:
                        pass
                    last_status, last_body = r.status_code, body_text
                    logger.info(f"[CALL RESPONSE] variante='{label}' status={r.status_code} "
                                f"body={body_text or '(vide)'}")

                    if 200 <= r.status_code < 300:
                        data = {}
                        try:
                            data = r.json()
                        except Exception:
                            data = {}
                        call_id = None
                        if isinstance(data, dict):
                            call_id = (data.get("call_id") or data.get("id")
                                       or data.get("call_uuid") or data.get("uuid"))
                        logger.info(f"[CALL OK] Ringover a accepte l'appel ({label}) "
                                    f"call_id={call_id}")
                        return {
                            "success": True,
                            "status_code": r.status_code,
                            "call_id": str(call_id) if call_id else None,
                            "payload_used": label,
                            "data": data,
                        }

                    # 401/403 = probleme d'auth/droits : inutile d'essayer les autres.
                    if r.status_code in (401, 403):
                        break

            logger.error(f"[CALL FAIL] Toutes les variantes refusees. "
                         f"Dernier status={last_status} body={last_body or '(vide)'}")
            hint = ""
            if last_status == 400:
                hint = (" — Ringover refuse la requete. Verifiez que RINGOVER_PHONE_NUMBER "
                        "est bien un numero Ringover de votre compte AVEC un appareil "
                        "(application/softphone) connecte en ligne pour decrocher la 1ere etape.")
            elif last_status in (401, 403):
                hint = " — Cle API invalide ou droits insuffisants (cochez 'Call' dans les droits de la cle)."
            return {
                "success": False,
                "status_code": last_status,
                "error": f"HTTP {last_status}: {last_body or 'reponse vide'}{hint}",
            }

        except Exception as e:
            # Filet de securite ultime : on n'autorise JAMAIS une exception a remonter.
            logger.exception(f"[CALL ERROR] Exception inattendue dans make_outbound_call: {e}")
            return {"success": False, "error": f"Exception interne: {e}"}

    # ── Webhooks ─────────────────────────────────────────────────────────────
    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        import hmac, hashlib
        secret = settings.RINGOVER_WEBHOOK_SECRET
        if not secret:
            return True
        try:
            expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature or "")
        except Exception:
            return False


ringover_service = RingoverService()
