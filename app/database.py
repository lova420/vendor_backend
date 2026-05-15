from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


def _verify_ca_cert() -> str:
    """Fail-fast: refuse to start without a readable CA pem on disk."""
    ca_path = settings.db_ca_cert_absolute_path
    if not ca_path.is_file():
        raise RuntimeError(
            f"DB CA certificate not found at {ca_path}. "
            "Set DB_CA_CERT_PATH to a valid .pem file."
        )
    return str(ca_path)


def _build_connect_args() -> dict[str, Any]:
    """libpq-style SSL params consumed by psycopg."""
    return {
        "sslmode": settings.DB_SSL_MODE,
        "sslrootcert": _verify_ca_cert(),
    }


def _build_dsn() -> str:
    return (
        f"postgresql+psycopg://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )


engine = create_async_engine(
    _build_dsn(),
    echo=False,
    pool_pre_ping=True,
    connect_args=_build_connect_args(),
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
