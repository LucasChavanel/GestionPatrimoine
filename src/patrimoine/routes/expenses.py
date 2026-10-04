from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_the_property, templates
from ..models.enums import CategorieCharge, EntityType, Recurrence
from ..models.expense import Expense
from ..services.attachments import list_attachments
from ..services.recurrence import generate_occurrences

router = APIRouter(prefix="/appartement/charges")


def _attachments_by_expense(session: Session, expenses: list[Expense]) -> dict[int, list]:
    return {e.id: list_attachments(session, EntityType.expense, e.id) for e in expenses if e.id is not None}


@router.get("")
def liste(request: Request, annee: Optional[int] = None, session: Session = Depends(get_session)):
    property_ = get_the_property(session)
    annee = annee or date.today().year

    expenses: list[Expense] = []
    if property_ is not None:
        expenses = session.exec(
            select(Expense).where(Expense.property_id == property_.id).order_by(Expense.date)
        ).all()

    expenses_annee = [e for e in expenses if e.date.year == annee]

    totaux_categorie: dict[str, float] = defaultdict(float)
    for e in expenses_annee:
        totaux_categorie[e.categorie.value] += e.montant_ttc
    total_annee = sum(totaux_categorie.values())

    annees_disponibles = sorted({e.date.year for e in expenses}) or [annee]

    return templates.TemplateResponse(
        request,
        "property/charges.html",
        {
            "property_": property_,
            "expenses": expenses_annee,
            "annee": annee,
            "annees_disponibles": annees_disponibles,
            "categories": list(CategorieCharge),
            "recurrences": list(Recurrence),
            "totaux_categorie": dict(totaux_categorie),
            "total_annee": total_annee,
            "expense_edit": None,
            "attachments_by_expense": _attachments_by_expense(session, expenses_annee),
            "redirect_to": f"/appartement/charges?annee={annee}",
        },
    )


@router.get("/{expense_id}/modifier")
def modifier_formulaire(expense_id: int, request: Request, session: Session = Depends(get_session)):
    property_ = get_the_property(session)
    expense_edit = session.get(Expense, expense_id)
    annee = expense_edit.date.year if expense_edit else date.today().year

    expenses: list[Expense] = []
    if property_ is not None:
        expenses = session.exec(
            select(Expense).where(Expense.property_id == property_.id).order_by(Expense.date)
        ).all()
    expenses_annee = [e for e in expenses if e.date.year == annee]
    totaux_categorie: dict[str, float] = defaultdict(float)
    for e in expenses_annee:
        totaux_categorie[e.categorie.value] += e.montant_ttc
    annees_disponibles = sorted({e.date.year for e in expenses}) or [annee]

    return templates.TemplateResponse(
        request,
        "property/charges.html",
        {
            "property_": property_,
            "expenses": expenses_annee,
            "annee": annee,
            "annees_disponibles": annees_disponibles,
            "categories": list(CategorieCharge),
            "recurrences": list(Recurrence),
            "totaux_categorie": dict(totaux_categorie),
            "total_annee": sum(totaux_categorie.values()),
            "expense_edit": expense_edit,
            "attachments_by_expense": _attachments_by_expense(session, expenses_annee),
            "redirect_to": f"/appartement/charges?annee={annee}",
        },
    )


def _form_to_expense(
    expense: Expense,
    date_: str,
    montant_ttc: float,
    fournisseur: Optional[str],
    description: Optional[str],
    categorie: CategorieCharge,
    recurrence: Recurrence,
) -> None:
    expense.date = date.fromisoformat(date_)
    expense.montant_ttc = montant_ttc
    expense.fournisseur = fournisseur or None
    expense.description = description or None
    expense.categorie = categorie
    expense.recurrence = recurrence


@router.post("")
def creer(
    session: Session = Depends(get_session),
    date_: str = Form(..., alias="date"),
    montant_ttc: float = Form(...),
    fournisseur: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    categorie: CategorieCharge = Form(...),
    recurrence: Recurrence = Form(Recurrence.aucune),
):
    property_ = get_the_property(session)
    if property_ is None or property_.id is None:
        return RedirectResponse(url="/appartement", status_code=303)

    expense = Expense(property_id=property_.id, date=date.today(), montant_ttc=0, categorie=categorie)
    _form_to_expense(expense, date_, montant_ttc, fournisseur, description, categorie, recurrence)
    session.add(expense)
    session.commit()
    return RedirectResponse(url=f"/appartement/charges?annee={expense.date.year}", status_code=303)


@router.post("/{expense_id}")
def modifier(
    expense_id: int,
    session: Session = Depends(get_session),
    date_: str = Form(..., alias="date"),
    montant_ttc: float = Form(...),
    fournisseur: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    categorie: CategorieCharge = Form(...),
    recurrence: Recurrence = Form(Recurrence.aucune),
):
    expense = session.get(Expense, expense_id)
    if expense is None:
        return RedirectResponse(url="/appartement/charges", status_code=303)
    _form_to_expense(expense, date_, montant_ttc, fournisseur, description, categorie, recurrence)
    session.add(expense)
    session.commit()
    return RedirectResponse(url=f"/appartement/charges?annee={expense.date.year}", status_code=303)


@router.post("/{expense_id}/supprimer")
def supprimer(expense_id: int, session: Session = Depends(get_session)):
    expense = session.get(Expense, expense_id)
    annee = expense.date.year if expense else date.today().year
    if expense is not None:
        session.delete(expense)
        session.commit()
    return RedirectResponse(url=f"/appartement/charges?annee={annee}", status_code=303)


@router.post("/{expense_id}/generer")
def generer(
    expense_id: int,
    session: Session = Depends(get_session),
    jusqu_au: str = Form(...),
):
    template = session.get(Expense, expense_id)
    if template is None:
        return RedirectResponse(url="/appartement/charges", status_code=303)
    generate_occurrences(session, template, date.fromisoformat(jusqu_au))
    return RedirectResponse(url=f"/appartement/charges?annee={template.date.year}", status_code=303)
