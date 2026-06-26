"""
Haiku plausibility check for declared FK relationships — Phase 7, Step 7.4.

check_plausibility() asks Haiku to flag semantically implausible joins
(e.g. joining a "product_name" column to a "customer_id" column).
It returns a list of PlausibilitySuggestion objects, each of which may
carry an optional suggested_from_col alternative.

apply_decisions() builds a new ERDDeclaration with accepted suggestions
applied, without modifying the user's original.  Declined suggestions
are silently dropped — the original relationship is kept.

Public API
----------
PlausibilitySuggestion  dataclass
check_plausibility(api_key, declaration) -> (suggestions, usage)
apply_decisions(declaration, suggestions, accepted) -> ERDDeclaration
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from data_compass.config import MODEL_HAIKU
from data_compass.erd.infer import ERDDeclaration, Relationship

_SYSTEM = (
    "You are a database schema expert. "
    "You review declared FK relationships and identify any that are semantically "
    "implausible — where the column names or table context suggest the join does "
    "not make business sense. "
    "Only flag genuine red flags. Do NOT flag relationships that look plausible. "
    "Respond with a JSON array only, no prose."
)

_USER_TEMPLATE = """\
Tables and columns:
{schema_text}

Declared FK relationships:
{rels_text}

Return a JSON array where each item has these keys:
  from_table       (string)
  from_col         (string)
  to_table         (string)
  to_col           (string)
  reason           (string — one sentence explaining why this join looks wrong)
  suggested_from_col (string or null — a better FK column in from_table, if obvious)

Return [] if all relationships look plausible.
"""


@dataclass
class PlausibilitySuggestion:
    """A semantically implausible join flagged by Haiku."""
    from_table: str
    from_col: str
    to_table: str
    to_col: str
    reason: str
    suggested_from_col: str | None = None


def check_plausibility(
    api_key: str,
    declaration: ERDDeclaration,
) -> tuple[list[PlausibilitySuggestion], anthropic.types.Usage | None]:
    """Ask Haiku to identify semantically implausible joins.

    Returns
    -------
    (suggestions, usage)
        suggestions — list of PlausibilitySuggestion (empty = all plausible)
        usage       — token usage object for cost accounting, or None
    """
    schema_text = _build_schema_text(declaration)
    rels_text = _build_rels_text(declaration)

    if not declaration.relationships:
        return [], None

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL_HAIKU,
        max_tokens=512,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(
                    schema_text=schema_text,
                    rels_text=rels_text,
                ),
            }
        ],
    )
    usage = response.usage
    raw = response.content[0].text.strip()

    suggestions = _parse_response(raw)
    return suggestions, usage


def apply_decisions(
    declaration: ERDDeclaration,
    suggestions: list[PlausibilitySuggestion],
    accepted: set[int],
) -> ERDDeclaration:
    """Return a new ERDDeclaration with accepted Haiku suggestions applied.

    Parameters
    ----------
    declaration:
        The original user-confirmed declaration (never mutated).
    suggestions:
        The full list of PlausibilitySuggestion returned by check_plausibility.
    accepted:
        The set of 0-based indices into ``suggestions`` that the user accepted.

    For accepted suggestions that carry a ``suggested_from_col``, the
    matching relationship's from_col is updated.  Declined suggestions
    leave the original relationship unchanged.
    """
    # Build a mutable copy of the relationships
    new_rels: list[Relationship] = list(declaration.relationships)

    for idx in sorted(accepted):
        if idx >= len(suggestions):
            continue
        sug = suggestions[idx]
        if sug.suggested_from_col is None:
            continue  # no concrete correction to apply

        # Find and replace the matching relationship
        for i, rel in enumerate(new_rels):
            if (
                rel.from_table == sug.from_table
                and rel.from_col == sug.from_col
                and rel.to_table == sug.to_table
                and rel.to_col == sug.to_col
            ):
                new_rels[i] = Relationship(
                    from_table=rel.from_table,
                    from_col=sug.suggested_from_col,
                    to_table=rel.to_table,
                    to_col=rel.to_col,
                )
                break

    return ERDDeclaration(
        tables=list(declaration.tables),
        primary_keys=dict(declaration.primary_keys),
        relationships=new_rels,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_schema_text(declaration: ERDDeclaration) -> str:
    lines: list[str] = []
    for tbl in declaration.tables:
        pk = declaration.primary_keys.get(tbl.name, "(none declared)")
        lines.append(f"Table '{tbl.name}' (PK: {pk}):")
        for col in tbl.columns:
            lines.append(f"  - {col.name} ({col.inferred_type})")
    return "\n".join(lines)


def _build_rels_text(declaration: ERDDeclaration) -> str:
    if not declaration.relationships:
        return "(none)"
    return "\n".join(
        f"  {r.from_table}.{r.from_col} -> {r.to_table}.{r.to_col}"
        for r in declaration.relationships
    )


def _parse_response(raw: str) -> list[PlausibilitySuggestion]:
    """Parse Haiku's JSON response into PlausibilitySuggestion objects.

    Returns an empty list if the response cannot be parsed or is not a list.
    """
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            l for l in lines if not l.startswith("```")
        ).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    results: list[PlausibilitySuggestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            results.append(
                PlausibilitySuggestion(
                    from_table=str(item["from_table"]),
                    from_col=str(item["from_col"]),
                    to_table=str(item["to_table"]),
                    to_col=str(item["to_col"]),
                    reason=str(item.get("reason", "")),
                    suggested_from_col=item.get("suggested_from_col") or None,
                )
            )
        except (KeyError, TypeError):
            continue

    return results
