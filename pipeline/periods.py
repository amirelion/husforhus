"""Compatibility re-export: the periods live in pipeline.city (contract C1).

Note the tuple shape changed from upstream's (key, label, from, to, colour) to
(key, label_en, label_sv, from, to, colour).
"""
from .city import PERIODS, period_index

__all__ = ["PERIODS", "period_index"]
