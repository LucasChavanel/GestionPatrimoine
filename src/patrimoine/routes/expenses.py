from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_property_or_404, templates
from ..models.enums import CategorieCharge, EntityType, Recurrence
from ..models.expense import Expense
from ..models.property import Property
from ..services.attachments import list_attachments
from ..services.recurrence import generate_occurrences

router = APIRouter(prefix="/biens/{property_id}/charges")


def _attachments_by_expense(session: Session, expenses: list[Expense]) -> dict[int, list]:
    return {e.id: list_attachments(session, EntityType.expense, e.id) for e in expenses if e.id is not None}


@router.get("")
def liste(
    property_id: int,
    request: Request,
    annee: int | None = None,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    annee = annee or date.today().year

    expenses = session.exec(
        select(Expense).where(Expense.property_id == property_id).order_by(Expense.date)
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
            "redirect_to": f"/biens/{property_id}/charges?annee={annee}",
        },
    )


@router.get("/{expense_id}/modifier")
def modifier_formulaire(
    property_id: int,
    expense_id: int,
    request: Request,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    expense_edit = session.get(Expense, expense_id)
    annee = expense_edit.date.year if expense_edit else date.today().year

    expenses = session.exec(
        select(Expense).where(Expense.property_id == property_id).order_by(Expense.date)
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
            "redirect_to": f"/biens/{property_id}/charges?annee={annee}",
        },
    )


def _form_to_expense(
    expense: Expense,
    date_: str,
    montant_ttc: float,
    fournisseur: str | None,
    description: str | None,
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
    property_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    date_: str = Form(..., alias="date"),
    montant_ttc: float = Form(...),
    fournisseur: str | None = Form(None),
    description: str | None = Form(None),
    categorie: CategorieCharge = Form(...),
    recurrence: Recurrence = Form(Recurrence.aucune),
):
    expense = Expense(property_id=property_id, date=date.today(), montant_ttc=0, categorie=categorie)
    _form_to_expense(expense, date_, montant_ttc, fournisseur, description, categorie, recurrence)
    session.add(expense)
    session.commit()
    return RedirectResponse(url=f"/biens/{property_id}/charges?annee={expense.date.year}", status_code=303)


@router.post("/{expense_id}")
def modifier(
    property_id: int,
    expense_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    date_: str = Form(..., alias="date"),
    montant_ttc: float = Form(...),
    fournisseur: str | None = Form(None),
    description: str | None = Form(None),
    categorie: CategorieCharge = Form(...),
    recurrence: Recurrence = Form(Recurrence.aucune),
):
    expense = session.get(Expense, expense_id)
    if expense is None:
        return RedirectResponse(url=f"/biens/{property_id}/charges", status_code=303)
    _form_to_expense(expense, date_, montant_ttc, fournisseur, description, categorie, recurrence)
    session.add(expense)
    session.commit()
    return RedirectResponse(url=f"/biens/{property_id}/charges?annee={expense.date.year}", status_code=303)


@router.post("/{expense_id}/supprimer")
def supprimer(
    property_id: int,
    expense_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    expense = session.get(Expense, expense_id)
    annee = expense.date.year if expense else date.today().year
    if expense is not None:
        session.delete(expense)
        session.commit()
    return RedirectResponse(url=f"/biens/{property_id}/charges?annee={annee}", status_code=303)


@router.post("/{expense_id}/generer")
def generer(
    property_id: int,
    expense_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    jusqu_au: str = Form(...),
):
    template = session.get(Expense, expense_id)
    if template is None:
        return RedirectResponse(url=f"/biens/{property_id}/charges", status_code=303)
    generate_occurrences(session, template, date.fromisoformat(jusqu_au))
    return RedirectResponse(url=f"/biens/{property_id}/charges?annee={template.date.year}", status_code=303)
