"""
NexCall AI v3 — Service Blacklist (Do Not Call)
"""
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.blacklist import Blacklist

logger = logging.getLogger(__name__)


class BlacklistService:

    def normalize_phone(self, phone: str) -> str:
        p = "".join(c for c in (phone or "") if c.isdigit() or c == "+")
        if p.startswith("0") and len(p) == 10:
            p = "+33" + p[1:]
        elif p.startswith("33") and not p.startswith("+"):
            p = "+" + p
        return p

    async def is_blacklisted(self, db: AsyncSession, phone: str) -> bool:
        norm = self.normalize_phone(phone)
        result = await db.execute(select(Blacklist).where(Blacklist.phone == norm))
        return result.scalar_one_or_none() is not None

    async def get_all_phones(self, db: AsyncSession) -> set[str]:
        """Retourne tous les numeros blacklistes (pour verification batch a l'import)."""
        result = await db.execute(select(Blacklist.phone))
        return {row[0] for row in result.all()}

    async def add(self, db: AsyncSession, phone: str, reason: str = None,
                  source: str = "manual", notes: str = None) -> Optional[Blacklist]:
        norm = self.normalize_phone(phone)
        if not norm:
            return None
        # Eviter doublon
        existing = await db.execute(select(Blacklist).where(Blacklist.phone == norm))
        if existing.scalar_one_or_none():
            return None
        entry = Blacklist(phone=norm, reason=reason, source=source, notes=notes)
        db.add(entry)
        await db.flush()
        logger.info(f"[blacklist] Ajout {norm} (raison: {reason})")
        return entry

    async def remove(self, db: AsyncSession, phone: str) -> bool:
        norm = self.normalize_phone(phone)
        result = await db.execute(select(Blacklist).where(Blacklist.phone == norm))
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        await db.delete(entry)
        return True

    async def get_all(self, db: AsyncSession, limit: int = 200, offset: int = 0) -> list[Blacklist]:
        result = await db.execute(
            select(Blacklist).order_by(Blacklist.created_at.desc()).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def count(self, db: AsyncSession) -> int:
        return await db.scalar(select(func.count(Blacklist.id))) or 0


blacklist_service = BlacklistService()
