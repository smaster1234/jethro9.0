"""
Credit System — Usage Tracking and Billing
============================================

Manages per-user/firm credits for analysis operations.
Every credit transaction is recorded in an immutable ledger.

Credit costs:
  - Document upload:     1 credit
  - Claim analysis:      0.5 credits per claim
  - LLM verification:    2 credits per call
  - OCR page:           1 credit per page

Usage:
    from credits import check_balance, deduct_analysis, grant_credits

    # Before analysis
    ok, balance = check_balance(user_id, firm_id, db)
    if not ok:
        raise HTTPException(402, "Insufficient credits")

    # After analysis
    deduct_analysis(user_id, firm_id, claims=50, verifier_calls=15, db=db)
"""

import logging
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Credit costs per operation
COST_PER_CLAIM = 0.5
COST_PER_VERIFIER_CALL = 2
COST_PER_DOCUMENT = 1
COST_PER_OCR_PAGE = 1
MIN_CREDITS_FOR_ANALYSIS = 10  # Minimum to start an analysis


def get_balance(user_id: str, firm_id: str, db) -> int:
    """Get current credit balance for a user."""
    from .db.models import UserCreditBalance

    row = db.query(UserCreditBalance).filter(
        UserCreditBalance.user_id == user_id,
    ).first()

    if row:
        return row.balance

    # No balance record → create one with initial grant
    _ensure_balance_row(user_id, firm_id, db)
    return _get_initial_grant()


def check_balance(user_id: str, firm_id: str, db, required: int = None) -> Tuple[bool, int]:
    """
    Check if user has enough credits.

    Returns:
        (has_enough, current_balance)
    """
    balance = get_balance(user_id, firm_id, db)
    min_required = required or MIN_CREDITS_FOR_ANALYSIS
    return (balance >= min_required, balance)


def estimate_analysis_cost(num_claims: int, num_verifier_calls: int = 30) -> int:
    """Estimate credit cost for an analysis run."""
    cost = (num_claims * COST_PER_CLAIM) + (num_verifier_calls * COST_PER_VERIFIER_CALL)
    return max(1, int(cost))


def deduct_analysis(
    db,
    user_id: str,
    operation_type: str = "analysis",
    claims_count: int = 0,
    verifier_calls: int = 0,
    firm_id: str = None,
    case_id: str = None,
    run_id: str = None,
) -> bool:
    """
    Deduct credits for an analysis run.
    If firm_id is not provided, it will be fetched from the user record.

    Returns:
        bool: True if deduction successful, False if insufficient credits
    """
    from .db.models import User

    # Get firm_id if not provided
    if not firm_id:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found for credit deduction")
            return False
        firm_id = user.firm_id

    # Calculate cost
    if operation_type == "text_analysis":
        cost = 10  # Fixed cost for free text analysis
    elif operation_type == "claims_analysis":
        cost = 5   # Fixed cost for pre-extracted claims
    else:
        cost = int(
            (claims_count * COST_PER_CLAIM) +
            (verifier_calls * COST_PER_VERIFIER_CALL)
        )

    cost = max(1, cost)

    # Check balance
    balance = get_balance(user_id, firm_id, db)
    if balance < cost:
        logger.warning(f"Insufficient credits for user {user_id}: has {balance}, needs {cost}")
        return False

    _record_transaction(
        user_id=user_id,
        firm_id=firm_id,
        amount=-cost,
        transaction_type="analysis",
        description=f"ניתוח ({operation_type}): {claims_count} טענות, {verifier_calls} אימותים",
        case_id=case_id,
        run_id=run_id,
        db=db,
    )
    return True


def deduct_document(db, user_id: str, firm_id: str = None, doc_name: str = "") -> int:
    """Deduct credit for document upload."""
    from .db.models import User

    # Get firm_id if not provided
    if not firm_id:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found for credit deduction")
            return 0
        firm_id = user.firm_id

    _record_transaction(
        user_id=user_id,
        firm_id=firm_id,
        amount=-COST_PER_DOCUMENT,
        transaction_type="document",
        description=f"העלאת מסמך: {doc_name[:100]}",
        db=db,
    )
    return COST_PER_DOCUMENT


