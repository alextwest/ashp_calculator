from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

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

app = FastAPI()
app.include_router(api_router)

print("hello from request", flush=True)

# --- Serve React build (after CI builds frontend) ---
# We will copy the built frontend into: backend/frontend_dist/
DIST_DIR = Path(__file__).resolve().parent / "frontend_dist"

if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="static")

    # SPA fallback (React Router safe)
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        return FileResponse(DIST_DIR / "index.html")

# adding in logic for AI agent to recommend ASHP system design
class RecommendReq(BaseModel):
    building_summary: dict
    user_text: str
    intent_model: str | None = None

@app.post("/api/ai/recommend")
def ai_recommend(req: RecommendReq):
    intent = get_intent(
        building_summary=req.building_summary,
        user_text=req.user_text,
        model=req.intent_model or "gpt-5.2",
    )
    rec = recommend_from_intent(intent, req.building_summary)
    return {"intent": intent, "rec": rec}