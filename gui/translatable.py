"""Mixin that remembers which widget texts come from which i18n key, so the
whole window can switch language without being rebuilt."""

from ..core.i18n import tr


class Translatable:
    def _t(self, setter, key, *args):
        """Call setter(tr(key, *args)) now and again on retranslate()."""
        if not hasattr(self, "_tr_items"):
            self._tr_items = []
        setter(tr(key, *args))
        self._tr_items.append((setter, key, args))

    def retranslate(self):
        for setter, key, args in getattr(self, "_tr_items", []):
            setter(tr(key, *args))
        self._retranslate_extra()

    def _retranslate_extra(self):
        """Override for things that are not a single setter (headers...)."""
