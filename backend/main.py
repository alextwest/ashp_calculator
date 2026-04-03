import logging
import sys
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router

# -----------------------------------------------------------------------------
# Logging (stdout -> picked up by App Service + can flow to App Insights)
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ashp-backend")


logging.getLogger("ashp").info("Python executable: %s", sys.executable)
logging.getLogger("ashp").info("Current working dir: %s", os.getcwd())

try:
    import uvicorn
    logging.getLogger("ashp").info("uvicorn import OK: %s", uvicorn.__version__)
except Exception:
    logging.getLogger("ashp").exception("uvicorn import failed")

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IMPORTANT: routers do NOT include "/api" internally in this cleaned setup.
app.include_router(api_router, prefix="/api", tags=["api"])

ENABLE_AI = os.getenv("ENABLE_AI", "0").lower() in ("1", "true", "yes")

if ENABLE_AI:
    try:
        from api.ai_routes import router as ai_router
        app.include_router(ai_router, prefix="/api", tags=["ai"])
        logging.getLogger("ashp").info("✅ AI routes enabled")
    except Exception:
        logging.getLogger("ashp").exception("❌ Failed to enable AI routes")
else:
    logging.getLogger("ashp").info("ℹ️ AI routes disabled")

# -----------------------------------------------------------------------------
# Debug helpers
# -----------------------------------------------------------------------------
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
    return {}


# -----------------------------------------------------------------------------
# Optional: serve SPA build (frontend_dist) if present
# -----------------------------------------------------------------------------
DIST_DIR = Path(__file__).resolve().parent / "frontend_dist"
INDEX_HTML = DIST_DIR / "index.html"
ASSETS_DIR = DIST_DIR / "assets"

if ASSETS_DIR.exists() and INDEX_HTML.exists():
    logger.info("✅ Serving frontend_dist SPA")
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

    @app.get("/")
    def spa_index():
        return FileResponse(INDEX_HTML)

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request):
        # don't swallow API routes
        if full_path.startswith("api/"):
            return RedirectResponse("/docs")
        return FileResponse(INDEX_HTML)
else:
    logger.info("ℹ️ frontend_dist not found; API-only mode")

    @app.get("/")
    def home():
        return RedirectResponse("/docs")
    
@app.get("/api/_debug/features")
def debug_features():
    return {"enable_ai": ENABLE_AI}