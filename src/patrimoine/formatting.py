"""Filtre Jinja `montant` — formate un nombre avec un espace comme séparateur
de milliers (ex: 142768.38 -> "142 768.38"), utilisé dans tous les templates
à la place de `"%.2f"|format(x)` pour les montants en euros/devises."""

from __future__ import annotations


def format_montant(value: float | int | None, decimales: int = 2) -> str:
    if value is None:
        return ""
    entier, _, decimale = f"{value:,.{decimales}f}".partition(".")
    entier = entier.replace(",", " ")
    return f"{entier}.{decimale}" if decimale else entier
