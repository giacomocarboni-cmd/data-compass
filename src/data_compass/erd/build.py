"""
ERD graph builder — Phase 7, Step 7.3.

build_erd(declaration) converts an ERDDeclaration into an ERDGraph, a
lookup-friendly structure used by the validation and the SQL prompt
injector.  No API calls.

Public API
----------
ERDGraph        dataclass — tables dict + pk dict + FK adjacency list
build_erd(declaration) -> ERDGraph
"""
from __future__ import annotations

from dataclasses import dataclass, field

from data_compass.erd.infer import ERDDeclaration, Relationship, TableSchema


@dataclass
class ERDGraph:
    """Lookup-friendly view of the declared ERD."""
    tables: dict[str, TableSchema]   # table_name -> TableSchema
    primary_keys: dict[str, str]     # table_name -> pk column name
    adjacency: list[Relationship]    # declared FK edges


def build_erd(declaration: ERDDeclaration) -> ERDGraph:
    """Build an :class:`ERDGraph` from a user-confirmed :class:`ERDDeclaration`."""
    return ERDGraph(
        tables={t.name: t for t in declaration.tables},
        primary_keys=dict(declaration.primary_keys),
        adjacency=list(declaration.relationships),
    )
