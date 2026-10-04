"""Stockage des identifiants IBKR Flex Web Service dans le Trousseau (keyring) —
jamais en base ni dans le repo. Pas d'appel à l'API IBKR ici : sauvegarde et
lecture seulement, en attendant que l'utilisateur obtienne un token et un
Query ID réels."""

from __future__ import annotations

from dataclasses import dataclass

import keyring

SERVICE_NAME = "patrimoine"
TOKEN_KEY = "ibkr_token"
QUERY_ID_KEY = "ibkr_query_id"


@dataclass
class IbkrCredentials:
    token: str | None
    query_id: str | None


def get_credentials() -> IbkrCredentials:
    return IbkrCredentials(
        token=keyring.get_password(SERVICE_NAME, TOKEN_KEY),
        query_id=keyring.get_password(SERVICE_NAME, QUERY_ID_KEY),
    )


def save_credentials(token: str | None, query_id: str | None) -> None:
    if token:
        keyring.set_password(SERVICE_NAME, TOKEN_KEY, token)
    if query_id:
        keyring.set_password(SERVICE_NAME, QUERY_ID_KEY, query_id)
