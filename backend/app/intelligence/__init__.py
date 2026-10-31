"""Resume intelligence: normalisation, taxonomy and structure parsing.

Everything here is deterministic. No model is called, so the same document always
produces the same structure — which is what makes the scores built on top of it
reproducible (SCORING_METHODOLOGY.md §1).
"""
