"""Ingestion pipeline — PDF parsing, embedding, Atlas setup.

Public API (import from here, not submodules):
    from tamubot.ingestion import parse_pdf, run_ingest, setup_indexes
"""

__all__ = ["parse_pdf", "run_ingest", "setup_indexes"]


def __getattr__(name: str):
    if name == "parse_pdf":
        from tamubot.ingestion.process_syllabi import parse_pdf
        return parse_pdf
    if name == "run_ingest":
        from tamubot.ingestion.ingest import main
        return main
    if name == "setup_indexes":
        from tamubot.ingestion.setup_atlas import main
        return main
    raise AttributeError(f"module 'tamubot.ingestion' has no attribute {name!r}")
