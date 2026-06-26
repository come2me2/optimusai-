from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from optimus.agent.loop import AgentLoop
from optimus.metrics.calculator import compute_kpis
from optimus.metrics.store import MetricsStore, DEFAULT_DB_PATH

app = typer.Typer(help="Optimus AI — self-optimizing ad agent")
console = Console()


def _get_store(db: Optional[Path]) -> MetricsStore:
    return MetricsStore(db_path=db or DEFAULT_DB_PATH)


@app.command()
def init(
    name: str = typer.Option("Тест CPA", "--name", "-n"),
    budget: float = typer.Option(5000.0, "--budget", "-b"),
    target_cpa: float = typer.Option(800.0, "--target-cpa", "-t"),
    bid: float = typer.Option(50.0, "--bid"),
    db: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    """Create a new mock campaign."""
    store = _get_store(db)
    campaign = store.create_campaign(
        name=name,
        daily_budget=budget,
        target_cpa=target_cpa,
        current_bid=bid,
    )
    console.print(f"[green]Campaign created[/green] id={campaign.id}")
    console.print(f"  name={campaign.name} budget={campaign.daily_budget} target_cpa={campaign.target_cpa}")


@app.command()
def run(
    ticks: int = typer.Option(24, "--ticks", "-t"),
    campaign_id: Optional[str] = typer.Option(None, "--campaign", "-c"),
    db: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    """Run agent optimization loop for N simulated hours."""
    store = _get_store(db)
    campaign = store.get_campaign(campaign_id) if campaign_id else store.get_active_campaign()
    if not campaign:
        console.print("[red]No campaign found. Run: optimus init[/red]")
        raise typer.Exit(1)

    loop = AgentLoop(store=store)
    console.print(f"Running {ticks} ticks for campaign [bold]{campaign.name}[/bold]...")

    for i, result in enumerate(loop.run(campaign.id, ticks=ticks), 1):
        d = result["decision"]
        kpis = result["window_kpis"]
        cpa = kpis.get("cpa", 0)
        console.print(
            f"  tick {result['tick']:3d} | "
            f"imp={result['period_metrics']['impressions']:4d} "
            f"clk={result['period_metrics']['clicks']:3d} "
            f"conv={result['period_metrics']['conversions']:2d} "
            f"CPA={cpa:6.0f} bid={result['bid']:.1f} | "
            f"{d['action']}: {d['reason'][:60]}"
        )

    console.print("[green]Done.[/green] Run [bold]optimus status[/bold] or [bold]optimus serve[/bold]")


@app.command()
def status(
    campaign_id: Optional[str] = typer.Option(None, "--campaign", "-c"),
    db: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    """Show campaign KPIs and recent decisions."""
    store = _get_store(db)
    campaign = store.get_campaign(campaign_id) if campaign_id else store.get_active_campaign()
    if not campaign:
        console.print("[red]No campaign found.[/red]")
        raise typer.Exit(1)

    cumulative = store.get_cumulative_metrics(campaign.id)
    kpis = compute_kpis(cumulative)
    tick = store.get_tick(campaign.id)

    console.print(f"\n[bold]{campaign.name}[/bold] (tick={tick}, bid={campaign.current_bid})")
    console.print(f"  Impressions: {cumulative.impressions:,}")
    console.print(f"  Clicks:      {cumulative.clicks:,}")
    console.print(f"  Conversions: {cumulative.conversions:,}")
    console.print(f"  Spend:       {cumulative.spend:,.0f} ₽")
    console.print(f"  CTR: {kpis.ctr:.2%}  CPC: {kpis.cpc:.0f}  CR: {kpis.cr:.2%}  CPA: {kpis.cpa:.0f}  ROAS: {kpis.roas:.2f}")

    decisions = store.get_decisions(campaign.id, limit=5)
    if decisions:
        table = Table(title="Recent decisions")
        table.add_column("Tick")
        table.add_column("Action")
        table.add_column("Bid")
        table.add_column("Reason")
        for d in decisions:
            table.add_row(str(d.tick), d.action.value, f"{d.new_bid:.1f}", d.reason[:70])
        console.print(table)


@app.command()
def reset(
    campaign_id: Optional[str] = typer.Option(None, "--campaign", "-c"),
    db: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    """Reset metrics and restart simulation."""
    store = _get_store(db)
    campaign = store.get_campaign(campaign_id) if campaign_id else store.get_active_campaign()
    if not campaign:
        console.print("[red]No campaign found.[/red]")
        raise typer.Exit(1)

    store.reset_campaign_data(campaign.id)
    loop = AgentLoop(store=store)
    loop.reset_adapter(campaign)
    console.print(f"[yellow]Reset campaign {campaign.name}[/yellow]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    db: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    """Start API server and web dashboard."""
    import uvicorn

    from optimus.main import create_app

    app_instance = create_app(db_path=db)
    console.print(f"[green]Dashboard:[/green] http://{host}:{port}")
    uvicorn.run(app_instance, host=host, port=port)


if __name__ == "__main__":
    app()
