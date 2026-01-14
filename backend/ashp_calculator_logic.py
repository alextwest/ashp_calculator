# backend/ashp_calculator_logic.py
from __future__ import annotations

from pathlib import Path
import pandas as pd
import re

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "assets" / "data"

MANUFACTURER_FILES = {
    "Fujitsu": DATA_DIR / "fujitsu_capacities_calculated.xlsx",
    "LG":      DATA_DIR / "lg_capacities_calculated.xlsx",
}

SHEET_NAME = "indoor_combinations"

DETAIL_COLS = [
    "Op. Watts/Htg",
    "Breaker Req.",
    "BTU @ 5*F",
    "BTU @ 0*F",
    "Tonnage",
    "SEER2",
    "EER2",
    "HSPF2",
]

def detect_unit_columns(df: pd.DataFrame):
    unit_nums = []
    for c in df.columns:
        m = re.fullmatch(r"Unit (\d+)", str(c).strip())
        if m:
            unit_nums.append(int(m.group(1)))

    if not unit_nums:
        raise ValueError("No 'Unit N' columns found.")

    max_n = max(unit_nums)

    paired = []
    for i in range(1, max_n + 1):
        u = f"Unit {i}"
        c = f"Max Capacity Unit {i}"
        if u in df.columns and c in df.columns:
            paired.append((u, c))

    if not paired:
        raise ValueError("Found Unit columns but no matching Max Capacity Unit columns.")

    unit_cols = [u for u, _ in paired]
    cap_cols  = [c for _, c in paired]
    return unit_cols, cap_cols


def load_combos(manufacturer: str) -> pd.DataFrame:
    if manufacturer not in MANUFACTURER_FILES:
        raise ValueError(f"Unknown manufacturer: {manufacturer}")

    path = MANUFACTURER_FILES[manufacturer]
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {path}")

    df = pd.read_excel(path, sheet_name=SHEET_NAME)

    unit_cols, cap_cols = detect_unit_columns(df)

    required = {"Model", "Type", "Indoor Capacity", "Total Capacity"} | set(unit_cols) | set(cap_cols)
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {path.name} sheet '{SHEET_NAME}': {sorted(missing)}")

    df = df.copy()
    df.attrs["UNIT_COLS"] = unit_cols
    df.attrs["CAP_COLS"] = cap_cols

    df["Model"] = df["Model"].astype(str).str.strip()
    df["Type"] = df["Type"].fillna("").astype(str).str.strip()
    df["Indoor Capacity"] = pd.to_numeric(df["Indoor Capacity"], errors="coerce")
    df["Total Capacity"] = pd.to_numeric(df["Total Capacity"], errors="coerce")

    for c in unit_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in cap_cols:
        df[c] = df[c].astype(str).str.replace(",", "", regex=False).replace({"nan": None, "None": None})
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # make sure the columns exist (avoid KeyError if sheet missing them)
    for c in DETAIL_COLS:
        if c not in df.columns:
            df[c] = None

    # parse numeric columns (commas -> numbers)
    for c in DETAIL_COLS:
        df[c] = df[c].astype(str).str.replace(",", "", regex=False).replace({"nan": None, "None": None})
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


def find_options(df: pd.DataFrame, reqs, type_filter="All", max_results=300):
    unit_cols = df.attrs["UNIT_COLS"]
    cap_cols  = df.attrs["CAP_COLS"]

    reqs = [float(x) for x in reqs]
    n = len(reqs)

    if type_filter != "All":
        df2 = df[df["Type"].fillna("").astype(str).str.strip() == type_filter].copy()
    else:
        df2 = df

    results = []

    for _, row in df2.iterrows():
        sizes, caps = [], []
        for ucol, ccol in zip(unit_cols, cap_cols):
            u = row.get(ucol)
            c = row.get(ccol)
            if pd.notna(u) and pd.notna(c):
                sizes.append(int(u))
                caps.append(float(c))

        if len(caps) != n:
            continue

        caps_sorted = sorted(caps, reverse=True)
        reqs_sorted = sorted(reqs, reverse=True)

        mapping = []
        ok = True
        for req, cap in zip(reqs_sorted, caps_sorted):
            if cap < req:
                ok = False
                break
            mapping.append((req, cap))

        if not ok:
            continue

        worst_margin = min(cap - req for req, cap in mapping)
        total_margin = sum(caps_sorted) - sum(reqs_sorted)

        results.append({
            "Model": row["Model"],
            "Type": row["Type"],
            "Indoor Capacity": None if pd.isna(row["Indoor Capacity"]) else float(row["Indoor Capacity"]),
            "Total Capacity": None if pd.isna(row["Total Capacity"]) else float(row["Total Capacity"]),
            "Units": "+".join(map(str, sizes)),
            "worst_margin": float(worst_margin),
            "margin_total": float(total_margin),
            "mapping": mapping,
            "heads_detected": len(unit_cols),
        })

        if len(results) >= max_results:
            break

    results.sort(key=lambda r: (-r["worst_margin"], r["margin_total"]))
    return results


def run_logic(manufacturer: str, reqs, type_filter="All", max_results=300):
    """
    Backend-friendly wrapper used by FastAPI.
    """
    df = load_combos(manufacturer)

    print("Top 10 rows of loaded data:", df.head(10))

    return {
        "manufacturer": manufacturer,
        "type_filter": type_filter,
        "max_heads": len(df.attrs["UNIT_COLS"]),
        "results": find_options(df, reqs=reqs, type_filter=type_filter, max_results=max_results),
    }
