from datetime import date

from patrimoine.services.amortization import dotation_annuelle


def test_dotation_annuelle_annee_pleine_debut_janvier():
    # 1000 euros sur 5 ans, demarre le 1er janvier : ~200 euros/an.
    dotation_2021 = dotation_annuelle(1000, 5, date(2020, 1, 1), 2021)
    assert dotation_2021 == 200.0


def test_dotation_annuelle_hors_fenetre_retourne_zero():
    assert dotation_annuelle(1000, 5, date(2020, 1, 1), 2019) == 0.0
    assert dotation_annuelle(1000, 5, date(2020, 1, 1), 2026) == 0.0


def test_dotation_annuelle_prorata_premiere_et_derniere_annee():
    # Taux journalier de 1 euro/jour (730 euros sur 2 ans), debut 1er juillet 2020.
    base = 730
    duree = 2
    debut = date(2020, 7, 1)

    dotation_2020 = dotation_annuelle(base, duree, debut, 2020)
    dotation_2021 = dotation_annuelle(base, duree, debut, 2021)
    dotation_2022 = dotation_annuelle(base, duree, debut, 2022)

    # 2020 (bissextile) : du 1er juillet au 31 decembre = 184 jours.
    assert dotation_2020 == 184.0
    # 2021 : annee pleine.
    assert dotation_2021 == 365.0
    # 2022 : du 1er janvier au 30 juin (fenetre se termine le 30 juin 2022) = 181 jours.
    assert dotation_2022 == 181.0

    # Le total sur la duree de vie doit correspondre exactement a la base ici,
    # car la fenetre ne traverse qu'une seule annee bissextile en dehors d'elle-meme.
    assert dotation_2020 + dotation_2021 + dotation_2022 == base


def test_dotation_annuelle_base_ou_duree_nulle():
    assert dotation_annuelle(0, 5, date(2020, 1, 1), 2021) == 0.0
    assert dotation_annuelle(1000, 0, date(2020, 1, 1), 2021) == 0.0
