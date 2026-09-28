"""EloteSat Tamaulipas was called FenoSat up to 0.4.0. Settings (calendar
profiles, language, folders) and SIAP downloads of FenoSat are reused."""

OLD, NEW = "FenoSat", "EloteSat"


def migrate_settings():
    """Copy FenoSat/* settings to EloteSat/* once (only if EloteSat has
    none yet). The old keys are left in place. Returns keys copied."""
    try:
        from qgis.core import QgsSettings
    except Exception:
        return 0
    s = QgsSettings()
    s.beginGroup(NEW)
    have = s.allKeys()
    s.endGroup()
    if have:
        return 0
    s.beginGroup(OLD)
    old = {k: s.value(k) for k in s.allKeys()}
    s.endGroup()
    for k, v in old.items():
        s.setValue("%s/%s" % (NEW, k), v)
    return len(old)
