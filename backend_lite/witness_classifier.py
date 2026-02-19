"""
Witness Affiliation Classifier — LLM-Powered
=============================================

Classifies witnesses and experts in Israeli legal proceedings by affiliation:
- Which party called/submitted the witness
- Whether the witness is a party themselves (עד שהוא בעל דין)
- Whether the witness is court-appointed (מומחה מטעם בית המשפט)

This is a SEMANTIC task that requires deep understanding of Hebrew legal text.
Uses Claude Sonnet for superior Hebrew legal reasoning.

Witness categories:
  WITNESS_PARTY_INITIATOR  — עד שהוא בעל דין מצד התובע/מערער/מבקש
  WITNESS_PARTY_RESPONDENT — עד שהוא בעל דין מצד הנתבע/משיב
  WITNESS_FOR_INITIATOR    — עד מטעם התובע/מערער/מבקש (לא בעל דין)
  WITNESS_FOR_RESPONDENT   — עד מטעם הנתבע/משיב (לא בעל דין)
  EXPERT_FOR_INITIATOR     — עד מומחה מטעם התובע
  EXPERT_FOR_RESPONDENT    — עד מומחה מטעם הנתבע
  EXPERT_COURT_APPOINTED   — מומחה מטעם בית המשפט (רופא, מודד, שמאי)
  WITNESS_NEUTRAL          — עד ניטרלי / לא ניתן לקבוע
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Affiliation constants
WITNESS_PARTY_INITIATOR = "witness_party_initiator"
WITNESS_PARTY_RESPONDENT = "witness_party_respondent"
WITNESS_FOR_INITIATOR = "witness_for_initiator"
WITNESS_FOR_RESPONDENT = "witness_for_respondent"
EXPERT_FOR_INITIATOR = "expert_for_initiator"
EXPERT_FOR_RESPONDENT = "expert_for_respondent"
EXPERT_COURT_APPOINTED = "expert_court_appointed"
WITNESS_NEUTRAL = "witness_neutral"


@dataclass
class WitnessAffiliation:
    """Result of witness affiliation classification."""
    witness_name: str
    affiliation: str           # One of the constants above
    aligned_with: str          # "initiator" / "respondent" / "court" / "neutral"
    is_party: bool             # True if the witness IS a party (בעל דין)
    is_expert: bool            # True if expert witness
    is_court_appointed: bool   # True if appointed by the court
    confidence: float          # 0-1
    reasoning: str             # Hebrew explanation


# System prompt for the LLM classifier
_WITNESS_CLASSIFIER_PROMPT = """אתה מומחה בסדר דין אזרחי ישראלי. תפקידך לסווג עדים בהליך משפטי.

## המשימה
בהינתן שם עד והקשר מכתבי הטענות, קבע:
1. **affiliation**: מי הזמין את העד / מטעם מי העד מעיד
2. **is_party**: האם העד הוא בעל דין בעצמו (תובע/נתבע שמעיד)
3. **is_expert**: האם מדובר בעד מומחה
4. **is_court_appointed**: האם מונה ע"י בית המשפט

