from __future__ import annotations

import unittest

from kernel.memory.graph import EntityEdge, EntityNode, MemoryEntityGraph, InMemoryGraphStorage


class MemoryEntityGraphTests(unittest.TestCase):
    def test_graph_initializes_with_empty_dataset(self):
        graph = MemoryEntityGraph()
        self.assertEqual(graph.nodes(), [])
        self.assertEqual(graph.edges(), [])

    def test_query_related_empty_dataset_returns_empty(self):
        graph = MemoryEntityGraph()
        self.assertEqual(graph.query_related("missing-node"), [])

    def test_add_and_query_related(self):
        graph = MemoryEntityGraph(storage=InMemoryGraphStorage())
        graph.add_node(EntityNode(id="task:demo", type="task"))
        graph.add_node(EntityNode(id="file:main", type="file"))
        graph.add_edge(EntityEdge(source="task:demo", target="file:main", label="read"))

        related = graph.query_related("task:demo")
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0].label, "read")

    def test_add_edge_ignores_unknown_nodes(self):
        graph = MemoryEntityGraph()
        graph.add_node(EntityNode(id="task:demo", type="task"))
        graph.add_edge(EntityEdge(source="task:demo", target="file:missing", label="read"))
        self.assertEqual(graph.edges(), [])


if __name__ == "__main__":
    unittest.main()
