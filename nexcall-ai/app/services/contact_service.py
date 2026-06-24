"""
NexCall AI v3 — Service Contacts
Import enrichi (dedup + numeros invalides + blacklist), export CSV, filtres.
"""
import csv
import io
import re
import logging
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prospect import Prospect, ProspectStatus
from app.services.blacklist_service import blacklist_service

logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^\+?[0-9]{8,15}$")


class ContactService:

    def normalize_phone(self, phone: str) -> str:
        p = "".join(c for c in (phone or "") if c.isdigit() or c == "+")
        if p.startswith("0") and len(p) == 10:
            p = "+33" + p[1:]
        elif p.startswith("33") and not p.startswith("+"):
            p = "+" + p
        return p

    def is_valid_phone(self, phone: str) -> bool:
        return bool(PHONE_RE.match(phone))

    async def import_csv(self, db: AsyncSession, csv_content: str,
                         campaign_id: Optional[int] = None,
                         agent_id: Optional[int] = None,
                         delimiter: str = ",") -> dict[str, Any]:
        """
        Importe des contacts. Verifie doublons, numeros invalides, blacklist.
        Colonnes : nom, prenom, telephone, date_naissance, date_resiliation,
                   ancienne_offre, informations_client
        """
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)

        def norm_key(k: str) -> str:
            return (k or "").strip().lower().replace(" ", "_") \
                .replace("é", "e").replace("è", "e").replace("'", "_")

        # Pre-charger blacklist + numeros existants pour verif rapide
        blacklisted = await blacklist_service.get_all_phones(db)
        existing_result = await db.execute(select(Prospect.phone))
        existing_phones = {row[0] for row in existing_result.all()}

        imported, duplicates, invalid, blocked = 0, 0, 0, 0
        errors = []
        seen_in_file = set()

        for i, row in enumerate(reader, start=2):
            r = {norm_key(k): (v or "").strip() for k, v in row.items() if k}

            raw_phone = r.get("telephone") or r.get("tel") or r.get("phone") or ""
            phone = self.normalize_phone(raw_phone)

            if not phone:
                invalid += 1
                errors.append(f"Ligne {i}: telephone manquant")
                continue
            if not self.is_valid_phone(phone):
                invalid += 1
                errors.append(f"Ligne {i}: numero invalide ({raw_phone})")
                continue
            if phone in blacklisted:
                blocked += 1
                continue
            if phone in existing_phones or phone in seen_in_file:
                duplicates += 1
                continue

            seen_in_file.add(phone)
            prospect = Prospect(
                phone            = phone,
                first_name       = r.get("prenom") or r.get("firstname") or None,
                last_name        = r.get("nom") or r.get("lastname") or None,
                birth_date       = r.get("date_naissance") or r.get("naissance") or None,
                resiliation_date = r.get("date_resiliation") or r.get("resiliation") or None,
                old_offer        = r.get("ancienne_offre") or r.get("offre") or None,
                city             = r.get("ville") or r.get("city") or None,
                extra_info       = r.get("informations_client") or r.get("informations") or r.get("info") or None,
                campaign_id      = campaign_id,
                agent_id         = agent_id,
                status           = ProspectStatus.NOUVEAU.value,
            )
            db.add(prospect)
            imported += 1

        # Mise a jour compteur campagne
        if imported > 0 and campaign_id:
            from app.models.campaign import Campaign
            result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
            campaign = result.scalar_one_or_none()
            if campaign:
                campaign.total_prospects = (campaign.total_prospects or 0) + imported

        await db.flush()
        return {
            "imported":   imported,
            "duplicates": duplicates,
            "invalid":    invalid,
            "blocked":    blocked,
            "errors":     errors[:20],
        }

    async def import_numbers(self, db: AsyncSession, numbers: list[str],
                             campaign_id: Optional[int] = None,
                             agent_id: Optional[int] = None) -> dict[str, Any]:
        """Import rapide d'une liste de numeros seuls (telephone obligatoire,
        aucun autre champ requis)."""
        blacklisted = await blacklist_service.get_all_phones(db)
        existing_result = await db.execute(select(Prospect.phone))
        existing_phones = {row[0] for row in existing_result.all()}

        imported, duplicates, invalid, blocked = 0, 0, 0, 0
        seen = set()

        for raw in numbers:
            phone = self.normalize_phone(raw)
            if not phone or not self.is_valid_phone(phone):
                invalid += 1
                continue
            if phone in blacklisted:
                blocked += 1
                continue
            if phone in existing_phones or phone in seen:
                duplicates += 1
                continue
            seen.add(phone)
            db.add(Prospect(
                phone=phone, campaign_id=campaign_id, agent_id=agent_id,
                status=ProspectStatus.NOUVEAU.value,
            ))
            imported += 1

        if imported > 0 and campaign_id:
            from app.models.campaign import Campaign
            result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
            campaign = result.scalar_one_or_none()
            if campaign:
                campaign.total_prospects = (campaign.total_prospects or 0) + imported

        await db.flush()
        return {"imported": imported, "duplicates": duplicates,
                "invalid": invalid, "blocked": blocked, "errors": []}

    async def export_csv(self, db: AsyncSession, campaign_id: Optional[int] = None,
                         status: Optional[str] = None) -> str:
        """Exporte les contacts au format CSV."""
        q = select(Prospect).where(Prospect.is_archived == False)
        if campaign_id:
            q = q.where(Prospect.campaign_id == campaign_id)
        if status:
            q = q.where(Prospect.status == status)
        q = q.order_by(Prospect.id)
        result = await db.execute(q)
        prospects = result.scalars().all()

        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([
            "ID", "Nom", "Prenom", "Telephone", "Date naissance",
            "Date resiliation", "Ancienne offre", "Ville", "Notes",
            "Statut", "Dernier appel", "Tentatives",
        ])
        for p in prospects:
            writer.writerow([
                p.id, p.last_name or "", p.first_name or "", p.phone,
                p.birth_date or "", p.resiliation_date or "", p.old_offer or "",
                p.city or "", (p.notes or "").replace("\n", " "),
                p.status_label, p.last_call_at.strftime("%d/%m/%Y %H:%M") if p.last_call_at else "",
                p.attempt_count,
            ])
        return out.getvalue()

    async def get_filtered(self, db: AsyncSession, search: str = None,
                           status: str = None, campaign_id: int = None,
                           agent_id: int = None, date_from: str = None,
                           date_to: str = None, limit: int = 50,
                           offset: int = 0) -> tuple[list[Prospect], int]:
        """Recherche filtree paginee. Retourne (prospects, total)."""
        q = select(Prospect).where(Prospect.is_archived == False)
        count_q = select(func.count(Prospect.id)).where(Prospect.is_archived == False)

        conditions = []
        if search:
            term = f"%{search}%"
            cond = or_(
                Prospect.first_name.ilike(term),
                Prospect.last_name.ilike(term),
                Prospect.phone.ilike(term),
                Prospect.old_offer.ilike(term),
            )
            conditions.append(cond)
        if status:
            conditions.append(Prospect.status == status)
        if campaign_id:
            conditions.append(Prospect.campaign_id == campaign_id)
        if agent_id:
            conditions.append(Prospect.agent_id == agent_id)

        for c in conditions:
            q = q.where(c)
            count_q = count_q.where(c)

        total = await db.scalar(count_q) or 0
        q = q.order_by(Prospect.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(q)
        return result.scalars().all(), total

    async def get_stats(self, db: AsyncSession, campaign_id: int = None) -> dict:
        base = select(func.count(Prospect.id)).where(Prospect.is_archived == False)
        if campaign_id:
            base = base.where(Prospect.campaign_id == campaign_id)

        async def cnt(status=None):
            qq = base
            if status:
                qq = qq.where(Prospect.status == status)
            return await db.scalar(qq) or 0

        return {
            "total":          await cnt(),
            "nouveau":        await cnt(ProspectStatus.NOUVEAU.value),
            "appele":         await cnt(ProspectStatus.APPELE.value),
            "interesse":      await cnt(ProspectStatus.INTERESSE.value),
            "pas_interesse":  await cnt(ProspectStatus.PAS_INTERESSE.value),
            "ne_repond_pas":  await cnt(ProspectStatus.NE_REPOND_PAS.value),
            "a_rappeler":     await cnt(ProspectStatus.A_RAPPELER.value),
            "transfere":      await cnt(ProspectStatus.TRANSFERE.value),
            "refus":          await cnt(ProspectStatus.REFUS_DEFINITIF.value),
            "do_not_call":    await cnt(ProspectStatus.DO_NOT_CALL.value),
        }


contact_service = ContactService()
