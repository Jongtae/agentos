"""
Entity graph skeleton for Phase 3 memory recall.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EntityNode:
    id: str
    type: str
    label: str = ""


@dataclass(frozen=True)
class EntityEdge:
    source: str
    target: str
    label: str


class GraphStorage(Protocol):
    def load(self) -> tuple[list[EntityNode], list[EntityEdge]]:
        ...

    def save(self, nodes: list[EntityNode], edges: list[EntityEdge]) -> None:
        ...


class InMemoryGraphStorage:
    def __init__(self):
        self._nodes: dict[str, EntityNode] = {}
        self._edges: list[EntityEdge] = []

    def load(self) -> tuple[list[EntityNode], list[EntityEdge]]:
        return list(self._nodes.values()), list(self._edges)

    def save(self, nodes: list[EntityNode], edges: list[EntityEdge]) -> None:
        self._nodes = {n.id: n for n in nodes}
        self._edges = list(edges)


class MemoryEntityGraph:
    """
    Minimal graph API used by future memory intelligence features.
    """

    def __init__(self, storage: GraphStorage | None = None):
        self._storage = storage or InMemoryGraphStorage()
        nodes, edges = self._storage.load()
        self._nodes: dict[str, EntityNode] = {n.id: n for n in nodes}
        self._edges: list[EntityEdge] = list(edges)

    def add_node(self, node: EntityNode) -> None:
        self._nodes[node.id] = node
        self._persist()

    def add_edge(self, edge: EntityEdge) -> None:
        if edge.source not in self._nodes or edge.target not in self._nodes:
            return
        self._edges.append(edge)
        self._persist()

    def query_related(self, node_id: str, limit: int = 20) -> list[EntityEdge]:
        if node_id not in self._nodes:
            return []
        matches = [
            edge for edge in self._edges if edge.source == node_id or edge.target == node_id
        ]
        return matches[:limit]

    def nodes(self) -> list[EntityNode]:
        return list(self._nodes.values())

    def edges(self) -> list[EntityEdge]:
        return list(self._edges)

    def _persist(self) -> None:
        self._storage.save(self.nodes(), self.edges())

