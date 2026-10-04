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


def _context_commun(session: Session, property_: Property, annee: int, expense_edit: Expense | None):
    expenses = session.exec(
        select(Expense).where(Expense.property_id == property_.id).order_by(Expense.date_paiement)
    ).all()
    expenses_annee = [e for e in expenses if e.date_paiement.year == annee]

    totaux_categorie: dict[str, float] = defaultdict(float)
    total_recuperable = 0.0
    for e in expenses_annee:
        totaux_categorie[e.categorie.value] += e.montant_ttc
        total_recuperable += e.montant_recuperable

    annees_disponibles = sorted({e.date_paiement.year for e in expenses}) or [annee]

    return {
        "property_": property_,
        "expenses": expenses_annee,
        "annee": annee,
        "annees_disponibles": annees_disponibles,
        "categories": list(CategorieCharge),
        "recurrences": list(Recurrence),
        "totaux_categorie": dict(totaux_categorie),
        "total_annee": sum(totaux_categorie.values()),
        "total_recuperable": total_recuperable,
        "expense_edit": expense_edit,
        "attachments_by_expense": _attachments_by_expense(session, expenses_annee),
        "redirect_to": f"/biens/{property_.id}/charges?annee={annee}",
    }


@router.get("")
def liste(
    property_id: int,
    request: Request,
    annee: int | None = None,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    annee = annee or date.today().year
    return templates.TemplateResponse(
        request, "property/charges.html", _context_commun(session, property_, annee, None)
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
    annee = expense_edit.date_paiement.year if expense_edit else date.today().year
    return templates.TemplateResponse(
        request, "property/charges.html", _context_commun(session, property_, annee, expense_edit)
    )


def _form_to_expense(
    expense: Expense,
    date_paiement: str,
    date_echeance: str | None,
    periode_debut: str | None,
    periode_fin: str | None,
    montant_ttc: float,
    montant_recuperable: float,
    fournisseur: str | None,
    description: str | None,
    categorie: CategorieCharge,
    recurrence: Recurrence,
) -> None:
    expense.date_paiement = date.fromisoformat(date_paiement)
    expense.date_echeance = date.fromisoformat(date_echeance) if date_echeance else None
    expense.periode_debut = date.fromisoformat(periode_debut) if periode_debut else None
    expense.periode_fin = date.fromisoformat(periode_fin) if periode_fin else None
    expense.montant_ttc = montant_ttc
    expense.montant_recuperable = montant_recuperable
    expense.fournisseur = fournisseur or None
    expense.description = description or None
    expense.categorie = categorie
    expense.recurrence = recurrence


@router.post("")
def creer(
    property_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    date_paiement: str = Form(...),
    date_echeance: str | None = Form(None),
    periode_debut: str | None = Form(None),
    periode_fin: str | None = Form(None),
    montant_ttc: float = Form(...),
    montant_recuperable: float = Form(0.0),
    fournisseur: str | None = Form(None),
    description: str | None = Form(None),
    categorie: CategorieCharge = Form(...),
    recurrence: Recurrence = Form(Recurrence.aucune),
):
    expense = Expense(
        property_id=property_id, date_paiement=date.today(), montant_ttc=0, categorie=categorie
    )
    _form_to_expense(
        expense,
        date_paiement,
        date_echeance,
        periode_debut,
        periode_fin,
        montant_ttc,
        montant_recuperable,
        fournisseur,
        description,
        categorie,
        recurrence,
    )
    session.add(expense)
    session.commit()
    return RedirectResponse(
        url=f"/biens/{property_id}/charges?annee={expense.date_paiement.year}", status_code=303
    )


@router.post("/appel-de-fonds")
def creer_appel_de_fonds(
    property_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    date_paiement: str = Form(...),
    date_echeance: str | None = Form(None),
    periode_debut: str | None = Form(None),
    periode_fin: str | None = Form(None),
    montant_courantes: float = Form(...),
    montant_recuperable_courantes: float = Form(0.0),
    montant_fonds_travaux: float = Form(0.0),
    fournisseur: str | None = Form(None),
    description: str | None = Form(None),
):
    """Un appel de fonds de copropriété se saisit en deux lignes : la quote-part
    de charges courantes (avec sa part récupérable) et le fonds de travaux
    (jamais récupérable, non déductible tant qu'il n'est pas utilisé)."""
    dp = date.fromisoformat(date_paiement)
    de = date.fromisoformat(date_echeance) if date_echeance else None
    pd = date.fromisoformat(periode_debut) if periode_debut else None
    pf = date.fromisoformat(periode_fin) if periode_fin else None

    session.add(
        Expense(
            property_id=property_id,
            date_paiement=dp,
            date_echeance=de,
            periode_debut=pd,
            periode_fin=pf,
            montant_ttc=montant_courantes,
            montant_recuperable=montant_recuperable_courantes,
            fournisseur=fournisseur or None,
            description=description or None,
            categorie=CategorieCharge.copro_courantes,
        )
    )
    if montant_fonds_travaux:
        session.add(
            Expense(
                property_id=property_id,
                date_paiement=dp,
                date_echeance=de,
                periode_debut=pd,
                periode_fin=pf,
                montant_ttc=montant_fonds_travaux,
                montant_recuperable=0.0,
                fournisseur=fournisseur or None,
                description=description or None,
                categorie=CategorieCharge.fonds_travaux,
            )
        )
    session.commit()
    return RedirectResponse(url=f"/biens/{property_id}/charges?annee={dp.year}", status_code=303)


@router.post("/{expense_id}")
def modifier(
    property_id: int,
    expense_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    date_paiement: str = Form(...),
    date_echeance: str | None = Form(None),
    periode_debut: str | None = Form(None),
    periode_fin: str | None = Form(None),
    montant_ttc: float = Form(...),
    montant_recuperable: float = Form(0.0),
    fournisseur: str | None = Form(None),
    description: str | None = Form(None),
    categorie: CategorieCharge = Form(...),
    recurrence: Recurrence = Form(Recurrence.aucune),
):
    expense = session.get(Expense, expense_id)
    if expense is None:
        return RedirectResponse(url=f"/biens/{property_id}/charges", status_code=303)
    _form_to_expense(
        expense,
        date_paiement,
        date_echeance,
        periode_debut,
        periode_fin,
        montant_ttc,
        montant_recuperable,
        fournisseur,
        description,
        categorie,
        recurrence,
    )
    session.add(expense)
    session.commit()
    return RedirectResponse(
        url=f"/biens/{property_id}/charges?annee={expense.date_paiement.year}", status_code=303
    )


@router.post("/{expense_id}/supprimer")
def supprimer(
    property_id: int,
    expense_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    expense = session.get(Expense, expense_id)
    annee = expense.date_paiement.year if expense else date.today().year
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
    return RedirectResponse(
        url=f"/biens/{property_id}/charges?annee={template.date_paiement.year}", status_code=303
    )
