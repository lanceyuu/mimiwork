"""Run a real reference list against the live services and print each verdict.

Manual, before a release (spec 2026-11-07, Testing). Needs the network and a model:
    .venv/bin/python scripts/live_refcheck.py
It builds a small Word file with known cases and uses the default Anthropic model through
the user's saved key, so it costs a few cents.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import docx

from coworker import refcheck
from coworker.providers import ProviderRouter
from coworker.secrets import SecretStore

CASES = [
    # Retracted in 2010: must land in Retracted.
    "Wakefield, A. J., Murch, S. H., Anthony, A., et al. (1998). Ileal-lymphoid-nodular hyperplasia, non-specific colitis, and pervasive developmental disorder in children. The Lancet, 351(9103), 637-641. https://doi.org/10.1016/S0140-6736(97)11096-0",
    # Not in Crossref; Crossref's top hit is a posted copy: must verify as found_copy or found_openalex, never supply a DOI.
    "Vaswani, A., Shazeer, N., Parmar, N., et al. (2017). Attention is all you need. Advances in Neural Information Processing Systems, 30.",
    # A DataCite DOI: must verify as Found on DataCite.
    "Vaswani, A., et al. (2017). Attention is all you need. arXiv. https://doi.org/10.48550/arXiv.1706.03762",
    # A book: must verify, or show an edition note only.
    "Bandura, A. (1997). Self-efficacy: The exercise of control. W. H. Freeman.",
    # A misspelled first author: must offer a surname fix.
    "Baumiester, R. F., Bratslavsky, E., Muraven, M., & Tice, D. M. (1998). Ego depletion: Is the active self a limited resource? Journal of Personality and Social Psychology, 74(5), 1252-1265.",
]


def main() -> int:
    folder = Path(tempfile.mkdtemp())
    path = folder / "live.docx"
    document = docx.Document()
    document.add_paragraph("References")
    for case in CASES:
        document.add_paragraph(case)
    document.save(path)
    secrets = SecretStore()
    provider = ProviderRouter(secrets, default_provider="anthropic")
    model = sys.argv[1] if len(sys.argv) > 1 else "anthropic:claude-haiku-4-5"

    def complete(system: str, user: str) -> str:
        turn = provider.complete(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=8000,
            reasoning_effort="none",
        )
        return turn.text or ""

    result = refcheck.check_file(path, complete=complete, lookups=refcheck.live_lookups(secrets), cache_dir=folder / "cache")
    if not result.get("ok"):
        print("check failed:", result)
        return 1
    print(result["counts"])
    for row in result["entries"]:
        print(f"\n[{row['group']}] {row['text'][:90]}")
        for c in row["codes"]:
            print("   -", refcheck.describe(c["code"], c["params"]))
        for fix in row["fixes"]:
            print("   fix:", fix["kind"], "->", fix["new"], "(writable)" if fix["writable"] else "(suggestion)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
