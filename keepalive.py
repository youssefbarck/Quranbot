"""
خادم Keep-alive بسيط — يبقي Render مستيقظًا.
"""
import asyncio
import logging
import os
from aiohttp import web

logger = logging.getLogger(__name__)


async def _health(request):
    return web.Response(text="OK — Quran Fortresses Bot is running ✅")


async def start_keepalive_server(port: int):
    """يبدأ خادم HTTP بسيط على المنفذ المحدد."""
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 خادم keep-alive يعمل على المنفذ {port}")
    return runner


async def start_self_ping(interval: int = 280):
    """ينشئ ping دوري لنفسه عبر RENDER_EXTERNAL_URL."""
    import aiohttp
    public_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not public_url:
        logger.warning("⚠️ RENDER_EXTERNAL_URL غير مضبوط — لن يعمل self-ping")
        return None

    async def _ping_loop():
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(f"{public_url}/health", timeout=10) as resp:
                        if resp.status == 200:
                            logger.debug("🔄 self-ping OK")
                        else:
                            logger.warning(f"⚠️ self-ping status={resp.status}")
                except Exception as e:
                    logger.warning(f"⚠️ self-ping فشل: {e}")
                await asyncio.sleep(interval)

    task = asyncio.create_task(_ping_loop())
    return task
