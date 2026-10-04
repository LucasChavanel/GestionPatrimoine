from __future__ import annotations

import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .routes import (
    agencies,
    attachments,
    bookings,
    dashboard,
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


def run() -> None:
    """Point d'entrée `uv run patrimoine` : migre la base, lance le serveur sur
    127.0.0.1 uniquement, et ouvre le navigateur automatiquement."""
    db.run_migrations()
    port = _find_free_port(DEFAULT_PORT)
    threading.Thread(target=_open_browser_when_ready, args=(port,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run()
