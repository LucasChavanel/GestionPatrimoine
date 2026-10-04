"""Énumérations partagées par les modèles."""

from enum import Enum


class StatutClassement(str, Enum):
    non_classe = "non_classe"
    classe = "classe"


class NatureComposant(str, Enum):
    gros_oeuvre = "gros_oeuvre"
    facade_etancheite = "facade_etancheite"
    installations_techniques = "installations_techniques"
    agencements = "agencements"


class Plateforme(str, Enum):
    airbnb = "airbnb"
    booking = "booking"
    direct = "direct"
    autre = "autre"


class StatutBooking(str, Enum):
    confirmee = "confirmee"
    annulee = "annulee"


class ReversementTaxeSejour(str, Enum):
    agence_plateforme = "agence_plateforme"
    utilisateur = "utilisateur"


class CategorieCharge(str, Enum):
    copropriete = "copropriete"
    assurance = "assurance"
    taxe_fonciere = "taxe_fonciere"
    energie = "energie"
    eau = "eau"
    internet = "internet"
    menage = "menage"
    linge = "linge"
    entretien = "entretien"
    frais_plateforme_autres = "frais_plateforme_autres"
    comptabilite = "comptabilite"
    interets_emprunt = "interets_emprunt"
    autre = "autre"


class Recurrence(str, Enum):
    aucune = "aucune"
    mensuelle = "mensuelle"
    trimestrielle = "trimestrielle"
    annuelle = "annuelle"


class NatureWorks(str, Enum):
    entretien_reparation = "entretien_reparation"
    amelioration = "amelioration"
    construction_agrandissement = "construction_agrandissement"


class EntityType(str, Enum):
    property = "property"
    booking = "booking"
    expense = "expense"
    works = "works"
    furniture = "furniture"
    coownership_year = "coownership_year"
