import argparse
import base64
import json
import os, re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
from collections import defaultdict

from openai import OpenAI

def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

# -----------------------------
# 1) HARD-CODE YOUR EXCEL PATHS
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent  # points to backend/

EXCEL_PATHS = {
    "fujitsu": BASE_DIR / "assets" / "data" / "fujitsu_capacities_calculated.xlsx",
    "lg": BASE_DIR / "assets" / "data" / "lg_capacities_calculated.xlsx",
}

LOADS_SCHEMA = {
    "name": "conduit_loads",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "project": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "address": {"type": ["string", "null"]},          # ✅ allow null
                    "report_type": {"type": "string"},
                    "units": {"type": "string"},
                    "total_area_sqft": {"type": ["number", "null"]},
                },
                "required": ["address", "report_type", "units", "total_area_sqft"],  # ✅ must include all
            },
            "whole_unit": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "heating_btu_hr": {"type": "number"},
                    "cooling_btu_hr": {"type": ["number", "null"]},
                },
                "required": ["heating_btu_hr", "cooling_btu_hr"],
            },
            "zones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "zone_name": {"type": "string"},
                        "heating_btu_hr": {"type": "number"},
                        "rooms": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "room_name": {"type": "string"},
                                    "heating_btu_hr": {"type": "number"},
                                    "sqft": {"type": ["number", "null"]},
                                    "notes": {"type": "string"},
                                },
                                "required": ["room_name", "heating_btu_hr", "sqft", "notes"],  # ✅ include all
                            },
                        },
                    },
                    "required": ["zone_name", "heating_btu_hr", "rooms"],
                },
            },
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
        },
        "required": ["project", "whole_unit", "zones", "assumptions", "warnings", "confidence"],
    },
}

# -----------------------------------------
# 2) PLUG IN YOUR EXISTING CONDUIT PARSER
# -----------------------------------------
def parse_pdf(pdf_path: Path, model: str) -> dict:
    pdf_bytes = pdf_path.read_bytes()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    client = get_openai_client()
    resp = client.responses.create(
        model=model,
        instructions=(
            "You extract heating/cooling load requirements from Conduit-style PDFs.\n"
            "Return ONLY valid JSON matching the schema.\n"
            "Also extract Total Area (sqft) from page 1 as project.total_area_sqft. If not found, null.\n"
            "If room sqft is not clearly readable, set sqft null. Do not guess."
        ),
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Extract the loads into JSON."},
                {
                    "type": "input_file",
                    "filename": pdf_path.name,
                    "file_data": f"data:application/pdf;base64,{pdf_b64}",
                },
            ],
        }],
        text={
            "format": {
                "type": "json_schema",
                "name": LOADS_SCHEMA["name"],      # ✅ required
                "strict": True,
                "schema": LOADS_SCHEMA["schema"],  # ✅ inner schema
            }
        },
    )

    return json.loads(resp.output_text)

def build_building_summary(loads_json: Dict[str, Any]) -> Dict[str, Any]:
    zones_out = []
    rooms_out = []

    for z in loads_json.get("zones", []) or []:
        zone_name = z.get("zone_name")
        zone_heat = z.get("heating_btu_hr")
        zone_rooms = z.get("rooms", []) or []

        zones_out.append({
            "zone_name": zone_name,
            "heating_btu_hr": zone_heat,
            "room_names": [z.get("room_name") for r in zone_rooms if z.get("room_name")],
        })

        for r in zone_rooms:
            rooms_out.append({
                "zone_name": zone_name,
                "room_name": r.get("room_name"),
                "heating_btu_hr": r.get("heating_btu_hr"),
                "sqft": r.get("sqft"),
                "notes": r.get("notes", ""),
            })

    return {
        "project": loads_json.get("project", {}),
        "whole_unit": loads_json.get("whole_unit", {}),
        "zones": zones_out,
        "rooms": rooms_out,
    }

# ----------------------------------------------------
# 3) YOUR DETERMINISTIC ENGINE + EXCEL CALC WRAPPER
# ----------------------------------------------------
from typing import Optional, Any, Dict, List
import pandas as pd
import math
import re

