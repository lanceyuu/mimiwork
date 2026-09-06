"""The account's own environmental footprint: a rough per-token estimate over this
month's ledger rows, standing on its own when Scaleway's service-wide figure is down."""

from coworker.footprint import estimate
from coworker.server.manager import SessionManager


def test_estimate_scales_with_tokens_and_grid():
    eu = estimate(100_000, 10_000, "eu")
    assert eu["energy_wh"] == 10.0 and eu["carbon_g"] == 0.55
    assert estimate(100_000, 10_000, "us")["carbon_g"] > eu["carbon_g"]
    assert estimate(0, 0)["carbon_g"] == 0


def test_footprint_sums_this_month_only_and_survives_a_dead_measurement(monkeypatch):
    from datetime import datetime, timezone

    mgr = SessionManager.__new__(SessionManager)
    now = datetime.now(timezone.utc)
    this = now.strftime("%Y-%m-15T10:00:00")
    last = (now.replace(day=1)).strftime("%Y-%m-01T00:00:00")
    last = f"{int(last[:4]) - (1 if last[5:7] == '01' else 0):04d}-{(int(last[5:7]) - 2) % 12 + 1:02d}-20T00:00:00"
    pages = {
        0: [
            {"at": this, "tokens_in": 60_000, "tokens_out": 4_000},
            {"at": this, "tokens_in": 40_000, "tokens_out": 6_000},
            {"at": last, "tokens_in": 999_999, "tokens_out": 999_999},  # older: stops the walk
        ]
    }
    seen = []
    monkeypatch.setattr(
        mgr,
        "qualitati_credits",
        lambda limit=50, offset=0: (seen.append(offset), {"ok": True, "entries": pages.get(offset // 200, [])})[1],
    )
    monkeypatch.setattr(mgr, "qualitati_region", lambda: {"ok": True, "region": "eu"})
    monkeypatch.setattr(mgr, "_qualitati_get", lambda path, label: {"ok": False, "error": "503"})

    out = mgr.qualitati_footprint()
    assert out["ok"] and "error" not in out
    you = out["you"]
    assert (you["tokens_in"], you["tokens_out"], you["calls"]) == (100_000, 10_000, 2)
    assert you["carbon_g"] == 0.55 and you["region"] == "eu"
    assert seen == [0]  # the older row ended the walk before a second page
