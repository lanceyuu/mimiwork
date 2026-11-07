"""Check a reference list against Crossref and OpenAlex (spec 2026-11-07)."""

from .run import NoModel, check_file, plan_fixes, prune
from .verdicts import Lookups, describe, live_lookups

__all__ = ["Lookups", "NoModel", "check_file", "describe", "live_lookups", "plan_fixes", "prune"]
