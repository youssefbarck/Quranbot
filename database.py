"""
طبقة قاعدة البيانات: إنشاء المحرك، الجلسات، التهيئة الآمنة.
"""
import logging
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)

from . import config
from .models import Base, UserSettings, MIGRATION_STATEMENTS
from . import config as cfg

logger = logging.getLogger(__name__)

# إزالة المعلمات غير المتوافقة مع asyncpg
_FORBIDDEN_PARAMS = {"sslmode", "channel_binding", "sslrootcert", "sslcert", "sslkey"}


def _strip_forbidden_params(url: str) -> str:
    if not url.startswith("postgresql://"):
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    for key in _FORBIDDEN_PARAMS:
        query.pop(key, None)
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


def _build_async_url() -> str:
    url = config.DATABASE_URL
    if not url:
        return "sqlite+aiosqlite:///:memory:"  # in-memory
    if url.startswith("postgresql://"):
        url = _strip_forbidden_params(url)
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("file:"):
        return url.replace("file:", "sqlite+aiosqlite:///", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


DB_ASYNC_URL = _build_async_url()

# محرك قاعدة البيانات
# ملاحظة: SQLite في الذاكرة لا يدعم pool_size — نستخدم StaticPool لإبقاء الاتصال واحدًا
_is_sqlite_mem = ":memory:" in DB_ASYNC_URL or DB_ASYNC_URL.endswith("sqlite+aiosqlite://")

if _is_sqlite_mem:
    from sqlalchemy.pool import StaticPool
    engine = create_async_engine(
        DB_ASYNC_URL,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        DB_ASYNC_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db():
    """إنشاء الجداول وتطبيق migrations الآمنة."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # تطبيق migrations (لإضافة الأعمدة الجديدة لقواعد قديمة)
        if config.is_postgres():
            for stmt in MIGRATION_STATEMENTS:
                try:
                    await conn.execute(__import__("sqlalchemy").text(stmt))
                except Exception as e:
                    logger.debug(f"migration skip: {e}")
    logger.info("✅ تم تهيئة قاعدة البيانات")


async def close_db():
    await engine.dispose()
    logger.info("✅ تم إغلاق قاعدة البيانات")


async def ensure_default_reminders(user_id: int):
    """تأكد من وجود 8 تذكيرات افتراضية لكل مستخدم."""
    from .models import User, UserSettings
    from sqlalchemy import select, delete
    from . import config as cfg

    async with AsyncSessionLocal() as session:
        # هل توجد تذكيرات أصلاً؟
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        existing = result.scalars().all()
        if existing:
            return  # تذكيرات موجودة بالفعل

        # إنشاء التذكيرات الافتراضية
        for reminder_type, default_time in cfg.DEFAULT_REMINDER_TIMES.items():
            session.add(UserSettings(
                user_id=user_id,
                reminder_type=reminder_type,
                reminder_time=default_time,
                enabled=True,
            ))
        await session.commit()
