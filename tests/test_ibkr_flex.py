from datetime import date
from unittest.mock import patch

import httpx

from patrimoine.models.enums import TypeTransaction
from patrimoine.services import ibkr_flex

SEND_SUCCESS = """<FlexStatementResponse timestamp='04 October, 2026 04:03 PM EDT'>
<Status>Success</Status>
<ReferenceCode>8936364590</ReferenceCode>
<Url>https://gdcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement</Url>
</FlexStatementResponse>"""

SEND_FAILURE = """<FlexStatementResponse timestamp='04 October, 2026 04:03 PM EDT'>
<Status>Fail</Status>
<ErrorCode>1003</ErrorCode>
<ErrorMessage>Invalid token</ErrorMessage>
</FlexStatementResponse>"""

GET_IN_PROGRESS = "<FlexStatementResponse><Status>Fail</Status><ErrorCode>1019</ErrorCode><ErrorMessage>Statement generation in progress. Please try again shortly.</ErrorMessage></FlexStatementResponse>"

REPORT_XML = """<FlexQueryResponse queryName="Test" type="AF">
<FlexStatements count="1">
<FlexStatement accountId="U21547209" fromDate="20260804" toDate="20261002" period="LastNCalendarDays" whenGenerated="20261004;160357">
<OpenPositions>
<OpenPosition accountId="U21547209" conid="314449552" isin="LU1681045370" symbol="AEEM" position="2275.6925" costBasisPrice="6.5946957" currency="EUR" />
<OpenPosition accountId="U21547209" conid="678102082" isin="IE000BI8OT95" symbol="MWRD" position="887.529" costBasisPrice="143.951223014" currency="EUR" />
</OpenPositions>
<Trades>
<Trade accountId="U21547209" transactionID="999111" conid="314449552" isin="LU1681045370" symbol="AEEM" quantity="10" tradePrice="7.5" currency="EUR" ibCommission="1.5" dateTime="10/03/2026;120000" />
<Trade accountId="U21547209" transactionID="999112" conid="314449552" isin="LU1681045370" symbol="AEEM" quantity="-5" tradePrice="8.0" currency="EUR" ibCommission="1.0" dateTime="10/04/2026;120000" />
</Trades>
<CashTransactions>
<CashTransaction accountId="U21547209" transactionID="3421738741" type="Broker Interest Received" amount="8.55" currency="EUR" dateTime="08/05/2026" description="EUR IBKR INTEREST FOR JUL-2026" />
<CashTransaction accountId="U21547209" transactionID="3421738742" type="Deposits/Withdrawals" amount="1000" currency="EUR" dateTime="08/06/2026" description="DEPOSIT" />
<CashTransaction accountId="U21547209" transactionID="3421738743" type="Deposits/Withdrawals" amount="-200" currency="EUR" dateTime="08/07/2026" description="WITHDRAWAL" />
<CashTransaction accountId="U21547209" transactionID="3421738744" type="Dividends" amount="12.3" currency="EUR" dateTime="08/08/2026" description="DIV" />
<CashTransaction accountId="U21547209" transactionID="3421738745" type="Withholding Tax" amount="-1.8" currency="EUR" dateTime="08/08/2026" description="TAX" />
<CashTransaction accountId="U21547209" transactionID="3421738746" type="Some Unknown Type" amount="42" currency="EUR" dateTime="08/09/2026" description="MYSTERE" />
</CashTransactions>
</FlexStatement>
</FlexStatements>
</FlexQueryResponse>"""


def _response(text, status_code=200):
    request = httpx.Request("GET", "https://ndcdyn.interactivebrokers.com/x")
    return httpx.Response(status_code, text=text, request=request)


def test_fetch_report_succes_premiere_tentative():
    with patch("patrimoine.services.ibkr_flex.httpx.get") as mock_get:
        mock_get.side_effect = [_response(SEND_SUCCESS), _response(REPORT_XML)]
        with patch("patrimoine.services.ibkr_flex.time.sleep"):
            result = ibkr_flex.fetch_report("token", "123")
    assert "<FlexQueryResponse" in result
    # Deuxieme appel doit utiliser l'Url renvoyee par SendRequest (gdcdyn), pas celle en dur.
    second_call_url = mock_get.call_args_list[1].args[0]
    assert "gdcdyn" in second_call_url


