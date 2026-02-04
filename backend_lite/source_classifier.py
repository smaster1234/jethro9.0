"""
Document Source Classifier
===========================

מערכת לסיווג מקורות מסמכים וטענות בהקשר של חקירה נגדית.

מטרה:
- לזהות האם טענה מגיעה מתצהיר העד הנחקר, עד תומך, או מהצד השני
- לאפשר ניסוח שאלות שמתייחסות ספציפית למקור ("בתצהיר שלך כתבת...")

סוגי מקורות:
1. WITNESS_OWN_STATEMENT - תצהיר/עדות של העד הנחקר עצמו
2. SUPPORTING_WITNESS - תצהיר עד אחר מאותו צד
3. PARTY_PLEADING - כתב טענות של הצד (כתב הגנה, כתב תביעה)
4. OPPOSING_EVIDENCE - ראיה/טענה מהצד השני
5. COURT_FINDING - קביעה של בית המשפט
6. EXTERNAL_DOCUMENT - מסמך חיצוני (חוזה, חשבונית, וכו')
"""

import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SourceType(str, Enum):
    """סוג המקור של הטענה"""
    WITNESS_OWN_STATEMENT = "witness_own_statement"      # תצהיר העד הנחקר
    SUPPORTING_WITNESS = "supporting_witness"            # עד תומך מאותו צד
    PARTY_PLEADING = "party_pleading"                    # כתב טענות
    OPPOSING_EVIDENCE = "opposing_evidence"              # ראיה מהצד השני
    COURT_FINDING = "court_finding"                      # קביעת בית משפט
    EXTERNAL_DOCUMENT = "external_document"              # מסמך חיצוני
    UNKNOWN = "unknown"


class PartyRole(str, Enum):
    """תפקיד הצד בהליך"""
    PLAINTIFF = "plaintiff"          # תובע
    DEFENDANT = "defendant"          # נתבע
    APPELLANT = "appellant"          # מערער
    RESPONDENT = "respondent"        # משיב
    PETITIONER = "petitioner"        # מבקש
    WITNESS = "witness"              # עד
    EXPERT = "expert"                # מומחה
    COURT = "court"                  # בית משפט
    UNKNOWN = "unknown"


@dataclass
class DocumentMetadata:
    """מטא-דאטה של מסמך"""
    doc_id: str
    doc_name: str
    doc_type: str                    # תצהיר, כתב הגנה, פסק דין, וכו'
    party_role: PartyRole            # מי הגיש את המסמך
    party_name: Optional[str] = None # שם הצד
    witness_name: Optional[str] = None  # שם העד (אם תצהיר)
    date: Optional[str] = None       # תאריך המסמך
    is_examined_witness: bool = False  # האם זה העד הנחקר


@dataclass
class SourceClassification:
    """סיווג מקור של טענה"""
    source_type: SourceType
    document: Optional[DocumentMetadata] = None
    confidence: float = 1.0
    reasoning: str = ""
    
    # מידע לניסוח שאלות
    reference_phrase: str = ""       # "בתצהיר שלך מיום..."
    attribution_phrase: str = ""     # "אתה כתבת ש..."
    confrontation_phrase: str = ""   # "אבל בכתב ההגנה נאמר..."


