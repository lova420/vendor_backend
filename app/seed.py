"""Idempotent seed script.

Creates the default super admin if it does not already exist.
Safe to run repeatedly.

Usage (from backend/):
    python -m app.seed
"""
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models.user import User, UserType


async def seed_super_admin(db: AsyncSession) -> None:
    email = settings.DEFAULT_SUPERADMIN_EMAIL.lower()

    existing = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if existing is not None:
        if existing.is_deleted:
            existing.is_deleted = False
        if existing.user_type != UserType.SUPER_ADMIN.value:
            print(
                f"[seed] WARNING: user {email} exists but is not a super_admin "
                f"(user_type={existing.user_type}). Leaving as-is.",
                file=sys.stderr,
            )
        await db.commit()
        print(f"[seed] super admin already present: {email}")
        return

    user = User(
        email=email,
        password=hash_password(settings.DEFAULT_SUPERADMIN_PASSWORD),
        user_type=UserType.SUPER_ADMIN.value,
    )
    db.add(user)
    await db.commit()
    print(f"[seed] created super admin: {email}")


async def main() -> None:
    async with SessionLocal() as db:
        await seed_super_admin(db)


if __name__ == "__main__":
    asyncio.run(main())
