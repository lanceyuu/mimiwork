"""A person's own share of the Mimi service's environmental impact — a ROUGH estimate.

Scaleway measures the whole service (carbon + water, month to date) but says nothing
per user. The user asked for an individual figure and accepted an estimate (2026-09-07),
so this scales public per-token energy figures by the account's own token counts and
the grid where its models run. Every constant is a round order-of-magnitude number,
not a measurement; the UI says so.

- Energy: decoding an output token costs about ten times a prefilled input token.
  0.5 Wh per 1k output tokens and 0.05 Wh per 1k input tokens sit inside the range
  published for large hosted models (Google's 2025 median text prompt: 0.24 Wh).
- Carbon: the grid. France (Scaleway Paris, the "eu" region) runs near 55 gCO2e/kWh;
  the US average grid (the default "us" region) near 390 gCO2e/kWh.
- Water: 1.8 L/kWh, the average on-site cooling figure for US data centers (LBNL).
"""

from __future__ import annotations

from typing import Any

WH_PER_1K_OUTPUT = 0.5
WH_PER_1K_INPUT = 0.05
GRID_G_CO2E_PER_KWH = {"eu": 55.0, "us": 390.0}
WATER_L_PER_KWH = 1.8


def estimate(tokens_in: int, tokens_out: int, region: str = "us") -> dict[str, Any]:
    """Carbon (g CO2e) and water (L) for the given token counts on the given grid."""
    wh = tokens_out / 1000 * WH_PER_1K_OUTPUT + tokens_in / 1000 * WH_PER_1K_INPUT
    grid = GRID_G_CO2E_PER_KWH.get(region, GRID_G_CO2E_PER_KWH["us"])
    return {
        "carbon_g": round(wh / 1000 * grid, 4),
        "water_l": round(wh / 1000 * WATER_L_PER_KWH, 6),
        "energy_wh": round(wh, 3),
        "region": region if region in GRID_G_CO2E_PER_KWH else "us",
        "method": "rough estimate: public per-token energy figures × your tokens × the grid",
    }


if __name__ == "__main__":  # ponytail self-check
    e = estimate(100_000, 10_000, "eu")
    assert e["energy_wh"] == 10.0 and e["carbon_g"] == 0.55 and e["water_l"] == 0.018
    assert estimate(0, 10_000, "mars")["region"] == "us"
    assert estimate(0, 10_000, "us")["carbon_g"] > estimate(0, 10_000, "eu")["carbon_g"]
    print("ok")
