"""Document ingestion: validation and text extraction.

Deliberately narrow. This package turns bytes into text plus a confidence
figure, and knows nothing about scoring, matching or resume semantics — the
parser owns that. Keeping bytes away from interpretation is what lets the
document layer be tested with synthetic files alone.
"""
