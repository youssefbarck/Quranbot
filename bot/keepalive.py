"""
keep-alive مدمج — يبقي خدمة Render Free مستيقظة دون منصة خارجية.

المكونات:
1) خادم HTTP بسيط على بورت Render (PORT) يقدم endpoint /health
2) مهمة async تصنع self-ping على الـ URL العام (RENDER_EXTERNAL_URL/health)
   كل 280 ثانية — أي أقل من عتبة نوم Render (15 دقيقة).
   هذا الطلب يأتي من الإنترنت لذا يعتبره Render نشاطاً خارجياً.

لا حاجة لـ UptimeRobot أو أي خدمة خارجية — كل شيء ذاتي.

طريقة الاستخدام:
    from .keepalive import start_keepalive_server
    server = await start_keepalive_server(port=10000)
"""
import asyncio
import logging
from datetime import datetime

from aiohttp import web

logger = logging.getLogger(__name__)


async def _health_handler(request: web.Request) -> web.Response:
    """يرد بحالة الخدمة — يستخدمه self-ping و Render للفحص الصحي"""
    return web.json_response({
        "status": "ok",
        "service": "quran-husun-bot",
        "timestamp": datetime.utcnow().isoformat(),
    })


async def _root_handler(request: web.Request) -> web.Response:
    """رد بسيط على جذر الموقع"""
    return web.Response(text="Quran Husun Bot is running ✅")


async def _do_ping(url: str, timeout_sec: float = 15.0) -> bool:
    """ينفّذ طلب GET واحد إلى URL المراقبة"""
    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                return resp.status == 200
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"keep-alive: فشل الـ ping إلى {url}: {e}")
        return False


async def keepalive_loop(url: str, interval: int = 280, startup_delay: int = 15):
    """
    حلقة keep-alive: تصنع ping كل `interval` ثانية.

    - `url`: الـ URL الكامل للـ health endpoint على Render (مثل https://<service>.onrender.com/health)
    - `interval`: 280 ثانية افتراضياً (أقل من عتبة نوم Render)
    - `startup_delay`: 15 ثانية انتظار قبل أول ping (لإعطاء الخادم وقتاً للإقلاع)
    """
    if not url:
        logger.warning("keep-alive: URL غير مضبوط — المهمة لن تعمل")
        return

    logger.info(f"keep-alive: بدء المهمة — ping كل {interval} ثانية إلى {url}")
    await asyncio.sleep(startup_delay)

    success_count = 0
    fail_count = 0

    while True:
        try:
            ok = await _do_ping(url)
            if ok:
                success_count += 1
                # تسجيل كل 10 نجاحات (≈ 47 دقيقة) لتفادي امتلاء السجلات
                if success_count % 10 == 0:
                    logger.info(f"keep-alive: {success_count} نجاح، {fail_count} فشل")
            else:
                fail_count += 1
                logger.warning(f"keep-alive: فشل (HTTP غير 200)")
        except asyncio.CancelledError:
            logger.info("keep-alive: إيقاف المهمة")
            break
        except Exception as e:
            fail_count += 1
            logger.warning(f"keep-alive: استثناء غير متوقع: {e}")
        await asyncio.sleep(interval)


async def start_keepalive_server(port: int, public_health_url: str = "",
                                keepalive_interval: int = 280) -> tuple:
    """
    يبدأ خادم HTTP للـ health + مهمة self-ping.

    الإرجاع:
        (web_runner, keepalive_task)
    """
    app = web.Application()
    app.router.add_get("/", _root_handler)
    app.router.add_get("/health", _health_handler)
    app.router.add_get("/ping", _health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"keep-alive: خادم HTTP يستمع على المنفذ {port}")

    keepalive_task = None
    if public_health_url:
        keepalive_task = asyncio.create_task(
            keepalive_loop(url=public_health_url, interval=keepalive_interval)
        )
    else:
        logger.warning("keep-alive: لا يوجد URL عام — لن تعمل مهمة self-ping "
                       "(الخادم يعمل لكن الخدمة قد تنام بعد 15 دقيقة)")

    return runner, keepalive_task
