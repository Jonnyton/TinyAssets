"""Knowledge graph system -- entity extraction, Leiden clustering, HippoRAG.

This package owns the three-layer hybrid retrieval backbone:
  1. Knowledge graph (igraph + SQLite) with HippoRAG PPR
  2. Leiden community detection for character groups / plot threads
  3. RAPTOR tree synthesis for global/thematic queries
"""
