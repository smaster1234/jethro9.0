"""
Candidate Filter — Hard filters and topic clustering  (§4)
==========================================================

Before comparing "everything with everything" (O(n²)), this module
filters candidate pairs via hard filters and groups claims by topic
cluster.

Hard Filters (§4.1):
    1. Entity / subject overlap — claims must share ≥1 meaningful entity
    2. Plane match — FACT↔FACT or LAW↔LAW only
    3. Time reference compatibility — same period or indeterminate
    4. Speaker mode — two party claims from different sides → skip
       (those are DISAGREEMENT, not internal contradiction)

Topic Clustering (§4.2):
    Group claims by central entity / law-reference / event, so we
    only compare within or between close clusters.
"""

import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .extractor import (
    Claim,
    PLANE_FACT,
    PLANE_LAW,
    PLANE_OPINION,
    PLANE_PROCEDURAL,
    SPEAKER_MODE_PARTY_CLAIM,
    SPEAKER_MODE_QUOTE,
)

logger = logging.getLogger(__name__)

# Planes that can be meaningfully compared with each other
_COMPARABLE_PLANES: Set[Tuple[str, str]] = {
    (PLANE_FACT, PLANE_FACT),
    (PLANE_LAW, PLANE_LAW),
}


# ---------------------------------------------------------------------------
# Hard filters
# ---------------------------------------------------------------------------

def passes_hard_filters(a: Claim, b: Claim) -> bool:
    """
    Return True if the pair (a, b) may be a contradiction candidate.
    If False, skip this pair entirely.

    Cursor 5.2 §4 — hard gates:
    - Both claims must have speaker_mode set
    - Both claims must have plane set (and be comparable)
    - Two party claims → route to DISAGREEMENT, never TRUE_CONTRADICTION
    - Entity/subject overlap required
    """
    # Filter 0: speaker_mode must be present on both (Cursor 5.2 §4)
    if not a.speaker_mode or not b.speaker_mode:
        return False

    # Filter 1: entity / subject overlap
    if not _entity_overlap(a, b):
        return False

    # Filter 2: plane match (now returns False when plane missing)
    if not _plane_compatible(a, b):
        return False

    # Filter 3: speaker mode — two party-claims → DISAGREEMENT (not contradiction)
    # Block ALL party_claim vs party_claim pairs, not just cross-party
    if a.speaker_mode == SPEAKER_MODE_PARTY_CLAIM and b.speaker_mode == SPEAKER_MODE_PARTY_CLAIM:
        return False

    return True


def _entity_overlap(a: Claim, b: Claim) -> bool:
    """At least one shared entity (after alias resolution)."""
    ea = set(a.entities or [])
    eb = set(b.entities or [])
    if ea and eb:
        return bool(ea & eb)
    # If entities are empty we fall back to word overlap (legacy behaviour)
    return _word_overlap(a.text, b.text) >= 0.15


def _plane_compatible(a: Claim, b: Claim) -> bool:
    """Both claims must be on the same plane to be compared.

    Cursor 5.2 §4: missing plane → INSUFFICIENT_CONTEXT, not comparable.
    """
    pa = a.plane
    pb = b.plane
    if not pa or not pb:
        return False  # missing plane → cannot compare (hard gate)
    return (pa, pb) in _COMPARABLE_PLANES or (pb, pa) in _COMPARABLE_PLANES


def _is_cross_party_disagreement(a: Claim, b: Claim) -> bool:
    """If both are party-claims from different sides, skip (will be tagged DISAGREEMENT)."""
    if a.speaker_mode != SPEAKER_MODE_PARTY_CLAIM or b.speaker_mode != SPEAKER_MODE_PARTY_CLAIM:
        return False
    ra = a.speaker_role
    rb = b.speaker_role
    if ra and rb and ra != rb:
        return True
    return False


def _word_overlap(text1: str, text2: str) -> float:
    """Jaccard-like word overlap (fallback for claims with no entities)."""
    stopwords = {
        'את', 'של', 'על', 'עם', 'אל', 'מן', 'כי', 'לא', 'גם', 'או', 'אם',
        'הוא', 'היא', 'הם', 'הן', 'אני', 'אנחנו', 'זה', 'זו', 'זאת',
        'כל', 'כך', 'רק', 'עוד', 'יותר', 'היה', 'היתה', 'היו',
        'ה', 'ו', 'ב', 'ל', 'מ', 'ש', 'כ',
    }

    def words(t: str) -> set:
        return {
            w for w in re.sub(r'[^\w\s]', '', t.lower()).split()
            if len(w) >= 3 and w not in stopwords
        }

    w1 = words(text1)
    w2 = words(text2)
    if not w1 or not w2:
        return 0.5
    return len(w1 & w2) / min(len(w1), len(w2))


# ---------------------------------------------------------------------------
# Topic Clustering (§4.2)
# ---------------------------------------------------------------------------

def cluster_claims(claims: List[Claim]) -> Dict[str, List[Claim]]:
    """
    Group claims into topic clusters by central entity / law-ref / event.

    Returns mapping of cluster-key → list of claims in that cluster.
    A claim may appear in multiple clusters.
    """
    clusters: Dict[str, List[Claim]] = defaultdict(list)

    for claim in claims:
        keys = _cluster_keys(claim)
        if not keys:
            clusters["_unclustered"].append(claim)
        for key in keys:
            clusters[key].append(claim)

    return dict(clusters)


def _cluster_keys(claim: Claim) -> List[str]:
    """Derive cluster keys for a claim."""
    keys: List[str] = []

    # By entity
    for ent in (claim.entities or []):
        keys.append(f"entity:{ent}")

    # By law reference (if plane == LAW)
    if claim.plane == PLANE_LAW:
        for ent in (claim.entities or []):
            if re.search(r'סעיף|תקנה', ent):
                keys.append(f"law:{ent}")

    # By subject (if set)
    if claim.subject:
        keys.append(f"subject:{claim.subject}")

    return keys


def generate_candidate_pairs(claims: List[Claim]) -> List[Tuple[Claim, Claim]]:
    """
    Generate candidate pairs using clustering + hard filters.

    Instead of O(n²) all-pairs, we compare within clusters and apply
    hard filters.  Claims that share no cluster still go through a
    final pass with the word-overlap filter.
    """
    clusters = cluster_claims(claims)
    seen_pairs: Set[Tuple[str, str]] = set()
    candidates: List[Tuple[Claim, Claim]] = []

    for _key, group in clusters.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                pair_key = tuple(sorted([a.id, b.id]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                if passes_hard_filters(a, b):
                    candidates.append((a, b))

    # Final pass: unclustered claims with word-overlap fallback
    unclustered = clusters.get("_unclustered", [])
    for i, a in enumerate(unclustered):
        for b in unclustered[i + 1:]:
            pair_key = tuple(sorted([a.id, b.id]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            if passes_hard_filters(a, b):
                candidates.append((a, b))

    logger.info(
        f"Candidate generation: {len(claims)} claims → {len(candidates)} candidate pairs "
        f"(clusters={len(clusters)}, filtered from {len(seen_pairs)} unique pairs)"
    )
    return candidates
