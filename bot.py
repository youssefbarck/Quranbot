"""
بوت الحصون الخمسة — ملف موحد (كل الأوامر والمنطق في ملف واحد)
================================================================
نسخة 5.0.0 — مع تحسين لوحات المفاتيح لتكون أوضح للمستخدم العادي

المنهجية:
    الحصن 1: التهيئة (قراءة 2 حزب/يوم + استماع 1 حزب/يوم)
    الحصن 2: التحضير (أسبوعي + ليلي + قبلي 15 دقيقة)
    الحصن 3: الحفظ الجديد
    الحصن 4: مراجعة القريب (آخر 20 وجه)
    الحصن 5: مراجعة البعيد (40 وجه/دورة)

التحسينات في هذه النسخة:
    - أزرار أكبر وأوضح مع تسميات كاملة
    - فاصل مرئي بين كل حصن في لوحة الأزرار
    - إرشادات مختصرة تشرح ما يحدث عند الضغط
    - أرقام الأحزاب تظهر دائمًا (المستخدم يرى التغيّر يوميًا)
"""

import os
import re
import sys
import html
import asyncio
import logging
import traceback
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from collections import Counter
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, String, Boolean, Text, Float,
    func, UniqueConstraint, select, text as sa_text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from telegram.error import Conflict, NetworkError, TimedOut, Forbidden, BadRequest

# ═══════════════════════════════════════════════════════════════════════════════
# الجزء الأول: الإعدادات والثوابت
# ═══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip().replace("postgres://", "postgresql://")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0") or "0")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Africa/Algiers")
PORT = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
KEEPALIVE_ENABLED = os.getenv("KEEPALIVE_ENABLED", "true").lower() == "true"
KEEPALIVE_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "280"))

QURAN_PAGE_COUNT = 604
QURAN_HIZB_COUNT = 60
QURAN_JUZ_COUNT = 30
DAILY_READING_HIZB = 2
DAILY_READING_PAGES = 20
READING_CYCLE_DAYS = 30
DAILY_LISTENING_HIZB = 1
DAILY_LISTENING_PAGES = 10
LISTENING_CYCLE_DAYS = 60
NEAR_REVISION_SIZE = 20
FAR_REVISION_SIZE = 40
PRE_SESSION_MINUTES = 15
DEFAULT_DAILY_HIFZ_AMOUNT = 1
DEFAULT_WEEKLY_HIFZ_AMOUNT = 7

DEFAULT_REMINDER_TIMES = {
    "memorize": "06:00", "reading": "08:00", "weekly_prep": "09:00",
    "pre_session": "10:00", "listening": "13:00", "near_review": "16:00",
    "far_review": "20:00", "nightly_prep": "21:00",
}
REMINDER_TYPES = list(DEFAULT_REMINDER_TIMES.keys())
REMINDER_LABELS_AR = {
    "memorize": "\U0001f4da \u0627\u0644\u062d\u0641\u0638", "reading": "\U0001f4d6 \u0627\u0644\u0642\u0631\u0627\u0621\u0629",
    "weekly_prep": "\U0001f4c5 \u0627\u0644\u062a\u062d\u0636\u064a\u0631 \u0627\u0644\u0623\u0633\u0628\u0648\u0639\u064a",
    "pre_session": "\u23f1\ufe0f \u0627\u0644\u062a\u062d\u0636\u064a\u0631 \u0627\u0644\u0642\u0628\u0644\u064a",
    "listening": "\U0001f3a7 \u0627\u0644\u0627\u0633\u062a\u0645\u0627\u0639",
    "near_review": "\U0001f504 \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u0642\u0631\u064a\u0628",
    "far_review": "\U0001f501 \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u0628\u0639\u064a\u062f",
    "nightly_prep": "\U0001f319 \u0627\u0644\u062a\u062d\u0636\u064a\u0631 \u0627\u0644\u0644\u064a\u0644\u064a",
}

