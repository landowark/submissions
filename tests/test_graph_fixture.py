"""Smoke test: the shared ``graph`` fixture builds without error."""
from __future__ import annotations


def test_graph_builds(graph):
    assert len(graph["submissions"]) == 4
    assert graph["runs"], "no runs seeded"
    assert graph["samples"], "no samples seeded"
