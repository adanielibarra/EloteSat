"""Settings of FenoSat (former name) are copied to EloteSat once.

    QT_QPA_PLATFORM=offscreen python elotesat/tests/test_migrate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication, QgsSettings  # noqa: E402

app = QgsApplication([], True)
app.initQgis()
from elotesat.core.migrate import migrate_settings  # noqa: E402

FAIL = []


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        FAIL.append(m)


s = QgsSettings()
s.remove("EloteSat")
s.remove("FenoSat")
s.setValue("FenoSat/profile", "norte_riego")
s.setValue("FenoSat/lang", "en")
check(migrate_settings() == 2, "two FenoSat keys copied")
check(s.value("EloteSat/profile") == "norte_riego" and
      s.value("EloteSat/lang") == "en", "values carried over")
s.setValue("FenoSat/lang", "es")
check(migrate_settings() == 0 and s.value("EloteSat/lang") == "en",
      "only once: EloteSat settings are never overwritten")
s.remove("EloteSat")
s.remove("FenoSat")
print("\n%d failures" % len(FAIL))
app.exitQgis()
sys.exit(1 if FAIL else 0)
