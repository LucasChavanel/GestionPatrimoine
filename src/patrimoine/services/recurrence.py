"""Génération des occurrences d'une charge récurrente (voir SPEC §4.2 Expense)."""

from __future__ import annotations

import calendar
from datetime import date

from sqlmodel import Session, select

from ..models.enums import Recurrence
from ..models.expense import Expense

_INTERVAL_MONTHS = {
    Recurrence.mensuelle: 1,
    Recurrence.trimestrielle: 3,
    Recurrence.annuelle: 12,
}


def add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def generate_occurrences(session: Session, template: Expense, until: date) -> int:
    """Génère les occurrences manquantes entre la dernière occurrence connue et `until`.
    Idempotent : rejouer la génération avec le même `until` ne crée rien de plus."""
    interval_months = _INTERVAL_MONTHS.get(template.recurrence)
    if interval_months is None or template.id is None:
        return 0

    existing = session.exec(
        select(Expense).where(
            (Expense.id == template.id) | (Expense.parent_expense_id == template.id)
        )
    ).all()
    last_date = max(e.date for e in existing)

    created = 0
    current = last_date
    while True:
        current = add_months(current, interval_months)
        if current > until:
            break
        session.add(
            Expense(
                property_id=template.property_id,
                date=current,
                montant_ttc=template.montant_ttc,
                fournisseur=template.fournisseur,
                description=template.description,
                categorie=template.categorie,
                recurrence=Recurrence.aucune,
                parent_expense_id=template.id,
            )
        )
        created += 1
    session.commit()
    return created
