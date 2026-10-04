# Patrimoine — Spécification v1

Outil **local** de gestion de patrimoine personnel : suivi de portefeuilles (IBKR, Trade Republic), gestion d'un appartement en location meublée de tourisme, et préparation des données de déclaration d'impôts.

> **Pour Claude Code :** ce document décrit le projet complet, mais **seule la Phase 1 est à implémenter maintenant**. Les phases suivantes sont décrites pour que l'architecture les anticipe. En cas d'ambiguïté, pose la question plutôt que de supposer. Les calculs fiscaux doivent être testés unitairement.

---

## 1. Principes non négociables

- **100 % local.** L'app tourne sur le Mac de l'utilisateur (Apple Silicon, macOS). Aucun déploiement serveur, aucun service cloud.
- **Serveur lié à `127.0.0.1` uniquement**, jamais `0.0.0.0`.
- **Aucun secret dans le code ni dans le repo.** Les tokens (IBKR, plus tard) sont stockés dans le Trousseau macOS via la librairie `keyring`.
- **Données hors du repo.** Base de données et pièces jointes dans un dossier de données configurable, par défaut `~/Library/Application Support/patrimoine/`. Le repo ne contient que le code. `.gitignore` strict.
- **Lecture seule vis-à-vis des courtiers.** L'app ne passe jamais d'ordre.
- **Les règles fiscales sont des paramètres, pas du code en dur.** Taux, plafonds et numéros de cases vivent dans des fichiers versionnés par année (voir §5).
- **L'outil prépare, l'utilisateur valide.** Toute sortie fiscale affiche clairement qu'il s'agit d'une aide à vérifier, pas d'un conseil fiscal.

## 2. Stack technique

- Python 3.12+, gestion des dépendances avec **uv**
- **FastAPI** + **Jinja2** + **HTMX** pour l'interface (pas de build frontend)
- **SQLModel** (SQLAlchemy) + **SQLite**, migrations avec **Alembic**
- Graphiques : **Chart.js** (fichier vendoré localement dans `static/`, pas de CDN)
- CSS : un fichier CSS simple et propre, ou Pico.css vendoré. Pas de framework lourd.
- Tests : **pytest**
- Interface **en français**, code et noms de variables en anglais.

Lancement : `uv run patrimoine` démarre le serveur et ouvre automatiquement le navigateur sur `http://127.0.0.1:<port>`.

## 3. Structure du projet (proposition)

```
patrimoine/
├── pyproject.toml
├── README.md
├── alembic/
├── src/patrimoine/
│   ├── main.py              # point d'entrée, ouvre le navigateur
│   ├── config.py            # chemins, dossier de données
│   ├── db.py
│   ├── models/              # SQLModel
│   ├── services/            # logique métier (calculs, simulateur fiscal)
│   ├── routes/              # endpoints FastAPI
│   ├── templates/           # Jinja2
│   ├── static/              # CSS, Chart.js vendoré
│   └── fiscal/
│       ├── params/2026.yaml # paramètres fiscaux par année
│       └── loader.py
└── tests/
```

## 4. Phase 1 — Socle + module Appartement (À IMPLÉMENTER)

### 4.1 Socle

