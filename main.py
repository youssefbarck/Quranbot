"""
نقطة الدخول الرئيسية للبوت.
"""
import asyncio
import logging
import sys
import os

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)

from . import config
from .database import init_db, close_db
from .handlers.commands import (
    start_command, today_command, progress_command, fortresses_command,
    settings_command, activity_command, suggestions_command,
    update_command, settime_command, setamount_command,
    notifications_command, help_command,
)
from .handlers.free_text import handle_free_text
from .handlers.callback_router import button_callback
from .handlers.error_handler import error_handler
from .scheduler.reminders import (
    start_scheduler, shutdown_scheduler, schedule_all_users_jobs
)
from .keepalive import start_keepalive_server, start_self_ping

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app):
    """يُستدعى بعد بناء التطبيق وقبل بدء التحديثات."""
    await init_db()
    await start_scheduler()
    await schedule_all_users_jobs(app.bot)

    if config.KEEPALIVE_ENABLED:
        try:
            runner = await start_keepalive_server(config.PORT)
            app._keepalive_runner = runner
            app._keepalive_task = await start_self_ping(config.KEEPALIVE_INTERVAL)
            logger.info("✅ keep-alive نشط")
        except Exception as e:
            logger.warning(f"⚠️ تعذّر بدء keep-alive: {e}")


async def post_shutdown(app):
    """يُستدعى عند إيقاف التطبيق."""
    task = getattr(app, "_keepalive_task", None)
    runner = getattr(app, "_keepalive_runner", None)
    if task:
        task.cancel()
        try: await task
        except (asyncio.CancelledError, Exception): pass
    if runner:
        await runner.cleanup()
    await shutdown_scheduler()
    await close_db()


def build_application():
    """يبني تطبيق Telegram."""
    if not config.BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN غير مضبوط")
        sys.exit(1)

    app = (
        ApplicationBuilder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .read_timeout(15)
        .write_timeout(15)
        .connect_timeout(10)
        .pool_timeout(10)
        .build()
    )

    # أوامر نصية
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("fortresses", fortresses_command))
    app.add_handler(CommandHandler("progress", progress_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("activity", activity_command))
    app.add_handler(CommandHandler("suggestions", suggestions_command))
    app.add_handler(CommandHandler("update", update_command))
    app.add_handler(CommandHandler("settime", settime_command))
    app.add_handler(CommandHandler("setamount", setamount_command))
    app.add_handler(CommandHandler("notifications", notifications_command))

    # نص حر
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))

    # أزرار inline
    app.add_handler(CallbackQueryHandler(button_callback))

    # معالج الأخطاء
    app.add_error_handler(error_handler)

    return app


def main():
    """نقطة الدخول."""
    try:
        logger.info("📖 بوت الحصون الخمسة — الإصدار 4.0.0 — البدء")
        logger.info(f"  - المنطقة الزمنية: {config.DEFAULT_TIMEZONE}")
        logger.info(f"  - قاعدة البيانات: {config.DATABASE_URL[:50] if config.DATABASE_URL else 'in-memory'}...")
        logger.info(f"  - PostgreSQL: {config.is_postgres()}")
        logger.info(f"  - BOT_TOKEN مضبوط: {bool(config.BOT_TOKEN)}")
        logger.info(f"  - keep-alive: {'مُفعّل' if config.KEEPALIVE_ENABLED else 'مُعطّل'}")

        app = build_application()
        logger.info("🚀 تشغيل البوت في وضع polling...")
        app.run_polling(poll_interval=1, drop_pending_updates=True, close_loop=False)
    except Exception as e:
        logger.error("❌ خطأ أثناء التشغيل:")
        logger.error(traceback.format_exc() if 'traceback' in dir() else str(e))
        print("❌ ERROR:", e, flush=True)
        sys.stdout.flush(); sys.stderr.flush()
        raise


if __name__ == "__main__":
    import traceback
    main()