def _to_num(x: Any) -> Optional[float]:
    """Convert Excel cell values like '3,720' or 3720 to float."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return None
    # remove commas and non-numeric (keep . and -)
    s = s.replace(",", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except:
        return None

def _infer_heads_from_row(row: Dict[str, Any]) -> int:
    """Count non-empty Unit 1..Unit 4 values."""
    count = 0
    for k in ["Unit 1", "Unit 2", "Unit 3", "Unit 4"]:
        v = row.get(k)
        if _to_num(v) is not None:
            count += 1
    return count

def _unit_mix_str(row: Dict[str, Any]) -> str:
    """Pretty string for Unit mix, e.g., '7k + 9k'."""
    units = []
    for k in ["Unit 1", "Unit 2", "Unit 3", "Unit 4"]:
        v = _to_num(row.get(k))
        if v is not None:
            # these look like '7' meaning 7k
            units.append(f"{int(v)}k")
    return " + ".join(units) if units else "(none)"

def _normalize_type_to_distribution(excel_type: str) -> Optional[str]:
    """
    Map your Excel 'Type' to distribution.
    Snippet shows 'Non-ducted' -> ductless.
    """
    t = (excel_type or "").strip().lower()
    if t in {"non-ducted", "nond-ducted", "nonducted", "ductless"}:
        return "ductless"
    if t in {"ducted"}:
        return "ducted"
    return None

def run_ashp_excel_candidates(
    required_btu_5f: Optional[float],
    required_btu_0f: Optional[float],
    distribution: str,
    indoor_head_count: int,
    preferences: Dict[str, Any],
    excel_paths: Dict[str, str],
    sheet_name: Optional[str] = None,
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """
    Reads a model spec workbook with columns like:
      Model, Type, Indoor Capacity, Unit 1..Unit 4, Total Capacity,
      Op. Watts/Htg, Breaker Req., BTU @ 5*F, BTU @ 0*F, Tonnage, SEER2, EER2, HSPF2
    Returns ranked candidates (dicts) for printing.
    """

    mfr = (preferences.get("manufacturer") or "fujitsu").strip().lower()
    if mfr not in excel_paths:
        mfr = "fujitsu"  # fallback

    path = excel_paths.get(mfr, excel_paths["fujitsu"])
    df = pd.read_excel(path, sheet_name=sheet_name)  # default first sheet

    # Normalize column names exactly as in workbook
    # If your workbook sometimes differs (e.g., extra spaces), you can strip:
    df.columns = [str(c).strip() for c in df.columns]

    # Optional manufacturer preference: if your Model encodes brand or you have a Manufacturer column
    # For now, we won't filter unless you actually have that column.

    # Filter by distribution using Type column
    def type_ok(x):
        dist = _normalize_type_to_distribution(x)
        return dist == distribution

    if "Type" in df.columns:
        df = df[df["Type"].apply(type_ok)]
    # else: no filtering

    # Compute heads from Unit columns and filter to desired count
    rows = df.to_dict(orient="records")
    filtered = []
    for r in rows:
        heads = _infer_heads_from_row(r)
        if heads == indoor_head_count:
            filtered.append(r)

    # If nothing matches exact heads, you can relax (optional):
    if not filtered:
        # fallback: allow <= heads (still useful if your sheet has 2-head combos but user asked 3, etc.)
        for r in rows:
            heads = _infer_heads_from_row(r)
            if heads <= indoor_head_count and heads > 0:
                filtered.append(r)

    # Rank by whether they meet the load, then by smallest oversize
    def score(r: Dict[str, Any]) -> tuple:
        b5 = _to_num(r.get("BTU @ 5*F")) or _to_num(r.get("BTU @ 5°F"))
        b0 = _to_num(r.get("BTU @ 0*F")) or _to_num(r.get("BTU @ 0°F"))
        total = _to_num(r.get("Total Capacity"))

        # choose governing requirement (prefer 5F if present, else 0F, else total)
        req = required_btu_5f or required_btu_0f
        cap = b5 or b0 or total

        meets = 0
        oversize = float("inf")
        if req is not None and cap is not None:
            meets = 1 if cap >= req else 0
            oversize = (cap - req) if cap >= req else (req - cap) + 1e6  # big penalty if undersized
        # Secondary: prefer lower breaker/op watts if similar
        breaker = _to_num(r.get("Breaker Req.")) or 9999
        watts = _to_num(r.get("Op. Watts/Htg")) or 9e9

        # Sort keys: meets first, then smallest oversize, then lower breaker, then lower watts
        return (-meets, oversize, breaker, watts)

    filtered.sort(key=score)

    # Build candidates list
    out: List[Dict[str, Any]] = []
    for idx, r in enumerate(filtered[:top_n], start=1):
        cand = {
            "rank": idx,
            "outdoor_model": r.get("Model"),
            "type": r.get("Type"),
            "unit_mix": _unit_mix_str(r),
            "heads": _infer_heads_from_row(r),
            "total_capacity": _to_num(r.get("Total Capacity")),
            "btu_5f": _to_num(r.get("BTU @ 5*F")) or _to_num(r.get("BTU @ 5°F")),
            "btu_0f": _to_num(r.get("BTU @ 0*F")) or _to_num(r.get("BTU @ 0°F")),
            "breaker_req": _to_num(r.get("Breaker Req.")),
            "op_watts_htg": _to_num(r.get("Op. Watts/Htg")),
            "seer2": _to_num(r.get("SEER2")),
            "eer2": _to_num(r.get("EER2")),
            "hspf2": _to_num(r.get("HSPF2")),
            "tonnage": _to_num(r.get("Tonnage")),
            "notes": "",
        }

        # Mark meets
        req = required_btu_5f or required_btu_0f
        cap = cand["btu_5f"] or cand["btu_0f"] or cand["total_capacity"]
        if req is not None and cap is not None:
            cand["meets_required"] = cap >= req
            cand["delta_btu"] = cap - req
        else:
            cand["meets_required"] = None
            cand["delta_btu"] = None

        out.append(cand)

    return out

# -----------------------------
# 4) OPENAI: INTENT JSON CALL
# -----------------------------
INTENT_SCHEMA = {
    "name": "conduit_intent",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "systems": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "system_name": {"type": "string"},
                        "scope": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "type": {"type": "string", "enum": ["zone_all", "rooms", "whole_building"]},
                                "zone_name": {"type": ["string", "null"]},
                                "room_names": {"type": ["array", "null"], "items": {"type": "string"}},
                            },
                            # ✅ strict mode requires all keys listed here
                            "required": ["type", "zone_name", "room_names"],
                        },
                        "distribution": {"type": "string", "enum": ["ductless", "ducted"]},
                        "indoor_head_count": {"type": "integer", "minimum": 1},
                        "margin_pct": {"type": "number", "minimum": 0, "maximum": 0.5},
                        "preferences": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "manufacturer": {"type": ["string", "null"], "enum": ["fujitsu", "lg", None]},
                                "priority": {"type": ["string", "null"]},
                                "max_breaker_amps": {"type": ["number", "null"]},
                            },
                            "required": ["manufacturer", "priority", "max_breaker_amps"],  # ✅ required must include all keys
                        },
                    },
                    "required": ["system_name", "scope", "distribution", "indoor_head_count", "margin_pct", "preferences"],
                },
            },
            "questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["systems", "questions"],
    },
}

def get_intent(building_summary: dict, user_text: str, model: str) -> dict:
    print("DEBUG preferences schema:", INTENT_SCHEMA["schema"]["properties"]["systems"]["items"]["properties"]["preferences"])
    
    client = get_openai_client()
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": (
                "Convert the user's HVAC scope request into intent JSON.\n"
                "Rules:\n"
                "- Only reference zone_name and room_name values that appear in building_summary.\n"
                "- If ambiguous, add a question in questions[].\n"
                "- Prefer scope.type='zone_all' for floors/stories.\n"
                "- Output MUST match the JSON schema exactly.\n"
                "- For scope.type='zone_all': set scope.zone_name to an existing zone, and set scope.room_names to null.\n"
                "- For scope.type='rooms': set scope.room_names to a list of existing room names, and set scope.zone_name to null.\n"
                "- For scope.type='whole_building': set both scope.zone_name and scope.room_names to null.\n"
            )},
            {"role": "user", "content": (
                "building_summary:\n"
                + json.dumps(building_summary, indent=2)
                + "\n\nuser_request:\n"
                + user_text
            )},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": INTENT_SCHEMA["name"],      # ✅ REQUIRED
                "strict": True,
                "schema": INTENT_SCHEMA["schema"],  # ✅ REQUIRED
            }
        },
    )
    return json.loads(resp.output_text)

def recommend_from_intent(intent: dict, building_summary: dict) -> dict:
    # Index rooms by zone and name
    rooms = building_summary.get("rooms", [])
    zones = building_summary.get("zones", [])

    rooms_by_zone = {}
    room_load = {}
    for r in rooms:
        zn = r.get("zone_name")
        rn = r.get("room_name")
        if not zn or not rn:
            continue
        rooms_by_zone.setdefault(zn, []).append(rn)
        room_load[(zn, rn)] = r.get("heating_btu_hr")

    zone_names = [z.get("zone_name") for z in zones if z.get("zone_name")]

    drafts = []
    warnings = []

    for s in intent.get("systems", []):
        scope = s["scope"]
        t = scope["type"]
        margin = float(s.get("margin_pct") or 0.15)
        prefs = s.get("preferences") or {}

        # Expand scope -> selected rooms
        selected = []
        zone_name = None

        if t == "whole_building":
            # all rooms across all zones
            for zn in zone_names:
                for rn in rooms_by_zone.get(zn, []):
                    selected.append((zn, rn))

        elif t == "zone_all":
            zone_name = scope.get("zone_name")
            if not zone_name or zone_name not in rooms_by_zone:
                warnings.append(f"Unknown zone_name '{zone_name}'. Available: {zone_names}")
            else:
                for rn in rooms_by_zone[zone_name]:
                    selected.append((zone_name, rn))
                    #room_load_lookup[(zone_name, rn)] = room_heating_btu

        elif t == "rooms":
            # room_names might be ambiguous across zones; try to match any
            wanted = scope.get("room_names") or []
            for wn in wanted:
                matched = False
                for zn in zone_names:
                    if wn in rooms_by_zone.get(zn, []):
                        selected.append((zn, wn))
                        matched = True
                        break
                if not matched:
                    warnings.append(f"Room '{wn}' not found in any zone.")

        # Sum loads
        total_heat = 0.0
        have_any = False
        selected_room_labels = []

        for zn, rn in selected:
            selected_room_labels.append(f"{zn} / {rn}")
            btu = room_load.get((zn, rn))
            if isinstance(btu, (int, float)):
                total_heat += float(btu)
                have_any = True

        required_btu = (total_heat * (1 + margin)) if have_any else None

        # Excel candidates
        cands = run_ashp_excel_candidates(
            required_btu_5f=required_btu,     # you only have one heating number in schema
            required_btu_0f=None,
            distribution=s["distribution"],
            indoor_head_count=int(s["indoor_head_count"]),
            preferences=prefs,
            excel_paths=EXCEL_PATHS,
            sheet_name="indoor_combinations",
            top_n=10,
        )

        print("Selected Rooms:", selected)

        drafts.append({
            "system_name": s["system_name"],
            "distribution": s["distribution"],
            "indoor_head_count": s["indoor_head_count"],
            "margin_pct": margin,
            "zone_name": zone_name,

            # ✅ keep BOTH
            "selected_rooms": selected,                  # [(zone, room), ...]
            "selected_room_labels": selected_room_labels, # ["Zone / Room", ...]

            "room_load_lookup": room_load,               # {(zone, room): btu}
            "required_heat_btu_hr": required_btu,
            "candidates": cands,
        })

    return {"drafts": drafts, "warnings": warnings}

# CHOOSE HEADS BASED ON ROOM LOAD REQUIREMENTS
def _head_nominal_btu(head: str) -> int:
    # "7k" -> 7000, "12k" -> 12000
    m = re.search(r"(\d+)", head.lower())
    return int(m.group(1)) * 1000 if m else 0

def assign_heads_to_rooms(
    rooms: List[Dict[str, Any]],     # [{room_name, heating_btu_hr}]
    unit_mix: List[str],             # ["7k","9k",...]
    room_margin_pct: float = 0.10,
) -> Dict[str, Any]:
    # sort rooms by required load desc
    room_items = []
    for r in rooms:
        load = r.get("heating_btu_hr")
        if not isinstance(load, (int, float)):
            continue
        req = float(load) * (1.0 + room_margin_pct)
        room_items.append((r["room_name"], req, float(load)))

    room_items.sort(key=lambda x: x[1], reverse=True)

    # sort heads by capacity desc
    heads = sorted(unit_mix, key=_head_nominal_btu, reverse=True)

    assignments = []
    warnings = []

    for i, (room_name, req, base) in enumerate(room_items):
        if i >= len(heads):
            warnings.append(f"Not enough heads for rooms: missing head for '{room_name}'")
            continue
        head = heads[i]
        cap = _head_nominal_btu(head)
        delta = cap - req
        assignments.append({
            "room_name": room_name,
            "room_load_btu": base,
            "room_required_btu": req,
            "assigned_head": head,
            "head_capacity_btu": cap,
            "delta_btu": delta,
            "meets": delta >= 0,
        })

    # if extra heads (more heads than rooms), flag it
    if len(heads) > len(room_items):
        warnings.append(f"More heads than rooms: {len(heads)} heads for {len(room_items)} rooms.")

    # undersize warnings
    for a in assignments:
        if not a["meets"]:
            warnings.append(
                f"Undersized: {a['room_name']} needs {a['room_required_btu']:.0f} BTU, "
                f"assigned {a['assigned_head']} (~{a['head_capacity_btu']} BTU)."
            )

    return {"assignments": assignments, "warnings": warnings}

# -----------------------------
# 5) CLI + INTERACTIVE LOOP
# -----------------------------
def fmt0(x, suffix=""):
    if isinstance(x, (int, float)):
        return f"{x:,.0f}{suffix}"
    return ""

def format_rooms_with_loads(selected_rooms, room_load_lookup):
    """
    selected_rooms: [(zone, room), ...]
    room_load_lookup: {(zone, room): heating_btu}
    """
    grouped = defaultdict(list)

    for zone, room in selected_rooms:
        load = room_load_lookup.get((zone, room))
        if isinstance(load, (int, float)):
            grouped[zone].append((room, load))
        else:
            grouped[zone].append((room, None))

    lines = []

    for zone, rooms in grouped.items():
        lines.append(f"{zone} ({len(rooms)} rooms selected)")
        for room, load in rooms:
            if load is not None:
                lines.append(f"  • {room} – {load:,.0f} BTU")
            else:
                lines.append(f"  • {room} – (no load found)")
        lines.append("")  # spacing

    return "\n".join(lines)

def print_recommendations_page(rec: dict, page: int = 0, page_size: int = 5) -> None:
    print("\n================ RECOMMENDATIONS ================\n")

    warnings = rec.get("warnings") or []
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"  - {w}")
        print("")

    drafts = rec.get("drafts") or []
    if not drafts:
        print("No recommendations available.")
        return

    # If you eventually have multiple systems, you can loop drafts here.
    d = drafts[0]

    system_name = d.get("system_name")
    selected_rooms = d.get("selected_rooms") or []
    room_load_lookup = d.get("room_load_lookup") or {}

    distribution = d.get("distribution")
    heads = d.get("indoor_head_count")
    margin_pct = d.get("margin_pct")
    req = d.get("required_heat_btu_hr")

    print(f"{system_name} :")
    if selected_rooms:
        print("Rooms & Heating Loads:")
        print(format_rooms_with_loads(selected_rooms, room_load_lookup))
        print("")

    print(f"{distribution} | heads = {heads}")
    if isinstance(margin_pct, (int, float)):
        print(f"Margin: {int(margin_pct * 100)}%")
    if isinstance(req, (int, float)):
        print(f"Required Heating Load: {req:,.0f} BTU/hr")
    print("")

    candidates = d.get("candidates") or []
    start = page * page_size
    end = start + page_size
    subset = candidates[start:end]

    if not subset:
        print("No more options.")
        return

    for display_num, c in enumerate(subset, start=start + 1):
        meets = c.get("meets_required")
        meets_txt = "meets" if meets is True else ("undersized" if meets is False else "n/a")
        delta = c.get("delta_btu")
        delta_txt = f"{delta:+,.0f} BTU" if isinstance(delta, (int, float)) else ""

        line = (
            f"#{display_num}: {c.get('outdoor_model')} | "
            f"Mix: {c.get('unit_mix','')} | "
            f"BTU@5F: {fmt0(c.get('btu_5f'))} | "
            f"BTU@0F: {fmt0(c.get('btu_0f'))} | "
            f"Total: {fmt0(c.get('total_capacity'))} | "
            f"Breaker: {fmt0(c.get('breaker_req'), 'A')} | "
            f"OpWatts(Htg): {fmt0(c.get('op_watts_htg'))} | "
            f"SEER2: {fmt0(c.get('seer2'))} "
            f"EER2: {fmt0(c.get('eer2'))} "
            f"HSPF2: {fmt0(c.get('hspf2'))} | "
            f"{meets_txt} {delta_txt}"
        )
        print(line)

def interactive_loop(building_summary: dict, model_intent: str, out_path: Path):
    print("\nEnter AI instructions. Examples:")
    print(" - Only replace the 3rd floor. Ductless. Need 2 indoor heads.")
    print(" - Replace whole building. Ductless. Prefer Fujitsu.\n")

    user_text = input("> ").strip()
    if not user_text:
        print("No input; exiting.")
        return

    while True:
        # 1) AI: instructions -> intent JSON
        intent = get_intent(building_summary=building_summary, user_text=user_text, model=model_intent)

        # 2) If AI asks clarifying questions, ask user and loop
        questions = intent.get("questions") or []
        if questions:
            print("\nI need clarification:")
            for q in questions:
                print(f"- {q}")
            ans = input("\nAnswer (or 'exit'): ").strip()
            if ans.lower() in {"exit", "quit"}:
                return
            user_text = user_text + "\n\nUser clarification: " + ans
            continue

        # 3) Deterministic: intent -> recommendations (Excel candidates etc.)
        rec = recommend_from_intent(intent, building_summary)

        # 4) Print
        #print_recommendations(rec)

        # 5) Accept / revise / exit
        # Track paging
        page = 0
        page_size = 5

        while True:
            print_recommendations_page(rec, page=page, page_size=page_size)

            choice = input(
                "\nSelect option number, type 'more' for more options, "
                "'revise' to change request, or 'exit': "
            ).strip().lower()

            if choice in {"exit", "quit"}:
                print("Exiting without saving.")
                return

            if choice == "more":
                page += 1
                continue

            if choice == "revise":
                new_text = input("\nEnter revised instructions: ").strip()
                if not new_text:
                    continue
                user_text = new_text
                break  # restart outer loop

            # If numeric selection
            if choice.isdigit():
                selected_index = int(choice) - 1
                drafts = rec.get("drafts") or []
                if not drafts:
                    print("No drafts available.")
                    continue

                # Assuming single system for now
                #print("DEBUG drafts:", drafts)
                draft = drafts[0]
                #print("DEBUG draft for selection:", draft)
                candidates = drafts[0].get("candidates") or []

                if 0 <= selected_index < len(candidates):
                    selected_candidate = candidates[selected_index]

                    payload = {
                        "building_summary": building_summary,
                        "intent": intent,
                        "selected_candidate": selected_candidate,
                    }

                    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                    print(f"\n✅ Saved selection #{selected_index+1} to {out_path}\n")

                    selected_candidate = candidates[selected_index]

                    # ----- Head assignment preview -----
                    selected_rooms = draft.get("selected_rooms") or []  # MUST be [(zone, room), ...]
                    #print("DEBUG selected_rooms:", selected_rooms)
                    room_load_lookup = draft.get("room_load_lookup") or {}

                    room_loads = []
                    for zone_name, room_name in selected_rooms:
                        # you likely already have a dict like rooms_by_zone_loads
                        load = room_load_lookup.get((zone_name, room_name))
                        if load is not None:
                            room_loads.append({
                                "room_name": f"{zone_name} / {room_name}",
                                "heating_btu_hr": load,
                            })

                    # Call assignment
                    assignment_result = assign_heads_to_rooms(
                        rooms=room_loads,
                        unit_mix=selected_candidate.get("unit_mix", "").split(" + "),
                        room_margin_pct=0.10,
                    )

                    print("\n--- HEAD ASSIGNMENT ---\n")
                    for a in assignment_result["assignments"]:
                        meets_txt = "✓" if a["meets"] else "✗"
                        print(
                            f"{a['room_name']} → {a['assigned_head']} "
                            f"(needs {a['room_required_btu']:.0f}, nominal head {a['head_capacity_btu']}) {meets_txt}"
                        )

                    if assignment_result["warnings"]:
                        print("\nWarnings:")
                        for w in assignment_result["warnings"]:
                            print(" -", w)

                    return
                else:
                    print("Invalid selection number.")
                    continue

            print("Invalid input.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=str, help="Path to Conduit PDF")
    ap.add_argument("--parse-model", default="gpt-5.2", help="Model used for PDF->loads parsing")
    ap.add_argument("--intent-model", default="gpt-5.2", help="Model used for intent extraction")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--cache", type=str, default="parsed_loads.json", help="Cache loads JSON here")
    ap.add_argument("--out", type=str, default="accepted_recommendation.json")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    cache_path = Path(args.cache)

    # Parse stage (use cache if exists)
    if cache_path.exists():
        loads_json = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"Loaded cached loads JSON: {cache_path}")
    else:
        print("Parsing PDF into loads JSON...")
        loads_json = parse_pdf(pdf_path, model=args.parse_model)
        cache_path.write_text(json.dumps(loads_json, indent=2), encoding="utf-8")
        print(f"Saved loads JSON cache: {cache_path}")

    building_summary = build_building_summary(loads_json)

    if args.interactive:
        interactive_loop(building_summary, model_intent=args.intent_model, out_path=Path(args.out))
    else:
        print("Run with --interactive to enter instructions.")


if __name__ == "__main__":
    main()