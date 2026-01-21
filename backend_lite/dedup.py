"""
Deduplication Utils
===================

Remove duplicate claims and contradictions.
Imported from main JETHRO4 codebase.
"""

import logging
from typing import List, Dict, Any
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


def deduplicate_contradictions(
    contradictions: List[Dict[str, Any]],
    similarity_threshold: float = 0.80
) -> List[Dict[str, Any]]:
    """
    Remove duplicate/similar contradictions
    """
    if not contradictions:
        return []

    unique = []
    removed = 0

    for contr in contradictions:
        desc = contr.get('explanation', '') or contr.get('description', '')

        is_dup = False
        for existing in unique:
            existing_desc = existing.get('explanation', '') or existing.get('description', '')

            if calculate_similarity(desc, existing_desc) >= similarity_threshold:
                is_dup = True
                removed += 1
                break

        if not is_dup:
            unique.append(contr)

    logger.info(f"Dedup contradictions: {len(unique)} unique (removed {removed})")
    return unique