def grant_credits(
    user_id: str,
    firm_id: str,
    amount: int,
    db,
    granted_by: str = None,
    description: str = "הענקת קרדיטים",
) -> int:
    """Grant credits to a user."""
    _record_transaction(
        user_id=user_id,
        firm_id=firm_id,
        amount=amount,
        transaction_type="grant",
        description=description,
        created_by=granted_by,
        db=db,
    )
    return amount


def get_user_credits_info(user_id: str, firm_id: str, db) -> Dict[str, Any]:
    """Get full credit info for a user (for API response)."""
    from .db.models import UserCreditBalance, CreditLedger

    balance_row = db.query(UserCreditBalance).filter(
        UserCreditBalance.user_id == user_id,
    ).first()

    if not balance_row:
        _ensure_balance_row(user_id, firm_id, db)
        balance_row = db.query(UserCreditBalance).filter(
            UserCreditBalance.user_id == user_id,
        ).first()

    # Recent transactions
    recent = (
        db.query(CreditLedger)
        .filter(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "balance": balance_row.balance if balance_row else 0,
        "total_granted": balance_row.total_granted if balance_row else 0,
        "total_consumed": balance_row.total_consumed if balance_row else 0,
        "last_transaction_at": (
            balance_row.last_transaction_at.isoformat()
            if balance_row and balance_row.last_transaction_at
            else None
        ),
        "recent_transactions": [
            {
                "id": t.id,
                "type": t.transaction_type,
                "amount": t.amount,
                "balance_after": t.balance_after,
                "description": t.description,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in recent
        ],
    }


# ── Internal helpers ──


def _get_initial_grant() -> int:
    """Initial free credits for new users."""
    import os
    return int(os.environ.get("INITIAL_CREDITS", "100"))


def _ensure_balance_row(user_id: str, firm_id: str, db):
    """Create balance row if missing, with initial grant."""
    from .db.models import UserCreditBalance

    existing = db.query(UserCreditBalance).filter(
        UserCreditBalance.user_id == user_id,
    ).first()

    if existing:
        return

    initial = _get_initial_grant()
    balance = UserCreditBalance(
        user_id=user_id,
        firm_id=firm_id,
        balance=initial,
        total_granted=initial,
        total_consumed=0,
        last_transaction_at=datetime.utcnow(),
    )
    db.add(balance)

    # Record grant in ledger
    _record_transaction(
        user_id=user_id,
        firm_id=firm_id,
        amount=initial,
        transaction_type="grant",
        description="קרדיטים ראשוניים",
        db=db,
        _skip_balance_update=True,  # We just created it
    )

    db.flush()
    logger.info("Created credit balance for user %s: %d initial credits", user_id, initial)


def _record_transaction(
    user_id: str,
    firm_id: str,
    amount: int,
    transaction_type: str,
    db,
    description: str = "",
    case_id: str = None,
    run_id: str = None,
    created_by: str = None,
    _skip_balance_update: bool = False,
):
    """Record a credit transaction and update balance."""
    from .db.models import CreditLedger, UserCreditBalance

    # Update balance
    if not _skip_balance_update:
        balance_row = db.query(UserCreditBalance).filter(
            UserCreditBalance.user_id == user_id,
        ).with_for_update().first()

        if not balance_row:
            _ensure_balance_row(user_id, firm_id, db)
            balance_row = db.query(UserCreditBalance).filter(
                UserCreditBalance.user_id == user_id,
            ).with_for_update().first()

        if balance_row:
            balance_row.balance += amount
            if amount > 0:
                balance_row.total_granted += amount
            else:
                balance_row.total_consumed += abs(amount)
            balance_row.last_transaction_at = datetime.utcnow()
            new_balance = balance_row.balance
        else:
            new_balance = amount
    else:
        new_balance = amount

    # Record ledger entry
    entry = CreditLedger(
        firm_id=firm_id,
        user_id=user_id,
        transaction_type=transaction_type,
        amount=amount,
        balance_after=new_balance,
        description=description,
        case_id=case_id,
        run_id=run_id,
        created_by=created_by,
    )
    db.add(entry)
    db.flush()

    logger.info(
        "Credit transaction: user=%s type=%s amount=%d balance=%d desc=%s",
        user_id, transaction_type, amount, new_balance, description[:50],
    )
