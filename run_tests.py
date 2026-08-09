#!/usr/bin/env python3
"""سكربت اختبار شامل."""
import os
import sys

# فرض SQLite في الذاكرة للاختبارات
os.environ.pop("DATABASE_URL", None)
os.environ["DATABASE_URL"] = ""

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__":
    from tests.test_engines import run_all_tests
    success = run_all_tests()
    sys.exit(0 if success else 1)
