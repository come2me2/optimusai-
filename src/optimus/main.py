from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from optimus.agent.loop import AgentLoop
from optimus.metrics.calculator import compute_kpis
from optimus.metrics.store import MetricsStore, DEFAULT_DB_PATH

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


class CreateCampaignRequest(BaseModel):
    name: str = "Тест CPA"
    daily_budget: float = 5000.0
    target_cpa: float = 800.0
    current_bid: float = 50.0


class UpdateTargetCpaRequest(BaseModel):
    target_cpa: float


class RunTicksRequest(BaseModel):
    ticks: int = 1


def create_app(db_path: Optional[Path] = None) -> FastAPI:
    store = MetricsStore(db_path=db_path or DEFAULT_DB_PATH)
    loop = AgentLoop(store=store)

    app = FastAPI(title="Optimus AI", version="0.1.0")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def dashboard():
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"message": "Optimus AI API — static dashboard not found"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/campaigns")
    async def list_campaigns():
        campaigns = store.list_campaigns()
        return [c.model_dump() for c in campaigns]

    @app.post("/campaigns")
    async def create_campaign(req: CreateCampaignRequest):
        campaign = store.create_campaign(
            name=req.name,
            daily_budget=req.daily_budget,
            target_cpa=req.target_cpa,
            current_bid=req.current_bid,
        )
        return campaign.model_dump()

    @app.get("/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str):
        campaign = store.get_campaign(campaign_id)
        if not campaign:
            raise HTTPException(404, "Campaign not found")
        cumulative = store.get_cumulative_metrics(campaign_id)
        kpis = compute_kpis(cumulative)
        return {
            "campaign": campaign.model_dump(),
            "tick": store.get_tick(campaign_id),
            "cumulative_metrics": cumulative.model_dump(),
            "kpis": kpis.model_dump(),
        }

    @app.patch("/campaigns/{campaign_id}/target-cpa")
    async def update_target_cpa(campaign_id: str, req: UpdateTargetCpaRequest):
        campaign = store.get_campaign(campaign_id)
        if not campaign:
            raise HTTPException(404, "Campaign not found")
        store.update_target_cpa(campaign_id, req.target_cpa)
        return {"target_cpa": req.target_cpa}

    @app.post("/campaigns/{campaign_id}/reset")
    async def reset_campaign(campaign_id: str):
        campaign = store.get_campaign(campaign_id)
        if not campaign:
            raise HTTPException(404, "Campaign not found")
        store.reset_campaign_data(campaign_id)
        loop.reset_adapter(campaign)
        return {"status": "reset"}

    @app.post("/agent/tick")
    async def agent_tick(campaign_id: Optional[str] = None):
        campaign = (
            store.get_campaign(campaign_id)
            if campaign_id
            else store.get_active_campaign()
        )
        if not campaign:
            raise HTTPException(404, "No campaign found")
        return loop.tick(campaign.id)

    @app.post("/agent/run")
    async def agent_run(req: RunTicksRequest, campaign_id: Optional[str] = None):
        campaign = (
            store.get_campaign(campaign_id)
            if campaign_id
            else store.get_active_campaign()
        )
        if not campaign:
            raise HTTPException(404, "No campaign found")
        results = loop.run(campaign.id, ticks=req.ticks)
        return {"results": results, "count": len(results)}

    @app.get("/metrics/{campaign_id}")
    async def get_metrics(campaign_id: str, limit: int = 100):
        snapshots = store.get_snapshots(campaign_id, limit=limit)
        return [s.model_dump() for s in snapshots]

    @app.get("/decisions/{campaign_id}")
    async def get_decisions(campaign_id: str, limit: int = 50):
        decisions = store.get_decisions(campaign_id, limit=limit)
        return [d.model_dump() for d in decisions]

    return app