def test_fetch_report_statement_en_cours_puis_succes():
    with patch("patrimoine.services.ibkr_flex.httpx.get") as mock_get:
        mock_get.side_effect = [_response(SEND_SUCCESS), _response(GET_IN_PROGRESS), _response(REPORT_XML)]
        with patch("patrimoine.services.ibkr_flex.time.sleep"):
            result = ibkr_flex.fetch_report("token", "123")
    assert "<FlexQueryResponse" in result


def test_fetch_report_echec_send_request():
    with patch("patrimoine.services.ibkr_flex.httpx.get", return_value=_response(SEND_FAILURE)):
        try:
            ibkr_flex.fetch_report("token", "123")
            raise AssertionError("devrait lever IbkrFlexError")
        except ibkr_flex.IbkrFlexError as exc:
            assert "1003" in str(exc)


def test_fetch_report_abandon_apres_trop_de_tentatives():
    with patch("patrimoine.services.ibkr_flex.httpx.get") as mock_get:
        mock_get.side_effect = [_response(SEND_SUCCESS)] + [
            _response(GET_IN_PROGRESS) for _ in range(ibkr_flex.MAX_POLL_ATTEMPTS)
        ]
        with patch("patrimoine.services.ibkr_flex.time.sleep"):
            try:
                ibkr_flex.fetch_report("token", "123")
                raise AssertionError("devrait lever IbkrFlexError")
            except ibkr_flex.IbkrFlexError as exc:
                assert "temps" in str(exc)


def test_fetch_report_erreur_reseau():
    with patch("patrimoine.services.ibkr_flex.httpx.get", side_effect=httpx.ConnectError("offline")):
        try:
            ibkr_flex.fetch_report("token", "123")
            raise AssertionError("devrait lever IbkrFlexError")
        except ibkr_flex.IbkrFlexError:
            pass


def test_parse_open_positions():
    positions = ibkr_flex.parse_open_positions(REPORT_XML)
    assert len(positions) == 2
    aeem = positions[0]
    assert aeem.conid == "314449552"
    assert aeem.isin == "LU1681045370"
    assert aeem.quantite == 2275.6925
    assert aeem.prix_moyen == 6.5946957
    assert aeem.devise == "EUR"


def test_parse_trades():
    trades = ibkr_flex.parse_trades(REPORT_XML)
    assert len(trades) == 2
    achat = trades[0]
    assert achat.achat is True
    assert achat.quantite == 10
    assert achat.frais == 1.5
    assert achat.date == date(2026, 10, 3)

    vente = trades[1]
    assert vente.achat is False
    assert vente.quantite == 5  # valeur absolue, le signe ne sert qu'a determiner achat/vente


def test_parse_cash_transactions():
    transactions = ibkr_flex.parse_cash_transactions(REPORT_XML)
    assert len(transactions) == 6
    interet = transactions[0]
    assert interet.transaction_id == "3421738741"
    assert interet.type_brut == "Broker Interest Received"
    assert interet.montant == 8.55
    assert interet.date == date(2026, 8, 5)


def test_map_cash_transaction_type_depot_retrait():
    assert ibkr_flex.map_cash_transaction_type("Deposits/Withdrawals", 1000) == TypeTransaction.depot
    assert ibkr_flex.map_cash_transaction_type("Deposits/Withdrawals", -200) == TypeTransaction.retrait


def test_map_cash_transaction_type_dividende_frais_interet():
    assert ibkr_flex.map_cash_transaction_type("Dividends", 12.3) == TypeTransaction.dividende
    assert ibkr_flex.map_cash_transaction_type("Withholding Tax", -1.8) == TypeTransaction.frais
    assert ibkr_flex.map_cash_transaction_type("Broker Interest Received", 8.55) == TypeTransaction.interet


def test_map_cash_transaction_type_inconnu_retourne_none():
    assert ibkr_flex.map_cash_transaction_type("Some Unknown Type", 42) is None
