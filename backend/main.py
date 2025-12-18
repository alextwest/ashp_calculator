from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from api.routes import router as api_router

app = FastAPI()
app.include_router(api_router)

# --- Serve React build (after CI builds frontend) ---
# We will copy the built frontend into: backend/frontend_dist/
DIST_DIR = Path(__file__).resolve().parent / "frontend_dist"

if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="static")

    # SPA fallback (React Router safe)
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        return FileResponse(DIST_DIR / "index.html")
