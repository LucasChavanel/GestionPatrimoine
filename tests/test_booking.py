from datetime import date

from patrimoine.models.booking import Booking
from patrimoine.models.enums import Plateforme, StatutBooking


def _booking(**overrides) -> Booking:
    defaults = dict(
        property_id=1,
        date_arrivee=date(2026, 7, 1),
        date_depart=date(2026, 7, 8),
        plateforme=Plateforme.airbnb,
        montant_brut=1000.0,
        commission_plateforme=200.0,
        statut=StatutBooking.confirmee,
    )
    defaults.update(overrides)
    return Booking(**defaults)


def test_nuits():
    b = _booking(date_arrivee=date(2026, 7, 1), date_depart=date(2026, 7, 8))
    assert b.nuits == 7


def test_net_encaisse_deduit_uniquement_la_commission():
    b = _booking(montant_brut=1000.0, commission_plateforme=200.0)
    assert b.net_encaisse == 800.0


def test_net_encaisse_exclut_toujours_la_taxe_de_sejour():
    # La taxe de sejour est un champ informatif : elle ne doit jamais influer
    # sur le net encaisse, qu'elle soit renseignee ou non (decision prise avec
    # l'utilisateur : agence, taxe jamais percue par l'hote).
    b = _booking(montant_brut=1000.0, commission_plateforme=200.0, taxe_sejour_collectee=50.0)
    assert b.net_encaisse == 800.0
