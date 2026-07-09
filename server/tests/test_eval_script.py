"""
Regression test for methods/similarity.py's scoring quality.
"""
import numpy as np

from evals.evaluate_similarity import fetch_reference_vectors, run_test
from evals.data import RAP_REFERENCE, RAP_QUERIES, POP_QUERIES


def test_rap_pop_separation_meets_threshold():
    ref_vectors = fetch_reference_vectors(RAP_REFERENCE)
    assert ref_vectors, "no reference vectors available — check ingestion/cache"

    rap_scores = run_test("RAP QUERIES", RAP_QUERIES, ref_vectors, RAP_REFERENCE)
    pop_scores = run_test("POP QUERIES", POP_QUERIES, ref_vectors, RAP_REFERENCE)

    assert rap_scores, "no rap scores produced"
    assert pop_scores, "no pop scores produced"

    gap = np.mean(rap_scores) - np.mean(pop_scores)

    assert gap > 0.23, f"separation gap too small: {gap:.4f}"