class DocumentSourceClassifier:
    """
    מסווג מקורות מסמכים וטענות.
    
    משמש לזיהוי:
    - האם טענה מגיעה מהעד הנחקר או ממקור אחר
    - איך לנסח התייחסות למקור בשאלה
    """
    
    # תבניות לזיהוי סוגי מסמכים
    DOCUMENT_TYPE_PATTERNS = {
        'תצהיר': [
            r'תצהיר\s+(?:עדות\s+)?(?:ראשית\s+)?(?:של\s+)?(.+?)(?:\s+מיום|\s*$)',
            r'תצהיר\s+(?:מר|גב\'?|עו"ד)\s+(.+?)(?:\s+מיום|\s*$)',
            r'תצהיר\s+(\d+)',
        ],
        'כתב_הגנה': [
            r'כתב\s+הגנה',
            r'כתב\s+הגנה\s+מתוקן',
        ],
        'כתב_תביעה': [
            r'כתב\s+תביעה',
            r'כתב\s+תביעה\s+מתוקן',
        ],
        'פסק_דין': [
            r'פסק\s+דין',
            r'פס"ד',
            r'החלטה',
        ],
        'פרוטוקול': [
            r'פרוטוקול\s+(?:דיון|ישיבה)',
            r'עמ\'\s+\d+\s+לפרוטוקול',
        ],
        'חוות_דעת': [
            r'חוות\s+דעת',
            r'חוו"ד',
        ],
    }
    
    # תבניות לזיהוי צדדים
    PARTY_PATTERNS = {
        PartyRole.PLAINTIFF: [
            r'התובע(?:ת|ים)?',
            r'המבקש(?:ת|ים)?',
            r'המערער(?:ת|ים)?',
            r'מטעם\s+התביעה',
        ],
        PartyRole.DEFENDANT: [
            r'הנתבע(?:ת|ים)?',
            r'המשיב(?:ה|ים)?',
            r'מטעם\s+ההגנה',
        ],
        PartyRole.WITNESS: [
            r'העד\s+(.+)',
            r'עד\s+(?:התביעה|ההגנה)',
        ],
        PartyRole.COURT: [
            r'בית\s+המשפט',
            r'ביהמ"ש',
            r'כב\'\s+השופט',
        ],
    }
    
    # ביטויים לניסוח שאלות לפי סוג מקור
    REFERENCE_TEMPLATES = {
        SourceType.WITNESS_OWN_STATEMENT: {
            'reference': 'בתצהיר שלך{date_phrase}',
            'attribution': 'אתה כתבת ש',
            'confrontation': 'אבל בתצהיר שלך כתבת ש',
        },
        SourceType.SUPPORTING_WITNESS: {
            'reference': 'בתצהיר של {witness_name}{date_phrase}',
            'attribution': '{witness_name} העיד ש',
            'confrontation': 'אבל העד {witness_name} מטעמך העיד ש',
        },
        SourceType.PARTY_PLEADING: {
            'reference': 'ב{doc_type} שהגשת{date_phrase}',
            'attribution': 'נטען מטעמך ש',
            'confrontation': 'אבל ב{doc_type} שהגשת נאמר ש',
        },
        SourceType.OPPOSING_EVIDENCE: {
            'reference': 'לפי {doc_type} של הצד השני',
            'attribution': 'הצד השני טוען ש',
            'confrontation': 'הצד השני מציג ראיה ש',
        },
        SourceType.COURT_FINDING: {
            'reference': 'בית המשפט קבע{date_phrase}',
            'attribution': 'נקבע ש',
            'confrontation': 'אבל בית המשפט כבר קבע ש',
        },
        SourceType.EXTERNAL_DOCUMENT: {
            'reference': 'במסמך {doc_name}',
            'attribution': 'כתוב ש',
            'confrontation': 'אבל במסמך כתוב ש',
        },
    }
    
    def __init__(self, examined_witness_id: Optional[str] = None,
                 examined_witness_name: Optional[str] = None,
                 examined_witness_party: Optional[PartyRole] = None,
                 documents_metadata: Optional[List[DocumentMetadata]] = None):
        """
        אתחול המסווג.
        
        Args:
            examined_witness_id: מזהה העד הנחקר
            examined_witness_name: שם העד הנחקר
            examined_witness_party: הצד של העד הנחקר (תובע/נתבע)
            documents_metadata: רשימת מטא-דאטה של מסמכים
        """
        self.examined_witness_id = examined_witness_id
        self.examined_witness_name = examined_witness_name
        self.examined_witness_party = examined_witness_party or PartyRole.UNKNOWN
        self.documents_metadata = {d.doc_id: d for d in (documents_metadata or [])}
        
        # מיפוי שמות עדים למסמכים שלהם
        self._witness_documents: Dict[str, List[str]] = {}
        for doc in (documents_metadata or []):
            if doc.witness_name:
                if doc.witness_name not in self._witness_documents:
                    self._witness_documents[doc.witness_name] = []
                self._witness_documents[doc.witness_name].append(doc.doc_id)
    
    def classify_claim_source(
        self,
        claim_text: str,
        doc_id: Optional[str] = None,
        doc_name: Optional[str] = None,
        speaker: Optional[str] = None,
        speaker_role: Optional[str] = None,
        speaker_mode: Optional[str] = None,
    ) -> SourceClassification:
        """
        מסווג את מקור הטענה.
        
        Args:
            claim_text: טקסט הטענה
            doc_id: מזהה המסמך
            doc_name: שם המסמך
            speaker: מי אמר
            speaker_role: תפקיד הדובר
            speaker_mode: סוג הדיבור (finding/party_claim/quote)
        
        Returns:
            SourceClassification עם סוג המקור וביטויי ניסוח
        """
        # אם יש מטא-דאטה על המסמך
        if doc_id and doc_id in self.documents_metadata:
            doc_meta = self.documents_metadata[doc_id]
            return self._classify_from_metadata(doc_meta, speaker_mode)
        
        # ניסיון לזהות מסוג המסמך
        if doc_name:
            doc_type = self._detect_document_type(doc_name)
            party_role = self._detect_party_from_doc_name(doc_name)
            
            # האם זה מסמך של העד הנחקר?
            if self._is_examined_witness_document(doc_name, speaker):
                return self._create_classification(
                    SourceType.WITNESS_OWN_STATEMENT,
                    doc_name=doc_name,
                    doc_type=doc_type,
                )
            
            # האם זה מסמך של עד תומך?
            if doc_type == 'תצהיר' and party_role == self.examined_witness_party:
                witness_name = self._extract_witness_name(doc_name)
                return self._create_classification(
                    SourceType.SUPPORTING_WITNESS,
                    doc_name=doc_name,
                    doc_type=doc_type,
                    witness_name=witness_name,
                )
            
            # האם זה כתב טענות?
            if doc_type in ['כתב_הגנה', 'כתב_תביעה']:
                if party_role == self.examined_witness_party:
                    return self._create_classification(
                        SourceType.PARTY_PLEADING,
                        doc_name=doc_name,
                        doc_type=doc_type,
                    )
                else:
                    return self._create_classification(
                        SourceType.OPPOSING_EVIDENCE,
                        doc_name=doc_name,
                        doc_type=doc_type,
                    )
            
            # האם זה פסק דין?
            if doc_type == 'פסק_דין':
                return self._create_classification(
                    SourceType.COURT_FINDING,
                    doc_name=doc_name,
                    doc_type=doc_type,
                )
        
        # ניסיון לזהות מ-speaker_mode
        if speaker_mode == 'finding':
            return self._create_classification(SourceType.COURT_FINDING)
        
        if speaker_mode == 'party_claim':
            # צריך לבדוק אם זה מהצד של העד או מהצד השני
            if speaker_role and self._is_same_party(speaker_role):
                return self._create_classification(SourceType.PARTY_PLEADING)
            else:
                return self._create_classification(SourceType.OPPOSING_EVIDENCE)
        
        # ברירת מחדל
        return self._create_classification(SourceType.UNKNOWN)
    
    def _classify_from_metadata(
        self,
        doc_meta: DocumentMetadata,
        speaker_mode: Optional[str] = None
    ) -> SourceClassification:
        """סיווג לפי מטא-דאטה של מסמך"""
        
        # תצהיר של העד הנחקר
        if doc_meta.is_examined_witness:
            return self._create_classification(
                SourceType.WITNESS_OWN_STATEMENT,
                document=doc_meta,
            )
        
        # תצהיר של עד אחר מאותו צד
        if doc_meta.doc_type == 'תצהיר' and doc_meta.party_role == self.examined_witness_party:
            return self._create_classification(
                SourceType.SUPPORTING_WITNESS,
                document=doc_meta,
                witness_name=doc_meta.witness_name,
            )
        
        # כתב טענות של אותו צד
        if doc_meta.doc_type in ['כתב_הגנה', 'כתב_תביעה']:
            if doc_meta.party_role == self.examined_witness_party:
                return self._create_classification(
                    SourceType.PARTY_PLEADING,
                    document=doc_meta,
                )
            else:
                return self._create_classification(
                    SourceType.OPPOSING_EVIDENCE,
                    document=doc_meta,
                )
        
        # פסק דין / החלטה
        if doc_meta.party_role == PartyRole.COURT:
            return self._create_classification(
                SourceType.COURT_FINDING,
                document=doc_meta,
            )
        
        # מסמך מהצד השני
        if doc_meta.party_role != self.examined_witness_party:
            return self._create_classification(
                SourceType.OPPOSING_EVIDENCE,
                document=doc_meta,
            )
        
        return self._create_classification(
            SourceType.EXTERNAL_DOCUMENT,
            document=doc_meta,
        )
    
    def _create_classification(
        self,
        source_type: SourceType,
        document: Optional[DocumentMetadata] = None,
        doc_name: Optional[str] = None,
        doc_type: Optional[str] = None,
        witness_name: Optional[str] = None,
        confidence: float = 0.8,
    ) -> SourceClassification:
        """יוצר אובייקט סיווג עם ביטויי ניסוח"""
        
        templates = self.REFERENCE_TEMPLATES.get(source_type, {})
        
        # בניית ביטויי תאריך
        date_phrase = ""
        if document and document.date:
            date_phrase = f" מיום {document.date}"
        
        # בניית שם מסמך
        final_doc_name = doc_name or (document.doc_name if document else "")
        final_doc_type = doc_type or (document.doc_type if document else "מסמך")
        final_witness_name = witness_name or (document.witness_name if document else "")
        
        # יצירת ביטויים
        reference = templates.get('reference', '').format(
            date_phrase=date_phrase,
            doc_name=final_doc_name,
            doc_type=self._format_doc_type(final_doc_type),
            witness_name=final_witness_name,
        )
        
        attribution = templates.get('attribution', '').format(
            witness_name=final_witness_name,
        )
        
        confrontation = templates.get('confrontation', '').format(
            doc_type=self._format_doc_type(final_doc_type),
            witness_name=final_witness_name,
        )
        
        return SourceClassification(
            source_type=source_type,
            document=document,
            confidence=confidence,
            reasoning=f"Classified as {source_type.value}",
            reference_phrase=reference.strip(),
            attribution_phrase=attribution.strip(),
            confrontation_phrase=confrontation.strip(),
        )
    
    def _detect_document_type(self, doc_name: str) -> str:
        """מזהה סוג מסמך משם הקובץ"""
        for doc_type, patterns in self.DOCUMENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, doc_name, re.IGNORECASE):
                    return doc_type
        return 'מסמך'
    
    def _detect_party_from_doc_name(self, doc_name: str) -> PartyRole:
        """מזהה צד משם המסמך"""
        for party_role, patterns in self.PARTY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, doc_name, re.IGNORECASE):
                    return party_role
        return PartyRole.UNKNOWN
    
    def _extract_witness_name(self, doc_name: str) -> str:
        """מחלץ שם עד משם תצהיר"""
        for pattern in self.DOCUMENT_TYPE_PATTERNS.get('תצהיר', []):
            match = re.search(pattern, doc_name, re.IGNORECASE)
            if match and match.groups():
                return match.group(1).strip()
        return ""
    
    def _is_examined_witness_document(
        self,
        doc_name: str,
        speaker: Optional[str] = None
    ) -> bool:
        """בודק אם זה מסמך של העד הנחקר"""
        if not self.examined_witness_name:
            return False
        
        # בדיקה לפי שם העד בשם המסמך
        if self.examined_witness_name.lower() in doc_name.lower():
            return True
        
        # בדיקה לפי speaker
        if speaker and self.examined_witness_name.lower() in speaker.lower():
            return True
        
        return False
    
    def _is_same_party(self, speaker_role: str) -> bool:
        """בודק אם הדובר מאותו צד כמו העד הנחקר"""
        if self.examined_witness_party == PartyRole.PLAINTIFF:
            return speaker_role in ['plaintiff', 'petitioner', 'appellant']
        elif self.examined_witness_party == PartyRole.DEFENDANT:
            return speaker_role in ['defendant', 'respondent']
        return False
    
    def _format_doc_type(self, doc_type: str) -> str:
        """מפרמט סוג מסמך לתצוגה"""
        return doc_type.replace('_', ' ')


