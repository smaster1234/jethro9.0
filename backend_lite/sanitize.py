"""
Input Sanitizer - Remove report/meta sections from input
=========================================================

Prevents self-contamination where the system analyzes its own
output as if it were legal input.

Usage:
    from backend_lite.sanitize import sanitize_input
    clean_text = sanitize_input(raw_input)
"""

import re
from typing import Set, List

# =============================================================================
# System Markers - Indicate report output (not legal input)
# =============================================================================

SYSTEM_MARKERS: Set[str] = {
    # Hebrew report sections
    "תוצאות הניתוח",
    "מטא-דאטה",
    "טבלת טענות",
    "פרטי הטענה",
    "סתירות קשורות",
    "שאלות לחקירה נגדית",
    # English/system markers
    "LLM_",
    "claim_",
    "contr_",
    "analysis_id",
    "processing_time_ms",
    "validation_flags",
    "Claims Checked",
    "Contradictions Found",
    "duration_ms",
    "llm_mode",
    "llm_parse_ok",
    "llm_empty",
}

# Patterns for report table rows (compiled for efficiency)
REPORT_TABLE_PATTERNS: List[re.Pattern] = [
    re.compile(r'^ID\t'),           # Table headers
    re.compile(r'^claim_\d+'),      # Claim rows
    re.compile(r'^contr_\d+'),      # Contradiction rows
    re.compile(r'^\d+\.\s*claim_'), # Numbered claim references
    re.compile(r'^Status:\s*'),     # Status lines
    re.compile(r'^Severity:\s*'),   # Severity lines
]

# Signature/contact patterns
SIGNATURE_PATTERNS: List[re.Pattern] = [
    re.compile(r'טל[:\s]*[\d\-\(\)]{7,}'),     # Phone
    re.compile(r'פקס[:\s]*[\d\-\(\)]{7,}'),    # Fax
    re.compile(r'נייד[:\s]*[\d\-\(\)]{9,}'),   # Mobile
    re.compile(r'דוא"?ל[:\s]*\S+@\S+'),        # Email
    re.compile(r'\S+@\S+\.\S+'),               # Generic email
    re.compile(r'כתובת[:\s]*[^\.]{10,}'),      # Address
    re.compile(r'ת\.?ד\.?\s*\d+'),             # P.O. Box
    re.compile(r'מיקוד\s*\d{5,7}'),            # Postal code
    re.compile(r'בכבוד רב'),                   # Respectfully
    re.compile(r'בברכה'),                      # Best regards
    re.compile(r'\[נחתם אלקטרונית\]'),         # Electronic signature
    re.compile(r'^_{3,}$'),                    # Underlines
    re.compile(r'עו"ד\s+\S+\s+\S+$'),          # Lawyer signature
]


def sanitize_input(text: str) -> str:
    """
    Remove report/meta sections from input text.

    This prevents the system from analyzing its own output as if it were
    a legal document, which would create false contradictions.

    Args:
        text: Raw input text that may contain previous report output

    Returns:
        Cleaned text with report sections removed
    """
    if not text:
        return ""

    lines = text.split('\n')
    cleaned_lines = []
    skip_section = False

    for line in lines:
        # Check if we're entering a report section
        if any(marker in line for marker in SYSTEM_MARKERS):
            skip_section = True
            continue

        # Check for table row patterns
        if any(pattern.match(line) for pattern in REPORT_TABLE_PATTERNS):
            continue

        # Reset skip flag on empty lines (section boundary)
        if not line.strip():
            skip_section = False
            cleaned_lines.append(line)
            continue

        # Skip lines in report sections
        if skip_section:
            continue

        # Check for inline system references and remove them
        cleaned_line = line
        for marker in SYSTEM_MARKERS:
            if marker in cleaned_line:
                # Remove the portion containing the marker
                cleaned_line = re.sub(
                    rf'[^\n]*{re.escape(marker)}[^\n]*',
                    '',
                    cleaned_line
                )

        if cleaned_line.strip():
            cleaned_lines.append(cleaned_line)

    return '\n'.join(cleaned_lines).strip()


def contains_system_text(text: str) -> bool:
    """
    Check if text contains system/report markers.

    Args:
        text: Text to check

    Returns:
        True if text contains system markers
    """
    if not text:
        return False
    return any(marker in text for marker in SYSTEM_MARKERS)


def is_signature_block(text: str) -> bool:
    """
    Check if text is a signature/contact info block.

    Args:
        text: Text to check

    Returns:
        True if text appears to be a signature block
    """
    if not text:
        return False

    # Count how many signature patterns match
    matches = sum(1 for p in SIGNATURE_PATTERNS if p.search(text))

    # If more than 2 signature patterns match, it's likely a signature block
    if matches >= 2:
        return True

    # Short text with signature patterns
    if matches >= 1 and len(text) < 100:
        return True

    return False


def sanitize_claim_text(text: str, max_length: int = 500) -> str:
    """
    Sanitize and truncate claim text.

    Args:
        text: Raw claim text
        max_length: Maximum length (default 500)

    Returns:
        Sanitized, truncated claim text
    """
    if not text:
        return ""

    # Remove system markers inline
    clean = text
    for marker in SYSTEM_MARKERS:
        clean = clean.replace(marker, "")

    # Clean up whitespace
    clean = ' '.join(clean.split())

    # Truncate if needed
    if len(clean) > max_length:
        # Try to cut at word boundary
        cutoff = clean.rfind(' ', 0, max_length - 3)
        if cutoff > max_length // 2:
            clean = clean[:cutoff] + "..."
        else:
            clean = clean[:max_length - 3] + "..."

    return clean.strip()


def sanitize_quote(quote: str, max_length: int = 200) -> str:
    """
    Sanitize a quote for display in reports.

    Args:
        quote: Raw quote text
        max_length: Maximum length (default 200)

    Returns:
        Sanitized, truncated quote
    """
    if not quote:
        return ""

    # Check if quote contains system text - if so, skip it entirely
    if contains_system_text(quote):
        return ""

    return sanitize_claim_text(quote, max_length)
