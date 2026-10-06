from __future__ import annotations

import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from . import db
from .models.enums import Courtier
from .models.investment_account import InvestmentAccount
from .routes import (
    agencies,
    attachments,
    bookings,
    cash_holdings,
    dashboard,
    declaration,
    expenses,
    immobilisations,
    indivision,
    securities,
    settings,
    simulator,
    synthese,
)
from .routes import (
    calendar as calendar_routes,
)
from .routes.investments import router_compte as investments_compte_router
from .routes.investments import router_liste as investments_liste_router
from .routes.property import router_fiche as property_fiche_router
from .routes.property import router_liste as property_liste_router
from .services.ibkr_credentials import get_credentials
from .services.ibkr_sync import sync_operations
from .services.market_data import refresh_all_prices

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 8451


def create_app() -> FastAPI:
    app = FastAPI(title="Patrimoine")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(dashboard.router)
    app.include_router(property_liste_router)
    app.include_router(property_fiche_router)
    app.include_router(bookings.router)
    app.include_router(expenses.router)
    app.include_router(immobilisations.router)
    app.include_router(simulator.router)
    app.include_router(indivision.router)
    app.include_router(attachments.router)
    app.include_router(settings.router)
    app.include_router(agencies.router)
    app.include_router(calendar_routes.router)
    app.include_router(synthese.router)
    app.include_router(securities.router)
    app.include_router(investments_liste_router)
    app.include_router(investments_compte_router)
    app.include_router(cash_holdings.router)
    app.include_router(declaration.router)
    return app


app = create_app()


def _find_free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("Aucun port disponible sur 127.0.0.1")


def _open_browser_when_ready(port: int) -> None:
    deadline = time.time() + 10
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                webbrowser.open(f"http://127.0.0.1:{port}")
                return
        time.sleep(0.1)


def _refresh_market_data_at_startup() -> None:
    """Rafraîchit les cours Yahoo Finance et synchronise les opérations IBKR en
    tâche de fond au lancement — ne doit jamais bloquer le démarrage du
    serveur ni faire planter l'app en cas d'échec réseau."""
    try:
        with Session(db.get_engine()) as session:
            refresh_all_prices(session)
            accounts = session.exec(
                select(InvestmentAccount).where(InvestmentAccount.courtier == Courtier.ibkr)
            ).all()
            if accounts:
                creds = get_credentials()
                for account in accounts:
                    sync_operations(session, account, creds)
    except Exception:
        pass


def run() -> None:
    """Point d'entrée `uv run patrimoine` : migre la base, lance le serveur sur
    127.0.0.1 uniquement, ouvre le navigateur automatiquement, et rafraîchit
    les cours/opérations IBKR en tâche de fond."""
    db.run_migrations()
    port = _find_free_port(DEFAULT_PORT)
    threading.Thread(target=_open_browser_when_ready, args=(port,), daemon=True).start()
    threading.Thread(target=_refresh_market_data_at_startup, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run()
