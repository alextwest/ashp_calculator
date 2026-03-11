import logging
import traceback
import math
from typing_extensions import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path

from ai_agent_system_design import get_intent, recommend_from_intent, build_building_summary, post_validate_intent
from ashp_calculator_logic import run_logic

logger = logging.getLogger("ashp.ai")

router = APIRouter()

## Defining paths for static mounting at the end
DIST_DIR = Path(__file__).resolve().parent / "frontend_dist"
INDEX_HTML = DIST_DIR / "index.html"
ASSETS_DIR = DIST_DIR / "assets"


# -----------------------------
# TEMP STUB loads for testing
# -----------------------------
def default_loads():
    # “Conduit-like” example load package (robust stub)
    loads = {
        "project": {
            "address": "70 Lagrange St, West Roxbury, MA 02132, USA",
            "report_type": "Homeowner Report",
            "units": "sqft",
            "total_area_sqft": 2156,
        },

        # Whole-unit totals from the report
        "whole_unit": {
            "heating_btu_hr": 46745,
            "cooling_btu_hr": 19472,
        },

        # Zone + room breakdown
        "zones": [
            {
                "zone_name": "Basement",
                "heating_btu_hr": 4933,
                "cooling_btu_hr": None,  # not provided in source
                "rooms": [
                    {"room_name": "Gym",        "heating_btu_hr": 2948, "cooling_btu_hr": None, "sqft": 208, "notes": ""},
                    {"room_name": "Mechanical", "heating_btu_hr": 4865, "cooling_btu_hr": None, "sqft": 318, "notes": ""},
                ],
            },
            {
                "zone_name": "First story",
                "heating_btu_hr": 22320,
                "cooling_btu_hr": None,
                "rooms": [
                    {"room_name": "Kitchen",     "heating_btu_hr": 3367, "cooling_btu_hr": None, "sqft": 190, "notes": ""},
                    {"room_name": "Den",         "heating_btu_hr": 5332, "cooling_btu_hr": None, "sqft": 145, "notes": ""},
                    {"room_name": "Bathroom",    "heating_btu_hr":  785, "cooling_btu_hr": None, "sqft":  28, "notes": ""},
                    {"room_name": "Living Room", "heating_btu_hr": 5087, "cooling_btu_hr": None, "sqft": 238, "notes": ""},
                    {"room_name": "Dining Room", "heating_btu_hr": 6461, "cooling_btu_hr": None, "sqft": 241, "notes": ""},
                    {"room_name": "Hallway",     "heating_btu_hr":    0, "cooling_btu_hr": None, "sqft":  46, "notes": ""},
                ],
            },
            {
                "zone_name": "Second story",
                "heating_btu_hr": 16704,
                "cooling_btu_hr": None,
                "rooms": [
                    {"room_name": "Hallway",    "heating_btu_hr": 1255, "cooling_btu_hr": None, "sqft": 114, "notes": ""},
                    {"room_name": "Primary",    "heating_btu_hr": 5747, "cooling_btu_hr": None, "sqft": 243, "notes": ""},
                    {"room_name": "Bathroom",   "heating_btu_hr": 1912, "cooling_btu_hr": None, "sqft":  58, "notes": ""},
                    {"room_name": "Bathroom 2", "heating_btu_hr": 1453, "cooling_btu_hr": None, "sqft":  41, "notes": ""},
                    {"room_name": "Office",     "heating_btu_hr": 3339, "cooling_btu_hr": None, "sqft": 129, "notes": ""},
                    {"room_name": "Bedroom",    "heating_btu_hr": 3563, "cooling_btu_hr": None, "sqft": 157, "notes": ""},
                ],
            },
        ],

        "assumptions": [],
        "warnings": [],
        "confidence": 1.0,

        # Helpful meta for debugging + future expansion
        "metadata": {
            "source": "default_stub",
            "notes": "Stub loads object used when generator integration is not yet connected.",
            "version": "1.0",
        },
    }

    # ---- Derived “robustness” helpers ----
    # 1) Add stable IDs + compute sqft totals by zone, and overall room sqft
    total_room_sqft = 0
    for zi, z in enumerate(loads["zones"], start=1):
        z.setdefault("zone_id", f"Z{zi:02d}")
        z_sqft = 0
        for ri, r in enumerate(z.get("rooms") or [], start=1):
            r.setdefault("room_id", f"{z['zone_id']}-R{ri:02d}")
            r_sqft = r.get("sqft") or 0
            z_sqft += r_sqft
        z["zone_sqft"] = z_sqft
        total_room_sqft += z_sqft

    loads["derived"] = {
        "total_room_sqft": total_room_sqft,
        "total_area_sqft": loads["project"].get("total_area_sqft"),
        "heating_btu_hr": loads["whole_unit"].get("heating_btu_hr"),
        "cooling_btu_hr": loads["whole_unit"].get("cooling_btu_hr"),
        "notes": [
            "Room cooling loads were not provided; cooling_btu_hr left as None at room/zone level.",
            "Zone heating totals may not equal sum(room heating) in this stub; treat room loads as primary if mismatched.",
        ],
    }

    return loads

