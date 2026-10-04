from datetime import date

import pytest
from sqlmodel import select

from patrimoine.models.property import Property
from patrimoine.services.backup import RestoreError, build_encrypted_archive, restore_encrypted_archive


def test_export_import_round_trip(session):
    from patrimoine import db

    session.add(Property(nom="Original", adresse="x", surface=30, date_acquisition=date(2020, 1, 1), prix_acquisition=100000))
    session.commit()

    archive = build_encrypted_archive("secret123")

    # On modifie les donnees apres l'export, pour verifier que la restauration les ecrase.
    prop = session.exec(select(Property)).first()
    prop.nom = "Modifie"
    session.add(prop)
    session.commit()

    restore_encrypted_archive("secret123", archive)
    db.dispose_engine()
    db.run_migrations()

    from sqlmodel import Session

    with Session(db.get_engine()) as s2:
        restored = s2.exec(select(Property)).first()
        assert restored.nom == "Original"


def test_restore_mauvais_mot_de_passe_leve_une_erreur(session):
    session.add(Property(nom="X", adresse="x", surface=30, date_acquisition=date(2020, 1, 1), prix_acquisition=100000))
    session.commit()

    archive = build_encrypted_archive("bon_mot_de_passe")

    with pytest.raises(RestoreError):
        restore_encrypted_archive("mauvais_mot_de_passe", archive)
