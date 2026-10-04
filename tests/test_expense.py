from datetime import date

from sqlmodel import select

from patrimoine.models.enums import CategorieCharge, Recurrence
from patrimoine.models.expense import Expense
from patrimoine.services.recurrence import add_months, generate_occurrences


def test_add_months_gere_les_fins_de_mois():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 1, 15), 3) == date(2026, 4, 15)
    assert add_months(date(2026, 11, 30), 2) == date(2027, 1, 30)


def test_generate_occurrences_mensuelle(session):
    template = Expense(
        property_id=1,
        date_paiement=date(2026, 1, 15),
        montant_ttc=100.0,
        categorie=CategorieCharge.energie_internet,
        recurrence=Recurrence.mensuelle,
    )
    session.add(template)
    session.commit()
    session.refresh(template)

    created = generate_occurrences(session, template, date(2026, 6, 30))
    assert created == 5  # fevrier a juin

    all_expenses = session.exec(select(Expense)).all()
    assert len(all_expenses) == 6
    dates = sorted(e.date_paiement for e in all_expenses)
    assert dates == [date(2026, m, 15) for m in range(1, 7)]


def test_generate_occurrences_est_idempotent(session):
    template = Expense(
        property_id=1,
        date_paiement=date(2026, 1, 15),
        montant_ttc=100.0,
        categorie=CategorieCharge.energie_internet,
        recurrence=Recurrence.mensuelle,
    )
    session.add(template)
    session.commit()
    session.refresh(template)

    generate_occurrences(session, template, date(2026, 6, 30))
    created_again = generate_occurrences(session, template, date(2026, 6, 30))

    assert created_again == 0
    assert len(session.exec(select(Expense)).all()) == 6


def test_generate_occurrences_aucune_pour_charge_non_recurrente(session):
    template = Expense(
        property_id=1,
        date_paiement=date(2026, 1, 15),
        montant_ttc=100.0,
        categorie=CategorieCharge.autre,
        recurrence=Recurrence.aucune,
    )
    session.add(template)
    session.commit()
    session.refresh(template)

    assert generate_occurrences(session, template, date(2026, 12, 31)) == 0