class CrossExamSourceContext:
    """
    הקשר מקורות לחקירה נגדית.
    
    מנהל את המידע על מקורות הטענות בהקשר של חקירה ספציפית.
    """
    
    def __init__(
        self,
        examined_witness_name: str,
        examined_witness_party: PartyRole,
        contradiction_claim1_source: SourceClassification,
        contradiction_claim2_source: SourceClassification,
    ):
        self.examined_witness_name = examined_witness_name
        self.examined_witness_party = examined_witness_party
        self.claim1_source = contradiction_claim1_source
        self.claim2_source = contradiction_claim2_source
    
    def get_witness_own_claim(self) -> Optional[SourceClassification]:
        """מחזיר את הטענה שמגיעה מהעד הנחקר"""
        if self.claim1_source.source_type == SourceType.WITNESS_OWN_STATEMENT:
            return self.claim1_source
        if self.claim2_source.source_type == SourceType.WITNESS_OWN_STATEMENT:
            return self.claim2_source
        return None
    
    def get_opposing_claim(self) -> Optional[SourceClassification]:
        """מחזיר את הטענה הסותרת (מהצד השני או ממקור אחר)"""
        if self.claim1_source.source_type != SourceType.WITNESS_OWN_STATEMENT:
            return self.claim1_source
        if self.claim2_source.source_type != SourceType.WITNESS_OWN_STATEMENT:
            return self.claim2_source
        return None
    
    def is_internal_contradiction(self) -> bool:
        """האם זו סתירה פנימית (שתי טענות של העד עצמו)"""
        return (
            self.claim1_source.source_type == SourceType.WITNESS_OWN_STATEMENT and
            self.claim2_source.source_type == SourceType.WITNESS_OWN_STATEMENT
        )
    
    def is_supporting_witness_contradiction(self) -> bool:
        """האם זו סתירה עם עד תומך"""
        types = {self.claim1_source.source_type, self.claim2_source.source_type}
        return (
            SourceType.WITNESS_OWN_STATEMENT in types and
            SourceType.SUPPORTING_WITNESS in types
        )
    
    def get_strategic_approach(self) -> str:
        """מחזיר גישה אסטרטגית מומלצת לפי סוג הסתירה"""
        
        if self.is_internal_contradiction():
            return "internal_contradiction"
        
        if self.is_supporting_witness_contradiction():
            return "supporting_witness_conflict"
        
        witness_claim = self.get_witness_own_claim()
        opposing_claim = self.get_opposing_claim()
        
        if witness_claim and opposing_claim:
            if opposing_claim.source_type == SourceType.COURT_FINDING:
                return "contradict_court_finding"
            
            if opposing_claim.source_type == SourceType.EXTERNAL_DOCUMENT:
                return "contradict_document"
            
            if opposing_claim.source_type == SourceType.OPPOSING_EVIDENCE:
                return "cross_party_conflict"
        
        return "general_contradiction"
    
    def get_question_phrasing(self) -> Dict[str, str]:
        """
        מחזיר ביטויי ניסוח לשאלות לפי הגישה האסטרטגית.
        
        Returns:
            Dict עם:
            - opening: פתיחת השאלה ("בתצהיר שלך כתבת...")
            - confrontation: ביטוי העימות ("אבל בכתב ההגנה נאמר...")
            - closing: סיום השאלה ("איך אתה מסביר את הסתירה?")
            - strategy_note: הערה אסטרטגית
        """
        approach = self.get_strategic_approach()
        witness_claim = self.get_witness_own_claim()
        opposing_claim = self.get_opposing_claim()
        
        # ברירות מחדל
        opening = ""
        confrontation = ""
        closing = "איך אתה מסביר את הסתירה?"
        strategy_note = ""
        
        if approach == "internal_contradiction":
            # סתירה פנימית - שתי טענות של העד עצמו
            opening = self.claim1_source.reference_phrase + ", " + self.claim1_source.attribution_phrase
            confrontation = "אבל " + self.claim2_source.reference_phrase + " כתבת משהו אחר"
            closing = "שתי הטענות לא יכולות להיות נכונות יחד. איזו מהן נכונה?"
            strategy_note = "סתירה פנימית - העד לא יכול להאשים אחרים. להישאר עם הציטוטים המדויקים."
        
        elif approach == "supporting_witness_conflict":
            # סתירה עם עד תומך
            if witness_claim:
                opening = witness_claim.attribution_phrase
            if opposing_claim:
                confrontation = opposing_claim.confrontation_phrase
            closing = "איך אתה מסביר שהעד מטעמך אומר אחרת?"
            strategy_note = "סתירה עם עד תומך - להדגיש שאחד מהם טועה או משקר."
        
        elif approach == "contradict_court_finding":
            # סתירה לקביעת בית משפט
            if witness_claim:
                opening = witness_claim.attribution_phrase
            if opposing_claim:
                confrontation = opposing_claim.confrontation_phrase
            closing = "אתה חולק על קביעת בית המשפט?"
            strategy_note = "סתירה לקביעה שיפוטית - ראיה חזקה מאוד. להדגיש את הסמכות."
        
        elif approach == "contradict_document":
            # סתירה למסמך
            if witness_claim:
                opening = witness_claim.attribution_phrase
            if opposing_claim:
                confrontation = opposing_claim.confrontation_phrase
            closing = "המסמך כתוב שחור על גבי לבן. איך אתה מסביר?"
            strategy_note = "סתירה למסמך - להציג את המסמך פיזית. לשאול אם העד מכיר אותו."
        
        elif approach == "cross_party_conflict":
            # עימות עם הצד השני
            if witness_claim:
                opening = witness_claim.attribution_phrase
            if opposing_claim:
                confrontation = opposing_claim.confrontation_phrase
            closing = "מה תגובתך לטענה הזו?"
            strategy_note = "עימות בין צדדים - להיות מוכן לתשובה מתגוננת. לדרוש הסבר, לא רק הכחשה."
        
        else:
            # כללי
            if witness_claim:
                opening = witness_claim.attribution_phrase
            if opposing_claim:
                confrontation = "אבל יש טענה סותרת"
            closing = "איך אתה מסביר את הסתירה?"
            strategy_note = "סתירה כללית - לזהות את נקודת התורפה ולהתמקד בה."
        
        return {
            "opening": opening,
            "confrontation": confrontation,
            "closing": closing,
            "strategy_note": strategy_note,
            "approach": approach,
        }
    
    def generate_source_aware_question(
        self,
        quote_a: str,
        quote_b: str,
        question_type: str = "confrontation"
    ) -> str:
        """
        מייצר שאלה שמתייחסת למקורות הספציפיים.
        
        Args:
            quote_a: ציטוט מטענה א'
            quote_b: ציטוט מטענה ב'
            question_type: סוג השאלה (confrontation/clarification/trap)
        
        Returns:
            שאלה מנוסחת עם התייחסות למקורות
        """
        phrasing = self.get_question_phrasing()
        approach = phrasing["approach"]
        
        # קיצור ציטוטים
        max_quote = 80
        quote_a_short = quote_a[:max_quote] + "..." if len(quote_a) > max_quote else quote_a
        quote_b_short = quote_b[:max_quote] + "..." if len(quote_b) > max_quote else quote_b
        
        if question_type == "confrontation":
            # שאלת עימות ישיר
            if approach == "internal_contradiction":
                return (
                    f'{self.claim1_source.reference_phrase}, כתבת: "{quote_a_short}". '
                    f'{self.claim2_source.reference_phrase}, כתבת: "{quote_b_short}". '
                    f'{phrasing["closing"]}'
                )
            else:
                return (
                    f'{phrasing["opening"]}: "{quote_a_short}". '
                    f'{phrasing["confrontation"]}: "{quote_b_short}". '
                    f'{phrasing["closing"]}'
                )
        
        elif question_type == "clarification":
            # שאלת הבהרה
            return (
                f'{phrasing["opening"]}: "{quote_a_short}". '
                f'תוכל להבהיר מה בדיוק התכוונת?'
            )
        
        elif question_type == "trap":
            # שאלת מלכודת - שאלה תמימה שמובילה לסתירה
            return (
                f'רק לוודא שהבנתי נכון - {phrasing["opening"].lower()}: "{quote_a_short}"?'
            )
        
        else:
            # ברירת מחדל
            return (
                f'{phrasing["opening"]}: "{quote_a_short}". '
                f'{phrasing["closing"]}'
            )


