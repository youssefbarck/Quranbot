"""
اتصال قاعدة البيانات — SQLAlchemy 2.0 async مع Neon Postgres
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import config


class Base(DeclarativeBase):
    pass


def _to_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# إنشاء المحرك (pool pre_ping يتفادى انقطاع اتصال Neon)
# SQLite (للاختبارات) لا يدعم pool_size/max_overflow
_engine_kwargs = {"echo": False, "pool_pre_ping": True}
if not config.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

engine = create_async_engine(
    _to_async_url(config.DATABASE_URL),
    **_engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """ينشئ الجداول إذا لم تكن موجودة"""
    from . import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
