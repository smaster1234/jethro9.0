#!/usr/bin/env python3
"""
Backfill missing anchors/insights for Phases 1-5.

Safe by default (dry-run). Use --apply to persist changes.
"""

import argparse
from typing import Dict, Any


def _anchor_missing(locator: Any) -> bool:
    if not locator or not isinstance(locator, dict):
        return True
    if not locator.get("doc_id"):
        return True
    if locator.get("char_start") is None or locator.get("char_end") is None:
        return True
    if not locator.get("snippet"):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill anchors/insights safely.")
    parser.add_argument("--apply", action="store_true", help="Persist changes (default: dry-run)")
    args = parser.parse_args()

    from backend_lite.db.session import get_db_session, init_db
    from backend_lite.db.models import Claim, Contradiction, ContradictionInsight
    from backend_lite.anchors import find_anchor_for_snippet
    from backend_lite.insights import compute_insight

    init_db()

    claim_updates = 0
    contradiction_updates = 0
    insights_created = 0

    with get_db_session() as db:
        claims = db.query(Claim).all()
        claim_map: Dict[str, Claim] = {c.id: c for c in claims if c.id}

        for claim in claims:
            if not _anchor_missing(claim.locator_json):
                continue
            if not claim.doc_id or not claim.text:
                continue
            snippet = (claim.text or "")[:80]
            anchor = find_anchor_for_snippet(db, claim.doc_id, snippet)
            if not anchor:
                continue
            claim_updates += 1
            if args.apply:
                claim.locator_json = anchor

        contradictions = db.query(Contradiction).all()
        for contr in contradictions:
            updated = False

            if _anchor_missing(contr.locator1_json):
                claim = claim_map.get(contr.claim1_id or "")
                if claim and claim.locator_json and not _anchor_missing(claim.locator_json):
                    contr.locator1_json = dict(claim.locator_json)
                    updated = True
                elif claim and claim.doc_id and contr.quote1:
                    anchor = find_anchor_for_snippet(db, claim.doc_id, contr.quote1[:80])
                    if anchor:
                        contr.locator1_json = anchor
                        updated = True

            if _anchor_missing(contr.locator2_json):
                claim = claim_map.get(contr.claim2_id or "")
                if claim and claim.locator_json and not _anchor_missing(claim.locator_json):
                    contr.locator2_json = dict(claim.locator_json)
                    updated = True
                elif claim and claim.doc_id and contr.quote2:
                    anchor = find_anchor_for_snippet(db, claim.doc_id, contr.quote2[:80])
                    if anchor:
                        contr.locator2_json = anchor
                        updated = True

            if updated:
                contradiction_updates += 1

        existing_insights = {
            i.contradiction_id
            for i in db.query(ContradictionInsight).all()
            if i.contradiction_id
        }
        for contr in contradictions:
            if not contr.id or contr.id in existing_insights:
                continue
            data = compute_insight(contr)
            insights_created += 1
            if args.apply:
                db.add(ContradictionInsight(
                    contradiction_id=contr.id,
                    impact_score=data["impact_score"],
                    risk_score=data["risk_score"],
                    verifiability_score=data["verifiability_score"],
                    stage_recommendation=data["stage_recommendation"],
                    prerequisites_json=data["prerequisites"],
                    evasions_json=data["expected_evasions"],
                    counters_json=data["best_counter_questions"],
                    do_not_ask=data["do_not_ask"],
                    do_not_ask_reason=data["do_not_ask_reason"],
                ))

        if args.apply:
            db.commit()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] Claims backfilled: {claim_updates}")
    print(f"[{mode}] Contradictions backfilled: {contradiction_updates}")
    print(f"[{mode}] Insights created: {insights_created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
