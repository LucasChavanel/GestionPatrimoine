from patrimoine.formatting import format_montant


def test_format_montant_ajoute_un_espace_tous_les_milliers():
    assert format_montant(142768.38) == "142 768.38"


def test_format_montant_sous_le_millier_inchange():
    assert format_montant(483.97) == "483.97"


def test_format_montant_plusieurs_milliers():
    assert format_montant(1234567.8) == "1 234 567.80"


def test_format_montant_negatif():
    assert format_montant(-1234.5) == "-1 234.50"


def test_format_montant_zero_decimale():
    assert format_montant(100000, decimales=0) == "100 000"


def test_format_montant_none_retourne_chaine_vide():
    assert format_montant(None) == ""
