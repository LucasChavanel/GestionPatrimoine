# Patrimoine

Outil **local** de gestion de patrimoine personnel — Phase 1 : socle + module Appartement (location meublée de tourisme) + module Indivision (simple) + simulateur fiscal micro-BIC / réel.

> Estimation indicative — à valider avec un professionnel. Cet outil prépare les chiffres, il ne remplace pas un expert-comptable.

## Principes

- 100 % local : aucun déploiement serveur, aucun service cloud. Le serveur n'écoute que sur `127.0.0.1`.
- Lecture seule vis-à-vis des courtiers (phases suivantes) : l'app ne passe jamais d'ordre.
- Les règles fiscales sont des paramètres versionnés (`src/patrimoine/fiscal/params/<année>.yaml`), jamais du code en dur. Chaque valeur a un champ `verified` ; un avertissement s'affiche tant qu'il est à `false`.

## Installation

Prérequis : [uv](https://docs.astral.sh/uv/) (gère lui-même l'installation de Python 3.12, indépendamment du Python système).

```bash
uv sync
```

## Lancement

```bash
uv run patrimoine
```

Cela :
1. applique les migrations de base de données (aucune commande manuelle à taper),
2. démarre le serveur sur `http://127.0.0.1:<port>` (port `8451` par défaut, ou le premier port libre ensuite),
3. ouvre automatiquement le navigateur.

## Emplacement des données

Par défaut : `~/Library/Application Support/patrimoine/`
- `patrimoine.db` — base SQLite
- `documents/` — pièces jointes, stockées par hash SHA-256 (dédupliquées)

Rien de tout cela n'est versionné dans le repo (voir `.gitignore`). Le dossier est configurable via la variable d'environnement `PATRIMOINE_DATA_DIR`.

## Sauvegarde et restauration

Dans l'écran **Paramètres** :
- **Exporter** : génère une archive `.zip` chiffrée (AES-256 via `pyzipper`), protégée par le mot de passe de votre choix, contenant la base et les documents. Choisissez un mot de passe fort et conservez-le en lieu sûr — il n'est stocké nulle part par l'application.
- **Restaurer** : remplace la base et les documents actuels par ceux d'une archive. Les fichiers précédents sont renommés avec un horodatage (jamais supprimés), en cas de besoin de récupération manuelle.

La date de la dernière sauvegarde est affichée sur le dashboard.

## Développement

```bash
uv run pytest        # tests unitaires (calculs : nuits, net encaissé, amortissements, simulateur, plafonds)
uv run alembic revision --autogenerate -m "message"   # nouvelle migration après modification des modèles
```

## Périmètre de cette phase

Voir `SPEC_patrimoine.md` pour la spécification complète. Seule la Phase 1 (socle + Appartement + Indivision simple) est implémentée. Les phases suivantes (IBKR, Trade Republic, aide à la déclaration d'impôts, vue patrimoine globale) sont décrites dans la spec mais pas encore développées.
