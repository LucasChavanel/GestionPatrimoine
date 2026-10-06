from unittest.mock import patch

from sqlmodel import Session

from patrimoine.main import _refresh_market_data_at_startup
from patrimoine.models.enums import Courtier, EnvelopeType
from patrimoine.models.investment_account import InvestmentAccount
from patrimoine.models.security import Security
from patrimoine.services.ibkr_credentials import IbkrCredentials
from patrimoine.services.market_data import PrixRecupere


def test_refresh_market_data_at_startup_met_a_jour_les_cours_et_sync_ibkr(session: Session):
    security = Security(isin="FR1", nom="World", ticker_yahoo="CW8.PA")
    compte_ibkr = InvestmentAccount(nom="CTO IBKR", type=EnvelopeType.cto, courtier=Courtier.ibkr)
    session.add(security)
    session.add(compte_ibkr)
    session.commit()

    with patch(
        "patrimoine.main.get_credentials",
        return_value=IbkrCredentials(token="tok", query_id="123"),
    ):
        with patch(
            "patrimoine.services.market_data.fetch_price",
            return_value=PrixRecupere(prix=10.0, devise="EUR"),
        ):
            with patch("patrimoine.services.ibkr_sync.ibkr_flex.fetch_report", return_value="") as mock_fetch:
                mock_fetch.side_effect = Exception("réseau indisponible dans ce test")
                # Ne doit jamais lever, même si le réseau/parsing IBKR échoue.
                _refresh_market_data_at_startup()

    session.refresh(security)
    assert security.dernier_cours == 10.0


def test_refresh_market_data_at_startup_ne_leve_jamais_sur_erreur_inattendue(session: Session):
    with patch("patrimoine.main.refresh_all_prices", side_effect=RuntimeError("boom")):
        _refresh_market_data_at_startup()  # ne doit pas lever
