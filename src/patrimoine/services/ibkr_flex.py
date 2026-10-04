"""Récupération et parsing du rapport Flex Web Service IBKR (v3).

Protocole : SendRequest déclenche la génération du rapport côté IBKR et
renvoie un ReferenceCode + une Url (variable selon la session, ndcdyn/gdcdyn —
on l'utilise telle que renvoyée plutôt qu'en dur) ; GetStatement est ensuite
interrogé (polling) jusqu'à obtenir le rapport ou dépasser le nombre de
tentatives — la génération est asynchrone côté IBKR (ErrorCode 1019 =
"en cours", il faut réessayer sans renvoyer de nouvelle requête).

Ce module ne lève que `IbkrFlexError` vers l'appelant (jamais une exception
réseau brute) — à charge de la route d'afficher un message clair.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from ..models.enums import TypeTransaction

SEND_REQUEST_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
DEFAULT_GET_STATEMENT_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
MAX_POLL_ATTEMPTS = 6
POLL_INTERVAL_SECONDS = 5.0
TIMEOUT_SECONDS = 30.0


class IbkrFlexError(Exception):
    """Erreur métier lors de la récupération du rapport Flex — message déjà
    adapté à l'affichage utilisateur."""


def fetch_report(token: str, query_id: str) -> str:
    try:
        send_response = httpx.get(
            SEND_REQUEST_URL, params={"t": token, "q": query_id, "v": 3}, timeout=TIMEOUT_SECONDS
        )
        send_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise IbkrFlexError(f"Impossible de contacter IBKR (SendRequest) : {exc}") from exc

    try:
        send_root = ET.fromstring(send_response.text)
    except ET.ParseError as exc:
        raise IbkrFlexError("Réponse IBKR illisible (SendRequest).") from exc

    status = send_root.findtext("Status")
    if status != "Success":
        code = send_root.findtext("ErrorCode") or "?"
        message = send_root.findtext("ErrorMessage") or send_response.text[:300]
        raise IbkrFlexError(f"IBKR a refusé la requête (code {code}) : {message}")

    reference_code = send_root.findtext("ReferenceCode")
    if not reference_code:
        raise IbkrFlexError("Réponse IBKR sans ReferenceCode (SendRequest).")
    get_statement_url = send_root.findtext("Url") or DEFAULT_GET_STATEMENT_URL

    for attempt in range(MAX_POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            get_response = httpx.get(
                get_statement_url,
                params={"t": token, "q": reference_code, "v": 3},
                timeout=TIMEOUT_SECONDS,
            )
            get_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise IbkrFlexError(f"Impossible de contacter IBKR (GetStatement) : {exc}") from exc

        text = get_response.text
        if "<FlexQueryResponse" in text or "<FlexStatements" in text:
            return text

        try:
            error_root = ET.fromstring(text)
            error_code = error_root.findtext("ErrorCode")
        except ET.ParseError:
            error_code = None

        if error_code == "1019":
            continue
        if error_code:
            message = error_root.findtext("ErrorMessage") or text[:300]
            raise IbkrFlexError(f"IBKR a renvoyé une erreur (code {error_code}) : {message}")
        # Réponse inattendue mais pas une erreur reconnue : on retente quand même
        # une fois avant d'abandonner, plutôt que d'échouer sur un simple aléa réseau.
        if attempt == MAX_POLL_ATTEMPTS - 1:
            raise IbkrFlexError("Réponse IBKR inattendue (GetStatement), réessayez plus tard.")

    raise IbkrFlexError(
        "Le rapport IBKR n'a pas été généré à temps (statement generation in progress). "
        "Réessayez dans quelques minutes."
    )


@dataclass
class OpenPositionIbkr:
    conid: str
    isin: str
    symbol: str
    quantite: float
    prix_moyen: float
    devise: str


@dataclass
class CashTransactionIbkr:
    transaction_id: str
    type_brut: str
    montant: float
    devise: str
    date: date
    description: str


@dataclass
class TradeIbkr:
    trade_id: str
    conid: str
    isin: str
    symbol: str
    quantite: float
    prix: float
    devise: str
    frais: float
    date: date
    achat: bool


def _parse_ibkr_date(value: str) -> date:
    # Les dates Flex sont au format MM/dd/yyyy ; certains champs datetime
    # incluent une heure séparée par ';' (ex. "10/04/2026;160357") — on ne
    # garde que la partie date.
    value = value.split(";")[0].strip()
    return datetime.strptime(value, "%m/%d/%Y").date()


def parse_open_positions(xml_text: str) -> list[OpenPositionIbkr]:
    root = ET.fromstring(xml_text)
    positions = []
    for el in root.findall(".//OpenPosition"):
        positions.append(
            OpenPositionIbkr(
                conid=el.get("conid", ""),
                isin=el.get("isin", ""),
                symbol=el.get("symbol", ""),
                quantite=float(el.get("position", 0)),
                prix_moyen=float(el.get("costBasisPrice", 0)),
                devise=el.get("currency", "EUR"),
            )
        )
    return positions


# Mapping du type brut IBKR (attribut `type` de <CashTransaction>) vers notre
# TypeTransaction — volontairement explicite et fermé : tout type non listé ici
# est ignoré (jamais mappé par défaut), voir import_cash_transactions.
_CASH_TYPE_DEPOT_RETRAIT = {"Deposits/Withdrawals"}
_CASH_TYPE_DIVIDENDE = {"Dividends", "Payment In Lieu Of Dividends"}
_CASH_TYPE_FRAIS = {"Broker Fees", "Other Fees", "Commission Adjustments"}
_CASH_TYPE_INTERET = {"Broker Interest Received", "Broker Interest Paid"}
_CASH_TYPE_RETENUE_SOURCE = {"Withholding Tax"}


def map_cash_transaction_type(type_brut: str, montant: float) -> TypeTransaction | None:
    """None si le type IBKR n'est pas reconnu — l'appelant doit alors ignorer
    la transaction et le signaler à l'utilisateur, jamais la mapper au hasard.

    `Withholding Tax` a sa propre valeur (`retenue_source`), distincte des frais
    de courtage génériques — nécessaire pour isoler le crédit d'impôt étranger
    (case 8VL) dans le récap de déclaration, voir services/capital_gains.py."""
    if type_brut in _CASH_TYPE_DEPOT_RETRAIT:
        return TypeTransaction.depot if montant > 0 else TypeTransaction.retrait
    if type_brut in _CASH_TYPE_DIVIDENDE:
        return TypeTransaction.dividende
    if type_brut in _CASH_TYPE_FRAIS:
        return TypeTransaction.frais
    if type_brut in _CASH_TYPE_INTERET:
        return TypeTransaction.interet
    if type_brut in _CASH_TYPE_RETENUE_SOURCE:
        return TypeTransaction.retenue_source
    return None


def parse_cash_transactions(xml_text: str) -> list[CashTransactionIbkr]:
    root = ET.fromstring(xml_text)
    transactions = []
    for el in root.findall(".//CashTransaction"):
        transactions.append(
            CashTransactionIbkr(
                transaction_id=el.get("transactionID", ""),
                type_brut=el.get("type", ""),
                montant=float(el.get("amount", 0)),
                devise=el.get("currency", "EUR"),
                date=_parse_ibkr_date(el.get("dateTime", el.get("settleDate", ""))),
                description=el.get("description", ""),
            )
        )
    return transactions


def parse_trades(xml_text: str) -> list[TradeIbkr]:
    root = ET.fromstring(xml_text)
    trades = []
    for el in root.findall(".//Trade"):
        quantite = float(el.get("quantity", 0))
        trades.append(
            TradeIbkr(
                trade_id=el.get("transactionID", el.get("tradeID", "")),
                conid=el.get("conid", ""),
                isin=el.get("isin", ""),
                symbol=el.get("symbol", ""),
                quantite=abs(quantite),
                prix=float(el.get("tradePrice", 0)),
                devise=el.get("currency", "EUR"),
                frais=abs(float(el.get("ibCommission", 0))),
                date=_parse_ibkr_date(el.get("dateTime", el.get("tradeDate", ""))),
                achat=quantite > 0,
            )
        )
    return trades