- Page d'accueil (dashboard) avec résumé de l'appartement : recettes de l'année, charges de l'année, résultat, prochaines réservations.
- Navigation : Dashboard / Appartement / Indivision / Paramètres.
- Gestion des pièces jointes : upload de PDF/images, stockés dans `<data_dir>/documents/` avec un nom basé sur un hash (SHA-256) pour éviter les doublons, métadonnées en base (nom d'origine, date, entité liée).
- **Export de sauvegarde chiffré** : un bouton qui génère une archive chiffrée par mot de passe (base SQLite + dossier documents), par exemple avec `pyzipper` (AES-256). Fonction d'import/restauration correspondante. Affichage de la date de la dernière sauvegarde sur le dashboard.

### 4.2 Modèle de données Appartement

**Property (bien)**
- nom, adresse, surface
- date d'acquisition, prix d'acquisition, frais de notaire
- part estimée du terrain (en %, non amortissable, saisie manuelle)
- statut de classement meublé de tourisme : `non_classe` / `classe` (+ nombre d'étoiles, date de classement)
- numéro d'enregistrement/déclaration en mairie (texte, optionnel)
- date de première mise en location (optionnelle : le bien est actuellement en travaux)

**Booking (réservation)**
- dates d'arrivée et de départ, nombre de nuits (calculé)
- plateforme (Airbnb, Booking, direct, autre)
- montant brut payé par le voyageur
- commission plateforme
- taxe de séjour collectée (et si reversée par la plateforme ou par l'utilisateur)
- frais de ménage facturés
- montant net encaissé (calculé)
- statut : confirmée / annulée
- notes

**Expense (charge)**
- date, montant TTC, fournisseur, description
- catégorie : `copropriete`, `assurance`, `taxe_fonciere`, `energie`, `eau`, `internet`, `menage`, `linge`, `entretien`, `frais_plateforme_autres`, `comptabilite`, `interets_emprunt`, `autre`
- récurrence optionnelle (mensuelle, trimestrielle, annuelle) avec génération des occurrences
- pièce jointe

**Works (travaux)**
- date, montant TTC, fournisseur/artisan, description
- nature : `entretien_reparation` (charge déductible) / `amelioration` (amortissable) / `construction_agrandissement` (amortissable, durée longue)
- durée d'amortissement proposée (modifiable)
- pièce jointe obligatoire (avertissement visible si absente)
- flag « avant première mise en location »

**Furniture (mobilier et équipement)**
- date d'achat, montant TTC, description
- durée d'amortissement (défaut 5 à 10 ans selon type, modifiable)
- si montant < seuil paramétré (voir fichier fiscal), proposé en charge directe plutôt qu'en amortissement
- pièce jointe

### 4.3 Écrans Appartement

- **Fiche bien** : informations, statut de classement, rappel si la déclaration en mairie n'est pas renseignée.
- **Réservations** : liste filtrable par année, ajout/édition rapide, taux d'occupation par mois, graphique recettes mensuelles.
- **Charges** : liste par catégorie et par année, total, graphique par catégorie.
- **Travaux & mobilier** : liste avec nature, montant, statut de la pièce jointe, tableau d'amortissement prévisionnel.
- **Simulateur fiscal** (voir 4.4).

### 4.4 Simulateur micro-BIC / réel

Pour une année donnée, à partir des données saisies, calculer et afficher côte à côte :

1. **Micro-BIC non classé** : recettes × (1 − abattement), avec vérification du plafond.
2. **Micro-BIC classé** : idem avec les paramètres « classé ».
3. **Réel simplifié (estimation)** : recettes − charges déductibles − amortissements, avec la règle que l'amortissement ne peut pas créer ou augmenter un déficit (l'excédent est reportable : le suivre d'une année sur l'autre).

Afficher pour chaque option : revenu imposable estimé, et une estimation d'impôt avec une TMI saisie par l'utilisateur + prélèvements sociaux (taux dans le fichier fiscal).

Règles et avertissements à afficher :
- Si les recettes dépassent le plafond micro applicable, le micro est marqué « non applicable ».
- Au réel, mention que **les amortissements pratiqués sont réintégrés dans le calcul de la plus-value à la revente** (réforme 2025), avec le cumul des amortissements affiché.
- Mention que le réel implique une liasse fiscale, en général faite par un expert-comptable ou un service spécialisé, et que ce coût est lui-même une charge déductible.
- Bandeau permanent : « Estimation indicative — à valider avec un professionnel. »

Les calculs vivent dans `services/` et sont **couverts par des tests** avec des cas chiffrés écrits à la main.

### 4.5 Module Indivision (simple)

Les biens en indivision sont gérés par un tiers qui transmet les chiffres chaque année. Pas de gestion détaillée.

**CoOwnershipYear**
- année, nom ou libellé du bien/de l'ensemble
- quote-part de l'utilisateur (%)
- revenus bruts et charges (montants totaux ou déjà proratisés : champ pour préciser)
- régime déclaré (texte libre)
- montants à reporter (saisis tels que transmis)
- pièce jointe (document reçu)

Affichage : un tableau par année et un récapitulatif à intégrer au futur module impôts.

### 4.6 Critères d'acceptation Phase 1

- `uv run patrimoine` lance l'app et ouvre le navigateur, serveur sur 127.0.0.1 uniquement.
- On peut créer le bien, saisir réservations, charges, travaux, mobilier, avec pièces jointes.
- Le simulateur affiche les trois options avec les paramètres de `fiscal/params/2026.yaml`.
- Export chiffré et restauration fonctionnels (testé sur une base de démo).
- Tests pytest passants sur les calculs (nuits, net encaissé, amortissements, simulateur, plafonds).
- README : installation, lancement, emplacement des données, sauvegarde.

## 5. Paramètres fiscaux

Fichier YAML par année de **revenus**. Chaque valeur doit avoir un champ `source` et `verified: false` par défaut, que l'utilisateur passe à `true` après vérification.

Exemple `fiscal/params/2026.yaml` (valeurs à vérifier avant usage réel) :

```yaml
year: 2026
meuble_tourisme:
  micro_bic:
    non_classe:
      abattement: 0.30
      plafond_recettes: 15000
      source: "LF 2025 / loi Le Meur — à vérifier"
      verified: false
    classe:
      abattement: 0.50
      plafond_recettes: 83600
      source: "à vérifier"
      verified: false
  amortissement:
    seuil_charge_directe_mobilier: 600   # HT, usage courant — à vérifier
    durees_defaut:
      gros_oeuvre: 50
      facade_etancheite: 25
      installations_techniques: 20
      agencements: 15
      mobilier: 7
    source: "durées d'usage indicatives — à valider avec l'expert-comptable"
    verified: false
prelevements_sociaux:
  revenus_bic_lmnp: 0.172   # à vérifier selon nature du revenu
  revenus_capital_mobilier: 0.186
  verified: false
cases_declaration: {}   # rempli en Phase 4, numéros vérifiés chaque année
```

L'app affiche un avertissement si des paramètres utilisés ont `verified: false`.

## 6. Phases suivantes (NE PAS IMPLÉMENTER, mais anticiper)

### Phase 2 — IBKR
- Récupération via **Flex Web Service** (Flex Queries) au lancement de l'app : positions, transactions, dividendes, retenues à la source, opérations de change.
- Token et Query ID dans le Trousseau macOS (`keyring`). Écran Paramètres pour les saisir.
- Stockage local des relevés bruts (XML) pour audit, puis parsing en tables.
- Gestion des devises : positions en USD, conversion EUR pour l'affichage.

### Phase 3 — Trade Republic (PEA + CTO)
- **Pas d'API non officielle** (pas de `pytr` ni équivalent : fragile et nécessite le PIN).
- Saisie manuelle des opérations (date, ISIN, quantité, prix, frais) et/ou import des exports CSV/PDF de l'app.
- Récupération des cours des ETF au lancement depuis une source publique gratuite (source à proposer et valider avec l'utilisateur, en respectant les conditions d'utilisation).
- Suivi du PEA : versements cumulés vs plafond de 150 000 €, date d'ouverture, ancienneté (5 ans), allocation cible 80 % World / 20 % Europe avec bande de rééquilibrage 15-25 % sur la ligne Europe et alerte si sortie de bande.

### Phase 4 — Aide à la déclaration d'impôts
- **CTO IBKR** (pas d'IFU français) : calcul des plus-values réalisées en EUR au prix moyen pondéré, conversion aux taux BCE à la date de chaque opération, dividendes bruts et retenues étrangères.
- **Rappel formulaire 3916** (comptes à l'étranger) avec les informations à reporter pour chaque compte concerné.
- **Appartement** : montants selon le régime choisi.
- **Indivision** : report des montants transmis.
- Sortie : une page récapitulative « à reporter » par année, exportable en PDF ou Markdown, avec table de correspondance des cases issue du fichier fiscal de l'année.

### Phase 5 — Vue patrimoine globale
- Dashboard consolidé : actions (par enveloppe), cash, immobilier, or.
- Exposition géographique estimée (World ≈ 72 % US, paramétrable), part d'émergents, part Europe.
- Historique de valeur dans le temps (snapshot à chaque lancement).

## 7. Hors périmètre

- Passage d'ordres, quel que soit le courtier.
- Comptabilité de Stillwind (gérée par l'expert-comptable).
- Génération de la liasse fiscale LMNP au réel.
- Toute synchronisation cloud.
