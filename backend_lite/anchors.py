"""
Evidence Anchors
================

Utilities for building and normalizing evidence anchors.
"""

from typing import Dict, Any, Optional

from .extractor import Claim


def build_anchor_from_claim(claim: Claim, snippet: Optional[str] = None) -> Dict[str, Any]:
    """
    Build a standardized anchor dict from a Claim.

    Anchor schema fields:
    - doc_id
    - page_no
    - block_index
    - paragraph_index
    - char_start
    - char_end
    - snippet
    - bbox
    """
    return {
        "doc_id": getattr(claim, "doc_id", None),
        "page_no": getattr(claim, "page", None),
        "block_index": getattr(claim, "block_index", None),
        "paragraph_index": getattr(claim, "paragraph_index", None),
        "char_start": getattr(claim, "char_start", None),
        "char_end": getattr(claim, "char_end", None),
        "snippet": snippet if snippet is not None else getattr(claim, "text", None),
        "bbox": getattr(claim, "bbox", None),
    }


def build_anchor_from_block(block: Any, snippet: Optional[str] = None) -> Dict[str, Any]:
    """
    Build a standardized anchor dict from a DocumentBlock.
    """
    return {
        "doc_id": getattr(block, "document_id", None),
        "page_no": getattr(block, "page_no", None),
        "block_index": getattr(block, "block_index", None),
        "paragraph_index": getattr(block, "paragraph_index", None),
        "char_start": getattr(block, "char_start", None),
        "char_end": getattr(block, "char_end", None),
        "snippet": snippet if snippet is not None else getattr(block, "text", None),
        "bbox": getattr(block, "bbox_json", None),
    }


def find_anchor_for_snippet(db: Any, document_id: str, snippet: str) -> Optional[Dict[str, Any]]:
    """
    Find a block containing a snippet and build an anchor.
    """
    if not document_id or not snippet:
        return None

    from .db.models import DocumentBlock

    blocks = (
        db.query(DocumentBlock)
        .filter(DocumentBlock.document_id == document_id)
        .order_by(DocumentBlock.block_index.asc())
        .all()
    )

    for block in blocks:
        text = block.text or ""
        idx = text.find(snippet)
        if idx != -1:
            anchor = build_anchor_from_block(block, snippet=snippet)
            if block.char_start is not None:
                anchor["char_start"] = int(block.char_start) + idx
                anchor["char_end"] = int(block.char_start) + idx + len(snippet)
            return anchor

    if blocks:
        return build_anchor_from_block(blocks[0])

    return None


def normalize_anchor_input(anchor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize anchor input from clients (accepts page/page_no, paragraph/paragraph_index).
    """
    if not anchor:
        return {}

    normalized = dict(anchor)
    if "page_no" not in normalized and "page" in normalized:
        normalized["page_no"] = normalized.get("page")
    if "paragraph_index" not in normalized and "paragraph" in normalized:
        normalized["paragraph_index"] = normalized.get("paragraph")
    return normalized
