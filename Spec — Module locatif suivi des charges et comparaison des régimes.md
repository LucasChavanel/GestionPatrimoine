# Spec — Module locatif : suivi des charges et comparaison des régimes

Oct 4, 2026 · @Lucas

## Contexte et objectif

Le module suit, par appartement, les charges et les loyers d'une année civile, puis estime l'impôt sous chaque régime pour choisir le plus intéressant.

- **Biens** : lot 115 (2 pièces) et lot 131 (1 pièce), copropriété Le Soleil, Saint-Sorlin-d'Arves, syndic MBI.
- **Copropriété** : appels trimestriels (1er mars, juin, septembre, décembre), exercice du 1er mars au 28 février.
- **Année fiscale** = année civile, rattachement à la **date de paiement** (charges) ou d'**encaissement** (loyers).
- **Usage** : outil local, pas de calcul fiscal opposable. Les résultats sont des estimations à valider avec un comptable.

Régimes comparés : micro-BIC, LMNP réel (meublé) ; micro-foncier, foncier réel (nu).

## Modèle de données

Quatre tables : `bien`, `charge`, `recette`, `immobilisation`. Montants en euros TTC, stockés en centimes (entiers) pour éviter les erreurs d'arrondi.

**bien**

| Champ | Type | Note |
| --- | --- | --- |
| id | texte | `lot115`, `lot131` |
| nom | texte | "2 pièces", "Studio" |
| type\_location | enum | `meuble_classique`, `meuble_tourisme_classe`, `meuble_tourisme_non_classe`, `nu` |
| quote\_part | décimal 0–1 | 1 par défaut ; < 1 si indivision |
| date\_acquisition | date |  |
| prix\_acquisition | montant | hors frais |
| frais\_acquisition | montant | notaire, agence |
| part\_terrain | % | non amortissable, défaut 15 % |
| date\_mise\_en\_location | date | début des amortissements |

**charge**