REMINDER_MESSAGES = {
    "memorize": "\U0001f195 <b>\u062a\u0630\u0643\u064a\u0631 \u0627\u0644\u062d\u0641\u0638</b>\n\n\u062d\u0627\u0646 \u0648\u0642\u062a \u0627\u0644\u062d\u0641\u0638 \u0627\u0644\u064a\u0648\u0645\u064a. \u0627\u0628\u062f\u0623 \u0628\u0628\u0633\u0645 \u0627\u0644\u0644\u0647 \U0001f91c",
    "reading": "\U0001f4d6 <b>\u062a\u0630\u0643\u064a\u0631 \u0627\u0644\u0642\u0631\u0627\u0621\u0629</b>\n\n\u0648\u0642\u062a \u0648\u0631\u062f \u0627\u0644\u0642\u0631\u0627\u0621\u0629 \u0627\u0644\u064a\u0648\u0645\u064a. \u062d\u0632\u0628\u0627\u0646 \u0641\u0642\u0637!",
    "weekly_prep": "\U0001f4da <b>\u062a\u0630\u0643\u064a\u0631 \u0627\u0644\u062a\u062d\u0636\u064a\u0631 \u0627\u0644\u0623\u0633\u0628\u0648\u0639\u064a</b>\n\n\u0627\u0642\u0631\u0623 \u0623\u0648\u062c\u0647 \u0627\u0644\u0623\u0633\u0628\u0648\u0639 \u0627\u0644\u0642\u0627\u062f\u0645 \u0642\u0628\u0644 \u0628\u062f\u0621 \u062d\u0641\u0638\u0647\u0627.",
    "pre_session": "\u23f1\ufe0f <b>\u062a\u0630\u0643\u064a\u0631 \u0627\u0644\u062a\u062d\u0636\u064a\u0631 \u0627\u0644\u0642\u0628\u0644\u064a</b>\n\n\u0627\u0642\u0631\u0623 \u0627\u0644\u0648\u062c\u0647 \u0627\u0644\u0645\u0637\u0644\u0648\u0628 15 \u062f\u0642\u064a\u0642\u0629 \u0642\u0628\u0644 \u0627\u0644\u062d\u0641\u0638.",
    "listening": "\U0001f3a7 <b>\u062a\u0630\u0643\u064a\u0631 \u0627\u0644\u0627\u0633\u062a\u0645\u0627\u0639</b>\n\n\u0648\u0642\u062a \u0627\u0644\u0627\u0633\u062a\u0645\u0627\u0639 \u0644\u062d\u0632\u0628 \u0627\u0644\u064a\u0648\u0645.",
    "near_review": "\U0001f504 <b>\u062a\u0630\u0643\u064a\u0631 \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u0642\u0631\u064a\u0628</b>\n\n\u0631\u0627\u062c\u0639 \u0622\u062e\u0631 20 \u0648\u062c\u0647 \u0645\u062d\u0641\u0648\u0638 \u0627\u0644\u064a\u0648\u0645.",
    "far_review": "\U0001f501 <b>\u062a\u0630\u0643\u064a\u0631 \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u0628\u0639\u064a\u062f</b>\n\n\u062d\u0627\u0646 \u0648\u0642\u062a \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u062f\u0648\u0631\u0629 \u0627\u0644\u062d\u0627\u0644\u064a\u0629 (40 \u0648\u062c\u0647).",
    "nightly_prep": "\U0001f319 <b>\u062a\u0630\u0643\u064a\u0631 \u0627\u0644\u062a\u062d\u0636\u064a\u0631 \u0627\u0644\u0644\u064a\u0644\u064a</b>\n\n\u0642\u0628\u0644 \u0627\u0644\u0646\u0648\u0645\u060c \u0627\u0642\u0631\u0623 \u0648\u062c\u0647 \u0627\u0644\u063a\u062f \u0627\u0633\u062a\u0639\u062f\u0627\u062f\u0627\u064b \u0644\u0647.",
}

TASK_FIELD_MAP = {
    "reading": "reading_done", "listening": "listening_done",
    "weekly_prep": "weekly_prep_done", "nightly_prep": "nightly_prep_done",
    "pre_session_prep": "pre_session_prep_done", "memorize": "memorize_done",
    "near_review": "near_review_done", "far_review": "far_review_done",
}


def get_db_url_async() -> str:
    if not DATABASE_URL:
        return "sqlite+aiosqlite://"
    if DATABASE_URL.startswith("postgresql://"):
        return DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    if DATABASE_URL.startswith("file:"):
        return DATABASE_URL.replace("file:", "sqlite+aiosqlite:///", 1)
    if DATABASE_URL.startswith("sqlite://"):
        return DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return DATABASE_URL


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql://")


logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