# פונקציות עזר לשימוש חיצוני

def create_source_classifier(
    examined_witness_name: str,
    examined_witness_party: str,
    documents: Optional[List[Dict[str, Any]]] = None
) -> DocumentSourceClassifier:
    """
    יוצר מסווג מקורות לחקירה.
    
    Args:
        examined_witness_name: שם העד הנחקר
        examined_witness_party: צד העד (plaintiff/defendant)
        documents: רשימת מסמכים עם מטא-דאטה
    
    Returns:
        DocumentSourceClassifier מוכן לשימוש
    """
    party_role = PartyRole.PLAINTIFF if examined_witness_party == 'plaintiff' else PartyRole.DEFENDANT
    
    doc_metadata = []
    if documents:
        for doc in documents:
            doc_metadata.append(DocumentMetadata(
                doc_id=doc.get('id', ''),
                doc_name=doc.get('name', ''),
                doc_type=doc.get('type', ''),
                party_role=PartyRole(doc.get('party', 'unknown')),
                party_name=doc.get('party_name'),
                witness_name=doc.get('witness_name'),
                date=doc.get('date'),
                is_examined_witness=doc.get('is_examined_witness', False),
            ))
    
    return DocumentSourceClassifier(
        examined_witness_name=examined_witness_name,
        examined_witness_party=party_role,
        documents_metadata=doc_metadata,
    )


