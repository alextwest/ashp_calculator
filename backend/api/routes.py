from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# import your logic
from ashp_calculator_logic import load_combos, run_logic 

router = APIRouter(prefix="/api", tags=["api"])

class RunRequest(BaseModel):
    manufacturer: str
    reqs: list[float]
    type_filter: str = "All"
    max_results: int = 300

@router.get("/health")
def health():
    return {"ok": True}

@router.post("/run")
def run(req: RunRequest):
    try:
        return {"ok": True, "result": run_logic(
            manufacturer=req.manufacturer,
            reqs=req.reqs,
            type_filter=req.type_filter,
            max_results=req.max_results,
        )}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get("/meta")
def meta(manufacturer: str = Query(...)):
    try:
        df = load_combos(manufacturer)
        types = sorted(set(df["Type"].fillna("").astype(str).str.strip()))
        return {
            "ok": True,
            "manufacturer": manufacturer,
            "max_heads": len(df.attrs["UNIT_COLS"]),
            "types": ["All"] + types,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))