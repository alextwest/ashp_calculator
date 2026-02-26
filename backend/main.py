import traceback

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import Request
from pathlib import Path
from fastapi import HTTPException

# for ai agent 
from pydantic import BaseModel
from ai_agent_system_design import get_intent, recommend_from_intent

from api.routes import router as api_router

import logging, sys

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logging.info("🔄 load_combos called")

## Defining paths for static mounting at the end
DIST_DIR = Path(__file__).resolve().parent / "frontend_dist"
STATIC_DIR = DIST_DIR / "static"
INDEX_HTML = DIST_DIR / "index.html"

app = FastAPI()
app.include_router(api_router)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten later to your SWA/App domain(s)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("hello from request", flush=True)

@app.get("/api/_debug/routes")
def debug_routes():
    out = []
    for r in app.routes:
        methods = sorted(getattr(r, "methods", []) or [])
        path = getattr(r, "path", "")
        out.append({"path": path, "methods": methods})
    return out

@app.options("/{rest_of_path:path}")
def options_passthrough(rest_of_path: str, request: Request):
    # If you ever see this hit, you know OPTIONS is reaching FastAPI.
    return {}

########################################################################################################
# TEMPORARY ROOM JSON INPUT FOR TESTING
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

# adding in logic for AI agent to recommend ASHP system design
class RecommendReq(BaseModel):
    user_text: str
    selected_ids: list[str] = ["whole_unit"]
    intent_model: str | None = None

@app.post("/api/ai/recommend")
def ai_recommend(req: RecommendReq):

    try:
        # normalize selection values from UI
        selected = req.selected_ids or ["whole_unit"]
        selected = ["WHOLE" if s in ("whole_unit", "WHOLE") else s for s in selected]

        # loads stub (or real loads later)
        loads = default_loads()

        # build building_summary for your intent + deterministic logic
        building_summary = {
            "loads": loads,
            "text": "stub building summary",
            "selected_ids": selected,
        }

        model_name = normalize_intent_model(req.intent_model)
        intent = get_intent(
            building_summary=building_summary,
            user_text=req.user_text,
            model=model_name,
        )
        rec = recommend_from_intent(intent, building_summary)
        return {"intent": intent, "rec": rec}

    except Exception as e:
        print("AI RECOMMEND ERROR:", repr(e))
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# Only mount the SPA AFTER your API routes, and exclude /api/* from the fallback
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def spa_index():
        if INDEX_HTML.exists():
            return FileResponse(INDEX_HTML)
        raise HTTPException(status_code=404, detail="index.html not found")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # never hijack API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if INDEX_HTML.exists():
            return FileResponse(INDEX_HTML)
        raise HTTPException(status_code=404, detail="index.html not found")