def build_room_catalog(loads: dict) -> dict:
    items = []
    for z in loads.get("zones", []):
        zone = z.get("zone_name", "Zone")
        for r in z.get("rooms", []):
            # If you already added room_id/zone_id in default_loads(), use those.
            rid = r.get("room_id") or f"{zone}::{r.get('room_name','Room')}"
            items.append({
                "id": rid,
                "label": f"{zone} • {r.get('room_name','Room')}",
                "zone": zone,
                "room": r.get("room_name", "Room"),
                "sqft": r.get("sqft"),
                "heating_btu_hr": r.get("heating_btu_hr"),
            })
    return {
        "catalog_version": "1.0",
        "scope": "rooms",
        "items": items,
        "whole_unit_option": {"id": "WHOLE", "label": "Entire Unit"},
    }

@router.get("/ai/catalog")
def ai_catalog():
    loads = default_loads()
    print("Generated room catalog from loads:", loads)
    return build_room_catalog(loads)

def filter_loads_by_selection(loads: dict, selected_ids: list[str]) -> dict:
    if not selected_ids or "WHOLE" in selected_ids:
        return loads  # whole-unit sizing

    selected = set(selected_ids)
    filtered_zones = []
    total_heat = 0
    total_sqft = 0

    for z in loads.get("zones", []):
        zone_rooms = []
        for r in z.get("rooms", []):
            rid = r.get("room_id") or f"{z.get('zone_name')}::{r.get('room_name')}"
            if rid in selected:
                zone_rooms.append(r)
                total_heat += (r.get("heating_btu_hr") or 0)
                total_sqft += (r.get("sqft") or 0)

        if zone_rooms:
            filtered_zones.append({
                **z,
                "rooms": zone_rooms,
                "heating_btu_hr": sum((rr.get("heating_btu_hr") or 0) for rr in zone_rooms),
            })

    # Return a trimmed “robust” object that matches the chosen rooms
    return {
        **loads,
        "zones": filtered_zones,
        "whole_unit": {
            **loads.get("whole_unit", {}),
            "heating_btu_hr": total_heat,
            # cooling could remain whole-unit, or you can allocate later
        },
        "derived": {
            **loads.get("derived", {}),
            "selected_room_count": len(selected),
            "selected_sqft": total_sqft,
            "selected_heating_btu_hr": total_heat,
        }
    }
#######################################################################################################

def normalize_intent_model(m: str | None) -> str:
    if not m:
        return "gpt-5.2"
    m = m.strip()
    if m.lower() in {"string", "default", "none", "null"}:
        return "gpt-5.2"
    return m

def reqs_from_loads(loads: dict, selected_ids: list[str] | None, head_count: int) -> tuple[list[float], float]:
    """
    Returns (reqs, required_total).
    - If selected_ids includes 'whole_unit' or is empty -> split whole-unit heat evenly across head_count
    - Else -> reqs are the selected rooms' heating loads
    """
    selected_ids = selected_ids or ["whole_unit"]
    head_count = max(int(head_count or 1), 1)

    # Whole unit
    if "whole_unit" in selected_ids:
        total = (loads.get("whole_unit") or {}).get("heating_btu_hr")
        total = float(total) if total is not None else 0.0
        per = total / head_count
        return [per] * head_count, total

    # Rooms
    room_map = {}
    for z in (loads.get("zones") or []):
        zn = z.get("zone_name") or "Zone"
        for r in (z.get("rooms") or []):
            rn = r.get("room_name") or "Room"
            rid = f"{zn}::{rn}"
            room_map[rid] = float(r.get("heating_btu_hr") or 0)

    reqs = []
    total = 0.0
    for rid in selected_ids:
        heat = room_map.get(rid, 0.0)
        if heat > 0:
            reqs.append(heat)
            total += heat

    # Fallback if user selected nothing valid
    if not reqs:
        total2 = float((loads.get("whole_unit") or {}).get("heating_btu_hr") or 0.0)
        per = total2 / head_count
        return [per] * head_count, total2

    return reqs, total