def classify_contradiction_sources(
    classifier: DocumentSourceClassifier,
    claim1_doc_id: Optional[str],
    claim1_doc_name: Optional[str],
    claim1_speaker: Optional[str],
    claim1_speaker_role: Optional[str],
    claim1_speaker_mode: Optional[str],
    claim2_doc_id: Optional[str],
    claim2_doc_name: Optional[str],
    claim2_speaker: Optional[str],
    claim2_speaker_role: Optional[str],
    claim2_speaker_mode: Optional[str],
) -> CrossExamSourceContext:
    """
    מסווג את מקורות שתי הטענות בסתירה.
    
    Returns:
        CrossExamSourceContext עם מידע על המקורות והגישה האסטרטגית
    """
    source1 = classifier.classify_claim_source(
        claim_text="",  # לא משתמשים בטקסט כרגע
        doc_id=claim1_doc_id,
        doc_name=claim1_doc_name,
        speaker=claim1_speaker,
        speaker_role=claim1_speaker_role,
        speaker_mode=claim1_speaker_mode,
    )
    
    source2 = classifier.classify_claim_source(
        claim_text="",
        doc_id=claim2_doc_id,
        doc_name=claim2_doc_name,
        speaker=claim2_speaker,
        speaker_role=claim2_speaker_role,
        speaker_mode=claim2_speaker_mode,
    )
    
    return CrossExamSourceContext(
        examined_witness_name=classifier.examined_witness_name or "",
        examined_witness_party=classifier.examined_witness_party,
        contradiction_claim1_source=source1,
        contradiction_claim2_source=source2,
    )
