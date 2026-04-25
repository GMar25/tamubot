"""Backward-compat shim — routing matrix moved to tamubot.rag.graph.builder."""
from tamubot.rag.graph.builder import ROUTING_MATRIX, RoutingEntry

__all__ = ["ROUTING_MATRIX", "RoutingEntry"]