# adding in logic for AI agent to recommend ASHP system design
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class RecommendReq(BaseModel):
    user_text: str
    selected_ids: list[str] | None = None #= Field(default_factory=lambda: ["whole_unit"])
    intent_model: str | None = None
    chat_history: list[ChatTurn] = Field(default_factory=list)

def build_intent_transcript(chat_history: list[ChatTurn], latest_user_text: str) -> str:
    parts: list[str] = []

    for msg in chat_history:
        text = (msg.content or "").strip()
        if not text:
            continue

        if msg.role == "user":
            parts.append(f"User: {text}")
        else:
            parts.append(f"Assistant: {text}")

    latest = (latest_user_text or "").strip()
    if latest:
        if not parts or parts[-1] != f"User: {latest}":
            parts.append(f"User: {latest}")

    return "\n".join(parts)

@router.post("/ai/recommend")
def ai_recommend(req: RecommendReq):

    try:
        loads = default_loads()

        building_summary = build_building_summary(loads)

        transcript = build_intent_transcript(req.chat_history, req.user_text)
        print("AI RECOMMEND - building summary:", building_summary)

        intent = get_intent(
            building_summary=building_summary,
            user_text=transcript,
            model=normalize_intent_model(req.intent_model),
        )

        # confirm with user about room selection
        intent = post_validate_intent(intent, building_summary, transcript)

        rec = recommend_from_intent(intent, building_summary)

        print("REC AFTER recommend_from_intent:", rec)
        print("REC WARNINGS:", rec.get("warnings", []))

        # ✅ Enrich each draft by calling the SAME deterministic engine as /api/run
        for d in rec.get("drafts", []):
            head_count = d.get("indoor_head_count") or 1
            distribution = d.get("distribution") or "ductless"
            type_filter = "Non-ducted" if distribution == "ductless" else "Ducted"

            selected_rooms = d.get("selected_rooms") or []
            room_load_lookup = d.get("room_load_lookup") or {}
            margin_pct = float(d.get("margin_pct") or 0.15)

            # Build reqs from AI-selected rooms if available
            if selected_rooms:
                room_loads = []
                for zone_name, room_name in selected_rooms:
                    key = f"{zone_name}||{room_name}"
                    btu = room_load_lookup.get(key)
                    if isinstance(btu, (int, float)):
                        room_loads.append(float(btu) * (1 + margin_pct))

                # sort biggest-to-smallest and round up
                room_loads = sorted(room_loads, reverse=True)

                # if user asked for more heads than selected rooms, keep only available room loads
                reqs = [math.ceil(r / 1000) * 1000 for r in room_loads[:head_count]]

                required_total = sum(reqs)
            else:
                # fallback only if no room scope could be resolved
                selected_ids = req.selected_ids or ["whole_unit"]
                reqs, required_total = reqs_from_loads(loads, selected_ids, head_count=head_count)
                reqs = [math.ceil(r / 1000) * 1000 for r in reqs]
                required_total = sum(reqs)

            d["required_heat_btu_hr"] = required_total
            d["reqs"] = reqs

            manufacturer = "Fujitsu"

            print("AI DRAFT BEFORE ENGINE:", d)
            print("HEAD COUNT:", head_count)
            print("DISTRIBUTION:", distribution)
            print("TYPE FILTER:", type_filter)
            print("REQS SENT TO ENGINE:", reqs)
            print("REQUIRED TOTAL:", required_total)

            engine = run_logic(
                manufacturer=manufacturer,
                reqs=reqs,
                type_filter=type_filter,
                max_results=300,
            )
            
            print("ENGINE RAW RESULT:", engine)
            logging.info("ENGINE RESULT COUNT: %s", len(engine.get("results", [])))

            d["candidates"] = engine.get("results", [])

            print(f"Enriched draft with deterministic engine results:\nIntent: {intent}\nDraft: {d}")

            print(">>> HIT /api/ai/recommend <<<")

        return {"intent": intent, "rec": rec}

        # print(f"Detected variables for AI recommendation:\nIntent: {intent}\nBuilding Summary: {building_summary}")
        # rec = recommend_from_intent(intent, building_summary)
        # return {"intent": intent, "rec": rec}

    except Exception as e:
        print("AI RECOMMEND ERROR:", repr(e))
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ai/catalog")
def ai_catalog():
    loads = default_loads()
    print("Generated room catalog from loads:", loads)
    return build_room_catalog(loads)   # items + whole_unit_option
