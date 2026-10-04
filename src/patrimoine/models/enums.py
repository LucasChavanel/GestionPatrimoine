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


class TypeLocation(str, Enum):
    meuble_classique = "meuble_classique"
    meuble_tourisme_classe = "meuble_tourisme_classe"
    meuble_tourisme_non_classe = "meuble_tourisme_non_classe"
    nu = "nu"


class CategorieCharge(str, Enum):
    copro_courantes = "copro_courantes"
    copro_regularisation = "copro_regularisation"
    fonds_travaux = "fonds_travaux"
    taxe_fonciere = "taxe_fonciere"
    assurance_pno = "assurance_pno"
    frais_gestion = "frais_gestion"
    menage_linge = "menage_linge"
    energie_internet = "energie_internet"
    eau = "eau"
    entretien_reparation = "entretien_reparation"
    travaux_amelioration = "travaux_amelioration"
    mobilier = "mobilier"
    interets_emprunt = "interets_emprunt"
    assurance_emprunteur = "assurance_emprunteur"
    frais_comptable = "frais_comptable"
    cfe = "cfe"
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
