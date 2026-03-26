import logging
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ashp_calculator_logic import get_combos_cached, run_logic

logger = logging.getLogger("ashp.routes")

router = APIRouter()

class RunRequest(BaseModel):
    manufacturer: str = Field(..., examples=["Fujitsu"])
    reqs: list[float] = Field(..., description="List of per-head required heating BTU/hr")
    type_filter: str = Field("All", examples=["All", "Non-ducted", "Ducted"])
    max_results: int = Field(300, ge=1, le=5000)

@router.get("/health")
def health():
    return {"ok": True}

@router.post("/run")
def run(req: RunRequest):
    try:
        logger.info("POST /run manufacturer=%s type_filter=%s reqs=%s",
                    req.manufacturer, req.type_filter, req.reqs)

        result = run_logic(
            manufacturer=req.manufacturer,
            reqs=req.reqs,
            type_filter=req.type_filter,
            max_results=req.max_results,
        )
        return {"ok": True, "result": result}
    except Exception as e:
        logger.exception("Error in /run")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/meta")
def meta(manufacturer: str = Query(...)):
    """
    Used by frontend to populate Type dropdown, max heads, etc.
    """
    try:
        logger.info(f"/meta called with manufacturer={manufacturer}")

        allowed = ["Fujitsu", "LG", "All"]
        if manufacturer not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown manufacturer: {manufacturer}"
            )

        manufacturers = ["Fujitsu", "LG"] if manufacturer == "All" else [manufacturer]
        logger.info(f"Resolved manufacturers={manufacturers}")

        dfs = []
        for m in manufacturers:
            logger.info(f"Loading combos for {m}")
            df = get_combos_cached(m)
            logger.info(f"{m} rows={len(df)} cols={list(df.columns)}")
            dfs.append(df)

        combined_df = pd.concat(dfs, ignore_index=True)
        logger.info(f"Combined rows={len(combined_df)}")

        types = sorted(
            set(combined_df["Type"].fillna("").astype(str).str.strip())
        )

        max_heads = max(
            (len(df.attrs.get("UNIT_COLS", [])) for df in dfs),
            default=0
        )

        return {
            "ok": True,
            "manufacturer": manufacturer,
            "max_heads": max_heads,
            "types": ["All"] + [t for t in types if t],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in /meta")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/_debug/df")
def debug_df(
    manufacturer: str = Query(...),
    mode: Literal["head", "full"] = "full",
    max_rows: int = 5000,
):
    """
    Logs/prints the dataframe loaded by load_combos() so you can see it in App Insights.
    - mode=head: logs first max_rows rows
    - mode=full: logs full df (chunked to avoid truncation)
    """
    try:
        df = get_combos_cached(manufacturer)

        if mode == "head":
            df_to_log = df.head(max_rows)
        else:
            df_to_log = df

        # Ensure "full" prints
        pd.set_option("display.max_rows", None)
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 0)
        pd.set_option("display.max_colwidth", None)

        s = df_to_log.to_string(index=False)

        # chunk to reduce truncation in telemetry
        chunk_size = 8000
        for i in range(0, len(s), chunk_size):
            logger.info("DF %s chunk %s:\n%s", manufacturer, (i // chunk_size) + 1, s[i:i+chunk_size])

        return {
            "ok": True,
            "manufacturer": manufacturer,
            "rows": int(df.shape[0]),
            "cols": int(df.shape[1]),
            "columns": list(df.columns),
        }
    except Exception as e:
        logger.exception("Error in /_debug/df")
        raise HTTPException(status_code=500, detail=str(e))