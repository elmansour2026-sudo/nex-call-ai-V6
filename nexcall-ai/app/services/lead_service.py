"""
NexCall AI — Service Lead
Logique métier pour la qualification et la gestion des leads
"""
import logging
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.lead import Lead, LeadStatus
from app.config import settings

logger = logging.getLogger(__name__)


class LeadService:

    async def upsert_from_call(
        self,
        db: AsyncSession,
        phone: str,
        ai_data: dict[str, Any],
        source: str = "inbound_call",
    ) -> Lead:
        """
        Crée ou met à jour un lead depuis les données extraites par l'IA.
        Fusionne intelligemment les nouvelles données avec les existantes.
        """
        lead = await self.get_by_phone(db, phone)

        score = float(ai_data.get("score") or 0)

        if lead:
            # Mise à jour — on ne remplace que les champs non-null
            fields_to_update = {
                "first_name": ai_data.get("first_name"),
                "last_name":  ai_data.get("last_name"),
                "email":      ai_data.get("email"),
                "interest":   ai_data.get("interest"),
                "budget":     ai_data.get("budget"),
                "urgency":    ai_data.get("urgency"),
            }
            for field, value in fields_to_update.items():
                if value:
                    setattr(lead, field, value)

            # Le score monte mais ne descend pas pendant un appel
            if score > lead.score:
                lead.score = score

            if ai_data.get("notes"):
                existing_notes = lead.notes or ""
                lead.notes = f"{existing_notes}\n[{datetime.utcnow().strftime('%d/%m %H:%M')}] {ai_data['notes']}".strip()

            lead.recalculate_status()
            lead.updated_at = datetime.utcnow()
        else:
            notes = ai_data.get("notes", "")
            if notes:
                notes = f"[{datetime.utcnow().strftime('%d/%m %H:%M')}] {notes}"

            lead = Lead(
                phone      = phone,
                first_name = ai_data.get("first_name"),
                last_name  = ai_data.get("last_name"),
                email      = ai_data.get("email"),
                interest   = ai_data.get("interest"),
                score      = score,
                budget     = ai_data.get("budget"),
                urgency    = ai_data.get("urgency"),
                notes      = notes,
                source     = source,
            )
            lead.recalculate_status()
            db.add(lead)

        await db.flush()
        return lead

    async def get_by_phone(self, db: AsyncSession, phone: str) -> Optional[Lead]:
        result = await db.execute(select(Lead).where(Lead.phone == phone))
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, lead_id: int) -> Optional[Lead]:
        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()

    async def get_all(
        self,
        db: AsyncSession,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        interest: Optional[str] = None,
    ) -> list[Lead]:
        q = select(Lead).where(Lead.is_archived == False)
        if status:
            q = q.where(Lead.status == status)
        if interest:
            q = q.where(Lead.interest == interest)
        q = q.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(q)
        return result.scalars().all()

    async def get_stats(self, db: AsyncSession) -> dict[str, Any]:
        total = await db.scalar(select(func.count(Lead.id)).where(Lead.is_archived == False))
        hot   = await db.scalar(select(func.count(Lead.id)).where(Lead.status == LeadStatus.HOT.value, Lead.is_archived == False))
        warm  = await db.scalar(select(func.count(Lead.id)).where(Lead.status == LeadStatus.WARM.value, Lead.is_archived == False))
        qual  = await db.scalar(select(func.count(Lead.id)).where(Lead.status == LeadStatus.QUALIFIED.value, Lead.is_archived == False))
        cold  = await db.scalar(select(func.count(Lead.id)).where(Lead.status == LeadStatus.COLD.value, Lead.is_archived == False))
        avg   = await db.scalar(select(func.avg(Lead.score)).where(Lead.is_archived == False))
        return {
            "total":     total or 0,
            "hot":       hot or 0,
            "warm":      warm or 0,
            "qualified": qual or 0,
            "cold":      cold or 0,
            "avg_score": round(avg or 0, 1),
        }

    async def delete(self, db: AsyncSession, lead_id: int) -> bool:
        lead = await self.get_by_id(db, lead_id)
        if not lead:
            return False
        await db.delete(lead)
        return True


# Singleton
lead_service = LeadService()