| Champ | Type | Note |
| --- | --- | --- |
| id | uuid |  |
| bien\_id | réf. | obligatoire |
| date\_paiement | date | détermine l'année fiscale |
| date\_echeance | date | optionnel (exigibilité de l'appel) |
| periode\_debut, periode\_fin | date | optionnel (ex. 01/03–31/05) |
| categorie | enum | voir section suivante |
| montant\_ttc | montant | négatif autorisé (crédit, régularisation) |
| montant\_recuperable | montant | part refacturable au locataire, défaut 0 |
| fournisseur | texte |  |
| description | texte |  |
| recurrence | enum | `aucune`, `mensuelle`, `trimestrielle`, `annuelle` |
| justificatif | chemin | fichier local optionnel |

**recette**

| Champ | Type | Note |
| --- | --- | --- |
| id | uuid |  |
| bien\_id | réf. |  |
| date\_encaissement | date |  |
| periode\_debut, periode\_fin | date | séjour ou mois loué |
| montant\_brut | montant | loyer + charges facturées, avant commission |
| commission | montant | plateforme ou agence (devient une charge) |
| taxe\_sejour | montant | collectée pour la commune, exclue des recettes |
| canal | texte | Airbnb, agence, direct… |

**immobilisation** (sert uniquement au LMNP réel)

| Champ | Type | Note |
| --- | --- | --- |
| id | uuid |  |
| bien\_id | réf. |  |
| type | enum | `batiment`, `travaux`, `mobilier` |
| date\_mise\_en\_service | date | prorata la 1re année |
| montant | montant |  |
| duree\_ans | entier | défauts dans les paramètres |

## Catégories et traitement fiscal

Chaque catégorie porte son traitement par régime. En micro (BIC ou foncier), aucune charge n'est déduite : l'abattement forfaitaire couvre tout.

| Catégorie | LMNP réel | Foncier réel (2044) |
| --- | --- | --- |
| `copro_courantes` | déductible en totalité | déductible hors `montant_recuperable` |
| `copro_regularisation` | même sens que la charge régularisée (négatif = réduit les charges) | idem |
| `fonds_travaux` | non déductible (avance attachée au lot) | non déductible au versement ; déductible quand utilisé pour des travaux déductibles |
| `taxe_fonciere` | déductible (hors TEOM refacturée) | idem |
| `assurance_pno` | déductible | déductible |
| `frais_gestion` | déductible (agence, plateforme, conciergerie) | déductible (forfait 20 €/lot en plus) |
| `menage_linge` | déductible | sans objet |
| `energie_internet` | déductible si payé par le propriétaire | déductible seulement si non récupérable |
| `entretien_reparation` | déductible | déductible |
| `travaux_amelioration` | immobilisation (amortie) | déductible (hors agrandissement) |
| `mobilier` | immobilisation si > 500 € HT, sinon déductible | sans objet |
| `interets_emprunt` | déductible | déductible (hors plafond déficit) |
| `assurance_emprunteur` | déductible | déductible |
| `frais_comptable` | déductible | sans objet |
| `cfe` | déductible | sans objet |
| `autre` | à qualifier manuellement | à qualifier manuellement |

Règles d'implémentation :

- Stocker ce tableau dans un fichier de configuration, pas en dur dans le code.
- Une charge `travaux_amelioration` ou `mobilier` crée automatiquement une proposition d'`immobilisation` à valider.
- Un appel de fonds se saisit en **deux lignes par lot** : `copro_courantes` (avec sa part récupérable) et `fonds_travaux`.

## Calculs

Tous les calculs se font par bien puis en consolidé, après application de `quote_part`. Recettes = somme de `montant_brut − taxe_sejour` encaissés dans l'année.

**Micro-BIC** (meublé)

```latex
\text{base} = \text{recettes} \times (1 - \text{abattement}_{type})
```

Abattement et plafond selon `type_location` (paramètres). Si les recettes dépassent le plafond, afficher « micro non applicable ».

**LMNP réel** (meublé)

1. Résultat avant amortissement = recettes − charges déductibles − commissions.
2. Amortissement de l'année = somme des immobilisations (linéaire, prorata temporis la 1re année). Bâtiment = (prix + frais) × (1 − part\_terrain).
3. L'amortissement ne peut ni créer ni augmenter un déficit : la part non utilisée est reportée sans limite de durée (stocker le report).
4. Un déficit issu des charges est imputable sur les BIC non professionnels des 10 années suivantes (stocker le report).
5. Base = max(0, résultat après amortissement admis − déficits reportés).

**Micro-foncier** (nu)

```latex
\text{base} = \text{loyers} \times (1 - 0{,}30)
```

Applicable si loyers nus ≤ plafond.

**Foncier réel** (nu)

1. Résultat = loyers − charges déductibles (dont 20 € de frais de gestion forfaitaires par lot).
2. Déficit hors intérêts imputable sur le revenu global dans la limite du plafond ; le reste et la part liée aux intérêts sont reportables 10 ans sur les revenus fonciers.

**Impôt estimé** (tous régimes)

```latex
\text{impôt} = \text{base} \times (\text{TMI} + \text{taux prélèvements sociaux})
```

`TMI` est saisie par l'utilisateur. Afficher aussi l'écart en euros entre le meilleur régime et les autres.

**Avertissement à afficher pour le LMNP réel** : depuis 2025, les amortissements déduits sont réintégrés dans le calcul de la plus-value à la revente. L'outil affiche le cumul des amortissements déduits par bien.

## Paramètres fiscaux

Tous les taux et plafonds vivent dans un fichier `parametres_fiscaux.json` indexé par année de revenus, jamais en dur. Les valeurs ci-dessous sont approximatives (de mémoire, règles en vigueur pour les revenus 2025) et sont à vérifier chaque année sur impots.gouv.fr.

| Paramètre | Valeur par défaut |
| --- | --- |
| Micro-BIC meublé classique | abattement 50 %, plafond 77 700 € |
| Micro-BIC tourisme classé | abattement 50 %, plafond 77 700 € |
| Micro-BIC tourisme non classé | abattement 30 %, plafond 15 000 € |
| Micro-foncier | abattement 30 %, plafond 15 000 € |
| Déficit foncier imputable sur revenu global | 10 700 € / an |
| Prélèvements sociaux | 17,2 % (taux à confirmer pour 2026) |
| Frais de gestion forfaitaires (foncier réel) | 20 € par lot |
| Seuil d'immobilisation du mobilier | 500 € HT |
| Durée amortissement bâtiment | 30 ans |
| Durée amortissement travaux | 12 ans |
| Durée amortissement mobilier | 7 ans |
| Part terrain par défaut | 15 % |

L'écran des paramètres affiche la date de dernière vérification et un avertissement si elle date de l'année précédente.

## Écrans et sorties

Trois écrans suffisent, avec un sélecteur d'année et de bien (ou « tous ») en haut.

1. **Saisie** : formulaire actuel + champs `bien`, `montant_recuperable`, `categorie` étendue. Bouton « appel de fonds » qui crée d'un coup les deux lignes (courantes + fonds travaux) pour un lot.
2. **Synthèse annuelle** par bien : total recettes, total charges par catégorie, part récupérable, fonds travaux cumulé, amortissements.
3. **Comparatif régimes** : une ligne par régime applicable avec base imposable, impôt estimé, écart avec le meilleur. Les régimes non applicables (plafond dépassé, type de location incompatible) sont grisés avec la raison.

Exports :

- CSV des charges et recettes de l'année, par bien et par catégorie (pour un comptable).
- Récapitulatif des montants à reporter sur la déclaration selon le régime retenu (lignes 2042-C-PRO en micro-BIC, 2044 en foncier réel).

## Données initiales 2026

Les trois appels de fonds MBI de 2026 (mars, juin, septembre) servent de jeu d'essai : 2 112,34 € appelés, 1 741,39 € décaissés. Le crédit de 370,95 € reporté de décembre 2025 est réparti au prorata de l'appel de mars. Remplacer `2026-09-XX` par le jour du virement de septembre.

```csv
bien_id;date_echeance;date_paiement;categorie;montant_ttc;montant_recuperable;fournisseur;description
lot115;2026-03-01;2026-03-05;copro_courantes;201.87;111.94;SDC Le Soleil (MBI);Appel 01/03-31/05/2026
lot115;2026-03-01;2026-03-05;fonds_travaux;243.14;0;SDC Le Soleil (MBI);Fonds travaux appel 15
lot115;2026-03-01;2026-03-05;copro_regularisation;-240.15;0;SDC Le Soleil (MBI);Credit solde dec. 2025 (prorata)
lot131;2026-03-01;2026-03-05;copro_courantes;133.29;92.64;SDC Le Soleil (MBI);Appel 01/03-31/05/2026
lot131;2026-03-01;2026-03-05;fonds_travaux;109.08;0;SDC Le Soleil (MBI);Fonds travaux appel 15
lot131;2026-03-01;2026-03-05;copro_regularisation;-130.80;0;SDC Le Soleil (MBI);Credit solde dec. 2025 (prorata)
lot115;2026-06-01;2026-09-XX;copro_courantes;214.42;124.49;SDC Le Soleil (MBI);Appel 01/06-31/08/2026
lot115;2026-06-01;2026-09-XX;fonds_travaux;243.14;0;SDC Le Soleil (MBI);Fonds travaux appel 16
lot131;2026-06-01;2026-09-XX;copro_courantes;145.84;105.19;SDC Le Soleil (MBI);Appel 01/06-31/08/2026
lot131;2026-06-01;2026-09-XX;fonds_travaux;109.08;0;SDC Le Soleil (MBI);Fonds travaux appel 16
lot115;2026-09-01;2026-09-XX;copro_courantes;214.42;124.49;SDC Le Soleil (MBI);Appel 01/09-30/11/2026
lot115;2026-09-01;2026-09-XX;fonds_travaux;243.14;0;SDC Le Soleil (MBI);Fonds travaux appel 17
lot131;2026-09-01;2026-09-XX;copro_courantes;145.84;105.19;SDC Le Soleil (MBI);Appel 01/09-30/11/2026
lot131;2026-09-01;2026-09-XX;fonds_travaux;109.08;0;SDC Le Soleil (MBI);Fonds travaux appel 17
```

Fonds de travaux cumulé au 01/09/2026 (soldes syndic, pour contrôle) : 2 364,48 € pour le lot 115, 1 060,76 € pour le lot 131.

Questions ouvertes pour compléter le jeu d'essai : type de location et loyers 2026 par lot, quote-part en cas d'indivision, prix et date d'acquisition, taxe foncière.

## Critères d'acceptation et limites

Le module est validé quand le jeu d'essai donne exactement ces totaux 2026 :

| Contrôle | Lot 115 | Lot 131 | Total |
| --- | --- | --- | --- |
| Charges courantes | 630,71 € | 424,97 € | 1 055,68 € |
| dont récupérables | 360,92 € | 303,02 € | 663,94 € |
| Fonds de travaux | 729,42 € | 327,24 € | 1 056,66 € |
| Régularisation | −240,15 € | −130,80 € | −370,95 € |
| **Décaissé net** | **1 119,98 €** | **621,41 €** | **1 741,39 €** |

Autres critères :

- [ ] Tests unitaires sur chaque régime, dont un cas où l'amortissement est plafonné et reporté.
- [ ] Un changement de `quote_part` recalcule toutes les synthèses.
- [ ] Une charge sans `bien_id` est refusée.
- [ ] Les paramètres d'une année absente du fichier bloquent le comparatif avec un message clair.

Hors périmètre : génération de la liasse 2031/2033, calcul de la plus-value de cession, TVA, statut LMP.