## סוגי עדים:
- **witness_party_initiator**: בעל דין מצד היוזם (תובע/מערער/מבקש/עותר) שמעיד
- **witness_party_respondent**: בעל דין מצד המגיב (נתבע/משיב) שמעיד
- **witness_for_initiator**: עד מטעם הצד היוזם (לא בעל דין)
- **witness_for_respondent**: עד מטעם הצד המגיב (לא בעל דין)
- **expert_for_initiator**: עד מומחה מטעם הצד היוזם
- **expert_for_respondent**: עד מומחה מטעם הצד המגיב
- **expert_court_appointed**: מומחה מטעם בית המשפט (רופא, מודד, שמאי, רו"ח)
- **witness_neutral**: לא ניתן לקבוע / עד ניטרלי

## סימנים לזיהוי:
- "עד מטעם התובע" / "עד תביעה" → witness_for_initiator
- "עד מטעם הנתבע" / "עד הגנה" → witness_for_respondent
- "המומחה מטעם בית המשפט" / "המומחה שמונה" → expert_court_appointed
- "התובע העיד" / "הנתבע בעדותו" → witness_party_*
- "ד"ר כהן, המומחה מטעם התובע" → expert_for_initiator
- "השמאי שמונה ע"י ביהמ"ש" → expert_court_appointed

## החזר JSON בלבד:
{
  "affiliation": "witness_for_initiator|witness_for_respondent|witness_party_initiator|witness_party_respondent|expert_for_initiator|expert_for_respondent|expert_court_appointed|witness_neutral",
  "aligned_with": "initiator|respondent|court|neutral",
  "is_party": true|false,
  "is_expert": true|false,
  "is_court_appointed": true|false,
  "confidence": 0.0-1.0,
  "reasoning": "הסבר קצר בעברית"
}"""


async def classify_witness_affiliation(
    witness_name: str,
    context: str,
    llm_client=None,
) -> WitnessAffiliation:
    """
    Classify a witness's affiliation using LLM analysis.

    Args:
        witness_name: Name or designation of the witness
        context: Surrounding text from pleadings/documents
        llm_client: LLM client instance (ClaudeBaseClient or GeminiBaseClient).
                    If None, falls back to rule-based heuristics.

    Returns:
        WitnessAffiliation with classification result
    """
    # Try rule-based heuristics first (fast path)
    rule_result = _classify_by_rules(witness_name, context)
    if rule_result and rule_result.confidence >= 0.85:
        return rule_result

    # Use LLM for complex cases
    if llm_client is not None:
        try:
            llm_result = await _classify_by_llm(witness_name, context, llm_client)
            if llm_result:
                return llm_result
        except Exception as e:
            logger.warning(f"LLM witness classification failed: {e}")

    # Return rule-based result (even if low confidence) or neutral
    return rule_result or WitnessAffiliation(
        witness_name=witness_name,
        affiliation=WITNESS_NEUTRAL,
        aligned_with="neutral",
        is_party=False,
        is_expert=False,
        is_court_appointed=False,
        confidence=0.2,
        reasoning="לא ניתן לקבוע שיוך — אין מידע מספיק",
    )


def _classify_by_rules(witness_name: str, context: str) -> Optional[WitnessAffiliation]:
    """
    Rule-based witness classification from explicit textual cues.

    Handles common patterns like:
    - "עד מטעם התובע"
    - "המומחה שמונה ע"י בית המשפט"
    - "התובע בעדותו"
    """
    combined = f"{witness_name} {context}".lower()
    combined = combined.replace('"', '').replace('״', '').replace('׳', '')

    # --- Court-appointed expert ---
    court_expert_cues = [
        "מומחה מטעם בית המשפט", "מומחה מטעם ביהמש", "מומחה שמונה",
        "מומחה שמינה בית המשפט", "מונה כמומחה", "מונתה כמומחית",
        "המומחה שמונה על ידי", "מומחה מטעם ביהמ",
    ]
    for cue in court_expert_cues:
        if cue in combined:
            return WitnessAffiliation(
                witness_name=witness_name,
                affiliation=EXPERT_COURT_APPOINTED,
                aligned_with="court",
                is_party=False, is_expert=True, is_court_appointed=True,
                confidence=0.95,
                reasoning=f"זוהה כמומחה מטעם בית המשפט (סימן: {cue})",
            )

    # --- Expert for initiator ---
    expert_initiator_cues = [
        "מומחה מטעם התובע", "מומחה מטעם המערער", "מומחה מטעם המבקש",
        "מומחה מטעם העותר", "מומחה התובע", "מומחה התביעה",
    ]
    for cue in expert_initiator_cues:
        if cue in combined:
            return WitnessAffiliation(
                witness_name=witness_name,
                affiliation=EXPERT_FOR_INITIATOR,
                aligned_with="initiator",
                is_party=False, is_expert=True, is_court_appointed=False,
                confidence=0.92,
                reasoning=f"מומחה מטעם הצד היוזם (סימן: {cue})",
            )

    # --- Expert for respondent ---
    expert_respondent_cues = [
        "מומחה מטעם הנתבע", "מומחה מטעם המשיב", "מומחה הנתבע",
        "מומחה ההגנה",
    ]
    for cue in expert_respondent_cues:
        if cue in combined:
            return WitnessAffiliation(
                witness_name=witness_name,
                affiliation=EXPERT_FOR_RESPONDENT,
                aligned_with="respondent",
                is_party=False, is_expert=True, is_court_appointed=False,
                confidence=0.92,
                reasoning=f"מומחה מטעם הצד המגיב (סימן: {cue})",
            )

    # --- Witness for initiator ---
    witness_initiator_cues = [
        "עד מטעם התובע", "עד מטעם המערער", "עד מטעם המבקש",
        "עד מטעם העותר", "עד תביעה", "עדת תביעה",
        "עד התובע", "עד התביעה",
    ]
    for cue in witness_initiator_cues:
        if cue in combined:
            return WitnessAffiliation(
                witness_name=witness_name,
                affiliation=WITNESS_FOR_INITIATOR,
                aligned_with="initiator",
                is_party=False, is_expert=False, is_court_appointed=False,
                confidence=0.92,
                reasoning=f"עד מטעם הצד היוזם (סימן: {cue})",
            )

    # --- Witness for respondent ---
    witness_respondent_cues = [
        "עד מטעם הנתבע", "עד מטעם המשיב", "עד הגנה", "עדת הגנה",
        "עד הנתבע", "עד ההגנה",
    ]
    for cue in witness_respondent_cues:
        if cue in combined:
            return WitnessAffiliation(
                witness_name=witness_name,
                affiliation=WITNESS_FOR_RESPONDENT,
                aligned_with="respondent",
                is_party=False, is_expert=False, is_court_appointed=False,
                confidence=0.92,
                reasoning=f"עד מטעם הצד המגיב (סימן: {cue})",
            )

    # --- Party as witness ---
    party_initiator_cues = [
        "התובע העיד", "התובע בעדותו", "המערער העיד", "המבקש העיד",
        "העותר העיד", "התובעת העידה", "בחקירתו של התובע",
        "בחקירתה של התובעת",
    ]
    for cue in party_initiator_cues:
        if cue in combined:
            return WitnessAffiliation(
                witness_name=witness_name,
                affiliation=WITNESS_PARTY_INITIATOR,
                aligned_with="initiator",
                is_party=True, is_expert=False, is_court_appointed=False,
                confidence=0.90,
                reasoning=f"בעל דין (צד יוזם) שמעיד (סימן: {cue})",
            )

    party_respondent_cues = [
        "הנתבע העיד", "הנתבע בעדותו", "המשיב העיד",
        "הנתבעת העידה", "בחקירתו של הנתבע", "בחקירתה של הנתבעת",
    ]
    for cue in party_respondent_cues:
        if cue in combined:
            return WitnessAffiliation(
                witness_name=witness_name,
                affiliation=WITNESS_PARTY_RESPONDENT,
                aligned_with="respondent",
                is_party=True, is_expert=False, is_court_appointed=False,
                confidence=0.90,
                reasoning=f"בעל דין (צד מגיב) שמעיד (סימן: {cue})",
            )

    # No clear cues found → return low-confidence neutral
    return WitnessAffiliation(
        witness_name=witness_name,
        affiliation=WITNESS_NEUTRAL,
        aligned_with="neutral",
        is_party=False,
        is_expert=False,
        is_court_appointed=False,
        confidence=0.3,
        reasoning="לא נמצאו סימנים ברורים לשיוך — נדרש ניתוח LLM",
    )


async def _classify_by_llm(
    witness_name: str,
    context: str,
    llm_client,
) -> Optional[WitnessAffiliation]:
    """
    Use LLM (Claude Sonnet) to classify witness affiliation from context.

    This handles the hard cases:
    - Implicit affiliation from document structure
    - Witness mentioned across multiple documents
    - Expert whose appointment source is ambiguous
    """
    user_prompt = f"""סווג את העד הבא:

שם העד: {witness_name}

הקשר מכתבי הטענות:
{context[:2000]}

קבע: מטעם מי העד מעיד? האם הוא בעל דין? האם הוא מומחה? האם מונה ע"י ביהמ"ש?"""

    messages = [
        {"role": "system", "content": _WITNESS_CLASSIFIER_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = await llm_client.call(
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=512,
    )

    if not result.success or not result.content:
        return None

    try:
        # Import the robust JSON parser
        from .llm_client import parse_json_robust
        data, ok, error = parse_json_robust(result.content)
        if not ok or data is None:
            logger.warning(f"Witness classifier JSON parse failed: {error}")
            return None

        affiliation = data.get("affiliation", WITNESS_NEUTRAL)
        aligned = data.get("aligned_with", "neutral")
        is_party = data.get("is_party", False)
        is_expert = data.get("is_expert", False)
        is_court = data.get("is_court_appointed", False)
        confidence = float(data.get("confidence", 0.5))
        reasoning = data.get("reasoning", "")

        return WitnessAffiliation(
            witness_name=witness_name,
            affiliation=affiliation,
            aligned_with=aligned,
            is_party=is_party,
            is_expert=is_expert,
            is_court_appointed=is_court,
            confidence=confidence,
            reasoning=reasoning,
        )

    except Exception as e:
        logger.warning(f"Failed to parse witness classification: {e}")
        return None
