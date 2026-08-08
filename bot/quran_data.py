"""
بيانات القرآن الكريم
====================
- 604 صفحة (مصحف المدينة المنورة)
- 30 جزء (كل جزء = 20 صفحة)
- 60 حزب (كل حزب = 10 صفحات)
- روابط الاستماع (mp3quran.net)
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SurahInfo:
    number: int
    name_ar: str
    name_en: str
    page_start: int
    ayah_count: int


SURAHS: list[SurahInfo] = [
    SurahInfo(1, "الفاتحة", "Al-Fatihah", 1, 7),
    SurahInfo(2, "البقرة", "Al-Baqarah", 2, 286),
    SurahInfo(3, "آل عمران", "Aal-Imran", 50, 200),
    SurahInfo(4, "النساء", "An-Nisa", 77, 176),
    SurahInfo(5, "المائدة", "Al-Maidah", 106, 120),
    SurahInfo(6, "الأنعام", "Al-Anam", 128, 165),
    SurahInfo(7, "الأعراف", "Al-Araf", 151, 206),
    SurahInfo(8, "الأنفال", "Al-Anfal", 177, 75),
    SurahInfo(9, "التوبة", "At-Tawbah", 187, 129),
    SurahInfo(10, "يونس", "Yunus", 208, 109),
    SurahInfo(11, "هود", "Hud", 221, 123),
    SurahInfo(12, "يوسف", "Yusuf", 235, 111),
    SurahInfo(13, "الرعد", "Ar-Rad", 249, 43),
    SurahInfo(14, "إبراهيم", "Ibrahim", 255, 52),
    SurahInfo(15, "الحجر", "Al-Hijr", 262, 99),
    SurahInfo(16, "النحل", "An-Nahl", 267, 128),
    SurahInfo(17, "الإسراء", "Al-Isra", 282, 111),
    SurahInfo(18, "الكهف", "Al-Kahf", 293, 110),
    SurahInfo(19, "مريم", "Maryam", 305, 98),
    SurahInfo(20, "طه", "Taha", 312, 135),
    SurahInfo(21, "الأنبياء", "Al-Anbiya", 322, 112),
    SurahInfo(22, "الحج", "Al-Hajj", 332, 78),
    SurahInfo(23, "المؤمنون", "Al-Muminun", 342, 118),
    SurahInfo(24, "النور", "An-Nur", 350, 64),
    SurahInfo(25, "الفرقان", "Al-Furqan", 359, 77),
    SurahInfo(26, "الشعراء", "Ash-Shuara", 367, 227),
    SurahInfo(27, "النمل", "An-Naml", 377, 93),
    SurahInfo(28, "القصص", "Al-Qasas", 385, 88),
    SurahInfo(29, "العنكبوت", "Al-Ankabut", 396, 69),
    SurahInfo(30, "الروم", "Ar-Rum", 404, 60),
    SurahInfo(31, "لقمان", "Luqman", 411, 34),
    SurahInfo(32, "السجدة", "As-Sajdah", 415, 30),
    SurahInfo(33, "الأحزاب", "Al-Ahzab", 418, 73),
    SurahInfo(34, "سبأ", "Saba", 428, 54),
    SurahInfo(35, "فاطر", "Fatir", 434, 45),
    SurahInfo(36, "يس", "Ya-Sin", 440, 83),
    SurahInfo(37, "الصافات", "As-Saffat", 446, 182),
    SurahInfo(38, "ص", "Sad", 453, 88),
    SurahInfo(39, "الزمر", "Az-Zumar", 458, 75),
    SurahInfo(40, "غافر", "Ghafir", 467, 85),
    SurahInfo(41, "فصلت", "Fussilat", 477, 54),
    SurahInfo(42, "الشورى", "Ash-Shura", 483, 53),
    SurahInfo(43, "الزخرف", "Az-Zukhruf", 489, 89),
    SurahInfo(44, "الدخان", "Ad-Dukhan", 496, 59),
    SurahInfo(45, "الجاثية", "Al-Jathiyah", 499, 37),
    SurahInfo(46, "الأحقاف", "Al-Ahqaf", 502, 35),
    SurahInfo(47, "محمد", "Muhammad", 507, 38),
    SurahInfo(48, "الفتح", "Al-Fath", 511, 29),
    SurahInfo(49, "الحجرات", "Al-Hujurat", 515, 18),
    SurahInfo(50, "ق", "Qaf", 518, 45),
    SurahInfo(51, "الذاريات", "Adh-Dhariyat", 520, 60),
    SurahInfo(52, "الطور", "At-Tur", 523, 49),
    SurahInfo(53, "النجم", "An-Najm", 526, 62),
    SurahInfo(54, "القمر", "Al-Qamar", 528, 55),
    SurahInfo(55, "الرحمن", "Ar-Rahman", 531, 78),
    SurahInfo(56, "الواقعة", "Al-Waqiah", 534, 96),
    SurahInfo(57, "الحديد", "Al-Hadid", 537, 29),
    SurahInfo(58, "المجادلة", "Al-Mujadila", 542, 22),
    SurahInfo(59, "الحشر", "Al-Hashr", 545, 24),
    SurahInfo(60, "الممتحنة", "Al-Mumtahanah", 549, 13),
    SurahInfo(61, "الصف", "As-Saff", 551, 14),
    SurahInfo(62, "الجمعة", "Al-Jumuah", 553, 11),
    SurahInfo(63, "المنافقون", "Al-Munafiqun", 554, 11),
    SurahInfo(64, "التغابن", "At-Taghabun", 556, 18),
    SurahInfo(65, "الطلاق", "At-Talaq", 558, 12),
    SurahInfo(66, "التحريم", "At-Tahrim", 560, 12),
    SurahInfo(67, "الملك", "Al-Mulk", 562, 30),
    SurahInfo(68, "القلم", "Al-Qalam", 564, 52),
    SurahInfo(69, "الحاقة", "Al-Haqqah", 566, 52),
    SurahInfo(70, "المعارج", "Al-Maarij", 568, 44),
    SurahInfo(71, "نوح", "Nuh", 570, 28),
    SurahInfo(72, "الجن", "Al-Jinn", 572, 28),
    SurahInfo(73, "المزمل", "Al-Muzzammil", 574, 20),
    SurahInfo(74, "المدثر", "Al-Muddaththir", 575, 56),
    SurahInfo(75, "القيامة", "Al-Qiyamah", 577, 40),
    SurahInfo(76, "الإنسان", "Al-Insan", 578, 31),
    SurahInfo(77, "المرسلات", "Al-Mursalat", 580, 50),
    SurahInfo(78, "النبأ", "An-Naba", 582, 40),
    SurahInfo(79, "النازعات", "An-Naziat", 583, 46),
    SurahInfo(80, "عبس", "Abasa", 585, 42),
    SurahInfo(81, "التكوير", "At-Takwir", 586, 29),
    SurahInfo(82, "الانفطار", "Al-Infitar", 587, 19),
    SurahInfo(83, "المطففين", "Al-Mutaffifin", 587, 36),
    SurahInfo(84, "الانشقاق", "Al-Inshiqaq", 589, 25),
    SurahInfo(85, "البروج", "Al-Buruj", 590, 22),
    SurahInfo(86, "الطارق", "At-Tariq", 591, 17),
    SurahInfo(87, "الأعلى", "Al-Ala", 591, 19),
    SurahInfo(88, "الغاشية", "Al-Ghashiyah", 592, 26),
    SurahInfo(89, "الفجر", "Al-Fajr", 593, 30),
    SurahInfo(90, "البلد", "Al-Balad", 594, 20),
    SurahInfo(91, "الشمس", "Ash-Shams", 595, 15),
    SurahInfo(92, "الليل", "Al-Layl", 595, 21),
    SurahInfo(93, "الضحى", "Ad-Duha", 596, 11),
    SurahInfo(94, "الشرح", "Ash-Sharh", 596, 8),
    SurahInfo(95, "التين", "At-Tin", 597, 8),
    SurahInfo(96, "العلق", "Al-Alaq", 597, 19),
    SurahInfo(97, "القدر", "Al-Qadr", 598, 5),
    SurahInfo(98, "البينة", "Al-Bayyinah", 598, 8),
    SurahInfo(99, "الزلزلة", "Az-Zalzalah", 599, 8),
    SurahInfo(100, "العاديات", "Al-Adiyat", 599, 11),
    SurahInfo(101, "القارعة", "Al-Qariah", 600, 11),
    SurahInfo(102, "التكاثر", "At-Takathur", 600, 8),
    SurahInfo(103, "العصر", "Al-Asr", 601, 3),
    SurahInfo(104, "الهمزة", "Al-Humazah", 601, 9),
    SurahInfo(105, "الفيل", "Al-Fil", 601, 5),
    SurahInfo(106, "قريش", "Quraysh", 602, 4),
    SurahInfo(107, "الماعون", "Al-Maun", 602, 7),
    SurahInfo(108, "الكوثر", "Al-Kawthar", 602, 3),
    SurahInfo(109, "الكافرون", "Al-Kafirun", 603, 6),
    SurahInfo(110, "النصر", "An-Nasr", 603, 3),
    SurahInfo(111, "المسد", "Al-Masad", 603, 5),
    SurahInfo(112, "الإخلاص", "Al-Ikhlas", 604, 4),
    SurahInfo(113, "الفلق", "Al-Falaq", 604, 5),
    SurahInfo(114, "الناس", "An-Nas", 604, 6),
]

TOTAL_PAGES = 604
TOTAL_JUZ = 30
TOTAL_HIZB = 60


def page_to_juz(page: int) -> int:
    if page < 1:
        return 1
    if page >= TOTAL_PAGES:
        return TOTAL_JUZ
    return ((page - 1) // 20) + 1


def page_to_hizb(page: int) -> int:
    if page < 1:
        return 1
    if page >= TOTAL_PAGES:
        return TOTAL_HIZB
    return ((page - 1) // 10) + 1


def juz_pages(juz: int) -> tuple[int, int]:
    juz = max(1, min(juz, TOTAL_JUZ))
    start = (juz - 1) * 20 + 1
    end = start + 19
    if juz == TOTAL_JUZ:
        end = TOTAL_PAGES
    return start, end


def hizb_pages(hizb: int) -> tuple[int, int]:
    hizb = max(1, min(hizb, TOTAL_HIZB))
    start = (hizb - 1) * 10 + 1
    end = start + 9
    if hizb == TOTAL_HIZB:
        end = TOTAL_PAGES
    return start, end


def page_to_surah(page: int) -> SurahInfo | None:
    if page < 1 or page > TOTAL_PAGES:
        return None
    result = SURAHS[0]
    for s in SURAHS:
        if s.page_start <= page:
            result = s
        else:
            break
    return result


def get_surah_by_name(name: str) -> SurahInfo | None:
    """بحث بالاسم العربي (مطابق جزئي)"""
    name = name.strip()
    for s in SURAHS:
        if s.name_ar == name or name in s.name_ar or s.name_ar in name:
            return s
    return None


def get_surah_by_number(num: int) -> SurahInfo | None:
    for s in SURAHS:
        if s.number == num:
            return s
    return None


# ====== روابط الاستماع ======
RECITERS = {
    "الحصري": "https://server8.mp3quran.net/afs/",
    "العجمي": "https://server7.mp3quran.net/afs/",
    "المعيقلي": "https://server11.mp3quran.net/maher/",
    "عبد الباسط": "https://server7.mp3quran.net/basit/",
    "السديس": "https://server13.mp3quran.net/sds/",
    "الحذيفي": "https://server7.mp3quran.net/hthfi/",
}


def get_surah_audio_url(surah_number: int, reciter: str = "الحصري") -> str | None:
    base = RECITERS.get(reciter, RECITERS["الحصري"])
    return f"{base}{surah_number:03d}.mp3"


def get_page_audio_url(page: int) -> str | None:
    surah = page_to_surah(page)
    if surah:
        return get_surah_audio_url(surah.number)
    return None


def get_quran_text_url(page: int) -> str:
    return f"https://quran.com/page/{page}"
