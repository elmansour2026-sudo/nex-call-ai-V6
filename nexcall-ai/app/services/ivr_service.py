"""
NexCall AI — Service IVR (Interactive Voice Response)
Gère le menu vocal interactif et le routage des appels
"""
from dataclasses import dataclass, field
from typing import Optional
from app.config import settings


@dataclass
class IVROption:
    digit:       str
    label:       str
    intent:      str
    greeting:    str
    is_transfer: bool = False


# ── Configuration du menu IVR ───────────────────────────────────────────────
IVR_MENU: dict[str, IVROption] = {
    "1": IVROption(
        digit    = "1",
        label    = "Assurance Auto",
        intent   = "assurance_auto",
        greeting = (
            "Parfait ! Vous souhaitez en savoir plus sur nos offres d'assurance auto. "
            "Je suis {agent_name} de {company_name}. "
            "Pour commencer, puis-je avoir votre prénom ?"
        ),
    ),
    "2": IVROption(
        digit    = "2",
        label    = "Assurance Santé",
        intent   = "assurance_sante",
        greeting = (
            "Très bien ! Vous vous intéressez à nos offres d'assurance santé. "
            "Je suis {agent_name} de {company_name}. "
            "Puis-je vous demander votre prénom pour commencer ?"
        ),
    ),
    "3": IVROption(
        digit       = "3",
        label       = "Parler à un conseiller",
        intent      = "transfert_agent",
        greeting    = "Je vous mets en relation avec un de nos conseillers. Veuillez patienter un instant.",
        is_transfer = True,
    ),
    "0": IVROption(
        digit    = "0",
        label    = "Répéter le menu",
        intent   = "repeat_menu",
        greeting = "",
    ),
}

IVR_INVALID_MESSAGE = (
    "Je n'ai pas compris votre choix. "
    "Pour l'assurance auto, tapez 1. "
    "Pour l'assurance santé, tapez 2. "
    "Pour parler à un conseiller, tapez 3."
)

IVR_TIMEOUT_MESSAGE = (
    "Nous n'avons pas reçu votre saisie. "
    "Pour l'assurance auto, tapez 1. "
    "Pour l'assurance santé, tapez 2. "
    "Pour parler à un conseiller, tapez 3."
)


class IVRService:
    """Gère le menu IVR et le routage des appels entrants"""

    def get_greeting(self) -> str:
        """Retourne le message d'accueil IVR configuré"""
        return settings.IVR_GREETING

    def process_dtmf(self, digit: str) -> dict:
        """
        Traite une touche DTMF et retourne l'action à effectuer.
        Retourne : { valid, digit, intent, label, message, is_transfer }
        """
        option = IVR_MENU.get(digit)

        if not option:
            return {
                "valid":       False,
                "digit":       digit,
                "intent":      None,
                "label":       None,
                "message":     IVR_INVALID_MESSAGE,
                "is_transfer": False,
            }

        if option.intent == "repeat_menu":
            return {
                "valid":       True,
                "digit":       digit,
                "intent":      "repeat_menu",
                "label":       "Répéter le menu",
                "message":     self.get_greeting(),
                "is_transfer": False,
            }

        greeting = option.greeting.format(
            agent_name=settings.AI_AGENT_NAME,
            company_name=settings.AI_COMPANY_NAME,
        )

        return {
            "valid":       True,
            "digit":       digit,
            "intent":      option.intent,
            "label":       option.label,
            "message":     greeting,
            "is_transfer": option.is_transfer,
        }

    def get_menu_options(self) -> list[dict]:
        return [
            {
                "digit": opt.digit,
                "label": opt.label,
                "intent": opt.intent,
            }
            for opt in IVR_MENU.values()
            if opt.intent != "repeat_menu"
        ]

    def get_timeout_message(self) -> str:
        return IVR_TIMEOUT_MESSAGE


# Singleton
ivr_service = IVRService()
