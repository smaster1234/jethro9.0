"""
Deduplication Utils
===================

Remove duplicate claims and contradictions.
Uses both text similarity and structural (claim pair) matching.
"""

import logging
from typing import List, Dict, Any, Set, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts (0-1)
    """
    if not text1 or not text2:
        return 0.0

    text1 = text1.strip().lower()
    text2 = text2.strip().lower()

    if text1 == text2:
        return 1.0

    return SequenceMatcher(None, text1, text2).ratio()


def deduplicate_claims(claims: List[Dict[str, Any]], similarity_threshold: float = 0.85) -> List[Dict[str, Any]]:
    """
    Remove duplicate/similar claims
    """
    if not claims:
        return []

    unique_claims = []
    duplicates_removed = 0

    for claim in claims:
        claim_text = claim.get('text', '') or claim.get('claim', '') or str(claim)

        if not claim_text:
            continue

        is_duplicate = False
        for existing_claim in unique_claims:
            existing_text = existing_claim.get('text', '') or existing_claim.get('claim', '') or str(existing_claim)
            similarity = calculate_similarity(claim_text, existing_text)

            if similarity >= similarity_threshold:
                is_duplicate = True
                duplicates_removed += 1

                # Merge locations if present
                if 'location' in claim and 'location' in existing_claim:
                    if isinstance(existing_claim.get('locations'), list):
                        if claim['location'] not in existing_claim['locations']:
                            existing_claim['locations'].append(claim['location'])
                    else:
                        existing_claim['locations'] = [existing_claim.get('location'), claim['location']]
                break

        if not is_duplicate:
            unique_claims.append(claim)

    logger.info(f"Dedup: {len(unique_claims)} unique claims (removed {duplicates_removed})")
    return unique_claims


def _extract_claim_pair_key(contr: Dict[str, Any]) -> Tuple[str, str]:
    """
    Extract a normalized claim pair key from a contradiction.
    Returns a sorted tuple of (claim1_id, claim2_id) for order-independent matching.
    """
    c1 = contr.get('claim1_id', '') or ''
    c2 = contr.get('claim2_id', '') or ''
    return tuple(sorted([c1, c2]))


def deduplicate_contradictions(
    contradictions: List[Dict[str, Any]],
    similarity_threshold: float = 0.80
) -> List[Dict[str, Any]]:
    """
    Remove duplicate/similar contradictions using multi-signal matching:
    1. Exact claim pair match (same claim1_id + claim2_id regardless of order)
    2. Text similarity of explanations
    3. Quote pair similarity (same quotes even with different explanations)
    """
    if not contradictions:
        return []

    unique: List[Dict[str, Any]] = []
    removed = 0
    seen_pairs: Set[Tuple[str, str]] = set()

    for contr in contradictions:
        # Signal 1: Exact claim pair match
        pair_key = _extract_claim_pair_key(contr)
        if pair_key[0] and pair_key[1] and pair_key in seen_pairs:
            removed += 1
            continue

        # Signal 2: Explanation text similarity
        desc = contr.get('explanation', '') or contr.get('description', '')

        # Signal 3: Quote pair similarity
        q1 = (contr.get('quote1', '') or '').strip().lower()
        q2 = (contr.get('quote2', '') or '').strip().lower()

        is_dup = False
        for existing in unique:
            existing_desc = existing.get('explanation', '') or existing.get('description', '')

            # Check explanation similarity
            if desc and existing_desc and calculate_similarity(desc, existing_desc) >= similarity_threshold:
                is_dup = True
                removed += 1
                break

            # Check quote pair similarity (both quotes must match)
            eq1 = (existing.get('quote1', '') or '').strip().lower()
            eq2 = (existing.get('quote2', '') or '').strip().lower()
            if q1 and q2 and eq1 and eq2:
                sim_direct = min(
                    calculate_similarity(q1, eq1),
                    calculate_similarity(q2, eq2)
                )
                sim_cross = min(
                    calculate_similarity(q1, eq2),
                    calculate_similarity(q2, eq1)
                )
                if max(sim_direct, sim_cross) >= similarity_threshold:
                    is_dup = True
                    removed += 1
                    break

        if not is_dup:
            unique.append(contr)
            if pair_key[0] and pair_key[1]:
                seen_pairs.add(pair_key)

    logger.info(f"Dedup contradictions: {len(unique)} unique (removed {removed})")
    return unique
