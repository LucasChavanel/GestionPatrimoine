from patrimoine.fiscal.loader import load_fiscal_params
from patrimoine.models.enums import AllocationCategorie
from patrimoine.models.security import Security
from patrimoine.services.allocation import compute_allocation
from patrimoine.services.positions import PositionCalculee


def _position(isin, categorie, quantite, cours, montant_investi=None):
    security = Security(isin=isin, nom=isin, categorie_allocation=categorie, dernier_cours=cours)
    return PositionCalculee(
        security=security,
        quantite_detenue=quantite,
        prmp=montant_investi / quantite if montant_investi else cours or 0.0,
        montant_investi=montant_investi if montant_investi is not None else quantite * (cours or 0.0),
    )


def test_allocation_dans_la_bande():
    # 800 World / 200 Europe -> 20% Europe, dans la bande 15-25%.
    positions = [
        _position("W1", AllocationCategorie.world, 8, 100),
        _position("E1", AllocationCategorie.europe, 2, 100),
    ]
    params = load_fiscal_params(2026)
    allocation = compute_allocation(positions, params)
    assert allocation.valeur_world == 800
    assert allocation.valeur_europe == 200
    assert allocation.pct_europe == 0.2
    assert allocation.hors_bande is False


def test_allocation_hors_bande_trop_europe():
    # 500 World / 500 Europe -> 50% Europe, hors bande.
    positions = [
        _position("W1", AllocationCategorie.world, 5, 100),
        _position("E1", AllocationCategorie.europe, 5, 100),
    ]
    params = load_fiscal_params(2026)
    allocation = compute_allocation(positions, params)
    assert allocation.pct_europe == 0.5
    assert allocation.hors_bande is True


def test_allocation_categorie_autre_ignoree_du_ratio():
    positions = [
        _position("W1", AllocationCategorie.world, 8, 100),
        _position("E1", AllocationCategorie.europe, 2, 100),
        _position("A1", AllocationCategorie.autre, 3, 100),
    ]
    params = load_fiscal_params(2026)
    allocation = compute_allocation(positions, params)
    assert allocation.valeur_autre == 300
    assert allocation.pct_europe == 0.2
    assert allocation.valeur_totale == 1300


def test_allocation_sans_cours_connu_utilise_montant_investi():
    positions = [_position("W1", AllocationCategorie.world, 10, None, montant_investi=1000)]
    params = load_fiscal_params(2026)
    allocation = compute_allocation(positions, params)
    assert allocation.valeur_world == 1000


def test_allocation_sans_position_pct_none():
    params = load_fiscal_params(2026)
    allocation = compute_allocation([], params)
    assert allocation.pct_europe is None
    assert allocation.hors_bande is None
