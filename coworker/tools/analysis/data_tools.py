"""``inspect_data`` — read a dataset's shape before analysing it.

The single highest-leverage tool for survey and business data. Loading a file blind and
guessing at what ``q4_1`` means is how an analysis goes quietly wrong: the model produces a
confident mean of a column that turns out to be a 1–5 Likert code, or averages a variable
where 99 means "declined to answer".

So for SPSS (.sav) and Stata (.dta) this returns the **variable labels and value labels** that
those formats carry, which is exactly the metadata that makes ``q4_1`` legible as
"Satisfaction with onboarding (1=Strongly disagree … 5=Strongly agree)". For every format it
returns schema, missingness, and summary statistics — enough to plan an analysis without
loading the whole file into context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..office._common import decorate, guard, require
from ..office.paths import context_roots, display_path, resolve_read

_MAX_SAMPLE = 5
_MAX_LEVELS = 20
_MAX_COLUMNS = 200

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "inspect_data",
        "description": (
            "Profile a dataset without loading it into the conversation: shape, column names "
            "and types, missing-value counts, sample values, and summary statistics. Supports "
            "CSV, TSV, Excel, SPSS (.sav), Stata (.dta), Parquet, and JSON. For SPSS and Stata "
            "it also returns variable labels and value labels — read these BEFORE interpreting "
            "any coded column, so you don't average a Likert code or treat 99 as a real value. "
            "Always inspect a dataset before analysing it. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The data file to profile."},
                "sheet": {
                    "type": "string",
                    "description": "Excel only: sheet name (default: the first sheet).",
                },
                "columns": {
                    "type": "array",
                    "description": "Only profile these columns (default: all).",
                    "items": {"type": "string"},
                },
            },
            "required": ["path"],
        },
    },
}


def _load(target: Path, sheet: str) -> tuple[Any, dict[str, Any]]:
    """Return (DataFrame, metadata). Metadata carries SPSS/Stata labels when the format has them."""
    pd = require("pandas", "pandas", extra="analysis")
    suffix = target.suffix.lower()
    meta: dict[str, Any] = {}

    if suffix in {".csv", ".txt"}:
        return pd.read_csv(target), meta
    if suffix in {".tsv", ".tab"}:
        return pd.read_csv(target, sep="\t"), meta
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        require("openpyxl", "openpyxl")
        frame = pd.read_excel(target, sheet_name=sheet or 0)
        meta["sheets"] = list(pd.ExcelFile(target).sheet_names)
        return frame, meta
    if suffix == ".parquet":
        return pd.read_parquet(target), meta
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(target, lines=suffix == ".jsonl"), meta
    if suffix in {".sav", ".zsav", ".por"}:
        pyreadstat = require("pyreadstat", "pyreadstat", extra="analysis")
        frame, reader = pyreadstat.read_sav(str(target), apply_value_formats=False)
        meta["variable_labels"] = dict(reader.column_names_to_labels or {})
        meta["value_labels"] = dict(reader.variable_value_labels or {})
        if getattr(reader, "missing_ranges", None):
            meta["missing_ranges"] = dict(reader.missing_ranges)
        return frame, meta
    if suffix == ".dta":
        pyreadstat = require("pyreadstat", "pyreadstat", extra="analysis")
        frame, reader = pyreadstat.read_dta(str(target), apply_value_formats=False)
        meta["variable_labels"] = dict(reader.column_names_to_labels or {})
        meta["value_labels"] = dict(reader.variable_value_labels or {})
        return frame, meta

    raise ValueError(
        f"unsupported data format {suffix!r}; supported: .csv, .tsv, .xlsx, .xls, .sav, "
        ".dta, .parquet, .json"
    )


def _profile_column(frame: Any, name: str) -> dict[str, Any]:
    series = frame[name]
    total = len(series)
    missing = int(series.isna().sum())
    entry: dict[str, Any] = {
        "name": str(name),
        "dtype": str(series.dtype),
        "missing": missing,
        "missing_pct": round(100.0 * missing / total, 1) if total else 0.0,
        "unique": int(series.nunique(dropna=True)),
    }

    present = series.dropna()
    if present.empty:
        entry["all_missing"] = True
        return entry

    is_numeric = str(series.dtype).startswith(("int", "float", "uint"))
    if is_numeric:
        entry["min"] = _scalar(present.min())
        entry["max"] = _scalar(present.max())
        entry["mean"] = _scalar(round(float(present.mean()), 4))
        entry["std"] = _scalar(round(float(present.std()), 4)) if len(present) > 1 else 0.0
        # A numeric column with few distinct values is almost always a coded categorical
        # (Likert, yes/no, group id). Showing its levels stops it being averaged blindly.
        if entry["unique"] <= _MAX_LEVELS:
            entry["levels"] = {
                _key(k): int(v) for k, v in present.value_counts().head(_MAX_LEVELS).items()
            }
    else:
        counts = present.value_counts().head(_MAX_LEVELS)
        entry["top_values"] = {_key(k): int(v) for k, v in counts.items()}

    entry["sample"] = [_scalar(v) for v in present.head(_MAX_SAMPLE).tolist()]
    return entry


def _scalar(value: Any) -> Any:
    """JSON-safe scalar: numpy types and timestamps become plain Python."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    return str(value)


def _key(value: Any) -> str:
    return str(_scalar(value))


def data_tools(context: Any) -> list:
    roots = context_roots(context)

    @guard
    def inspect_data(path: str, sheet: str = "", columns: Any = None) -> dict[str, Any]:
        target = resolve_read(path, roots)
        if not target.is_file():
            raise FileNotFoundError(display_path(target, roots))

        frame, meta = _load(target, sheet)
        names = [str(c) for c in frame.columns]
        if columns:
            wanted = [str(c) for c in columns]
            unknown = [c for c in wanted if c not in names]
            if unknown:
                raise KeyError(
                    f"no such column(s): {', '.join(unknown)}; available: {', '.join(names[:40])}"
                )
            names = wanted

        truncated_columns = len(names) > _MAX_COLUMNS
        profiled = names[:_MAX_COLUMNS]

        result: dict[str, Any] = {
            "path": display_path(target, roots),
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "column_names": [str(c) for c in frame.columns][:_MAX_COLUMNS],
            "profile": [_profile_column(frame, name) for name in profiled],
        }
        if truncated_columns:
            result["note"] = (
                f"profiled the first {_MAX_COLUMNS} of {len(names)} columns; pass 'columns' "
                "to profile specific ones"
            )
        if meta.get("sheets"):
            result["sheets"] = meta["sheets"]

        # The SPSS/Stata payoff: what the coded columns actually mean.
        labels = meta.get("variable_labels") or {}
        values = meta.get("value_labels") or {}
        if labels:
            result["variable_labels"] = {
                k: v for k, v in labels.items() if v and k in set(profiled)
            }
        if values:
            result["value_labels"] = {k: v for k, v in values.items() if k in set(profiled)}
        if meta.get("missing_ranges"):
            result["missing_ranges"] = meta["missing_ranges"]
        if labels or values:
            result["labels_note"] = (
                "this dataset carries variable/value labels — use them to interpret coded "
                "columns, and check for reserved missing codes before computing statistics"
            )
        return result

    return [decorate(inspect_data, name="inspect_data", schema=_SCHEMA)]
