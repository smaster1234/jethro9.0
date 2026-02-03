"""
Entity Resolution Graph for Cross-Document Analysis
====================================================

Builds a unified entity graph across all claims/documents to enable:

1. **Coreference Resolution**: "הנתבע" = "מר כהן" = "דוד כהן" = "הוא"
2. **Cross-Document Linking**: Same entity mentioned in different documents
3. **Subject Matching**: Determines if two claims discuss the same subject/event
4. **Entity-Aware Filtering**: Only compare claims about the same entities

Algorithm:
    1. Extract named entities from each claim (names, dates, amounts, places)
    2. Fuzzy-match entities across claims using Hebrew-aware similarity
    3. Build graph: entity nodes ↔ claim nodes
    4. For any pair of claims, compute entity overlap score

Usage:
    from entity_graph import EntityGraph

    graph = EntityGraph()
    graph.build(claims)
    overlap = graph.entity_overlap(claim_a, claim_b)
    shared = graph.shared_entities(claim_a, claim_b)
"""

import re
import logging
from typing import List, Dict, Set, Tuple, Optional, Any
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


# =============================================================================
# Entity Types
# =============================================================================

class EntityType:
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    DATE = "date"
    AMOUNT = "amount"
    DOCUMENT = "document"
    EVENT = "event"
    ROLE = "role"


@dataclass
class Entity:
    """A normalized entity extracted from text."""
    canonical: str          # Normalized form
    entity_type: str        # One of EntityType
    mentions: Set[str] = field(default_factory=set)  # All surface forms
    claim_ids: Set[str] = field(default_factory=set)  # Claims mentioning this entity
    doc_ids: Set[str] = field(default_factory=set)    # Documents mentioning this entity


# =============================================================================
# Hebrew Entity Extraction Patterns
# =============================================================================

# Title/prefix patterns to strip for normalization
_TITLE_STRIP = re.compile(
    r'^(?:מר|גב|גברת|עו"ד|ד"ר|פרופ|רו"ח|שופט|שופטת|כב|כבוד)\s+',
    re.UNICODE,
)

# Role patterns that should be recognized as entity references
_ROLE_PATTERNS = re.compile(
    r'(?:הנתבע|התובע|המשיב|המערער|המבקש|המשיבה|התובעת|הנתבעת|'
    r'הנאשם|הנאשמת|העד|העדה|המומחה|השוכר|המשכיר|הקונה|המוכר|'
    r'העובד|המעביד|החייב|הנושה|הערב)',
    re.UNICODE,
)

# Person name pattern: Two+ Hebrew words, each 2+ characters
_PERSON_PATTERN = re.compile(
    r'(?:מר|גב|גברת|עו"ד|ד"ר|פרופ|רו"ח)?\s*'
    r'([\u0590-\u05FF]{2,})\s+([\u0590-\u05FF]{2,}(?:\s+[\u0590-\u05FF]{2,})?)',
    re.UNICODE,
)

# Amount pattern (simplified)
_AMOUNT_PATTERN = re.compile(
    r'(?:₪|ש"ח|שקל|דולר|\$)\s*[\d,]+(?:\.\d+)?|'
    r'[\d,]+(?:\.\d+)?\s*(?:₪|ש"ח|שקל|שקלים|דולר|דולרים|\$)',
    re.UNICODE,
)

# Date pattern (DD/MM/YYYY or Hebrew month)
_DATE_PATTERN = re.compile(
    r'\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|'
    r'\d{1,2}\s*ב?(?:ינואר|פברואר|מרץ|מרס|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s*\d{4}',
    re.UNICODE,
)

# Location indicators
_LOCATION_PATTERN = re.compile(
    r'(?:ברחוב|בכביש|בעיר|ביישוב|בבית|במשרד|בסניף|בכתובת)\s+'
    r'([\u0590-\u05FF\w\s]{2,30})',
    re.UNICODE,
)

# Document type indicators
_DOCUMENT_PATTERN = re.compile(
    r'(?:הסכם|חוזה|מסמך|מכתב|תצהיר|כתב\s+(?:תביעה|הגנה|ערעור)|'
    r'פרוטוקול|חשבונית|קבלה|אישור|הודעה)\s*'
    r'(?:מיום\s+[\d/.\-]+|מס[\'׳]\s*\d+)?',
    re.UNICODE,
)

# Event indicators
_EVENT_PATTERN = re.compile(
    r'(?:הפגישה|האירוע|התאונה|החתימה|ההסכם|המשא\s*ומתן|'
    r'הדיון|הישיבה|הבדיקה|הביקור|העסקה|ההעברה|התשלום|'
    r'הפיטורין|ההתפטרות|המינוי)',
    re.UNICODE,
)

# Pronoun patterns for coreference
_PRONOUN_MAP = {
    'הוא': 'male_singular',
    'היא': 'female_singular',
    'הם': 'male_plural',
    'הן': 'female_plural',
    'הנ"ל': 'aforementioned',
    'האמור': 'aforementioned',
    'הנזכר': 'aforementioned',
}


class EntityGraph:
    """
    Cross-document entity resolution graph.

    Extracts entities from claims, merges duplicates using fuzzy matching,
    resolves pronouns and role references to named entities, and provides
    entity-overlap scoring for claim pairs.
    """

    def __init__(
        self,
        name_similarity_threshold: float = 0.75,
        merge_threshold: float = 0.80,
    ):
        self.name_threshold = name_similarity_threshold
        self.merge_threshold = merge_threshold

        # Entity storage
        self._entities: Dict[str, Entity] = {}  # canonical -> Entity
        self._claim_entities: Dict[str, Set[str]] = defaultdict(set)  # claim_id -> set of entity canonicals
        self._built = False

        # Coreference state: maps pronoun/role mentions to resolved entity canonicals
        self._coref_map: Dict[str, str] = {}  # "הנתבע" -> "דוד כהן"

    def build(self, claims: list) -> None:
        """
        Build entity graph from a list of claims.

        Args:
            claims: List of Claim objects with .id, .text, and optionally .doc_id
        """
        self._entities.clear()
        self._claim_entities.clear()
        self._coref_map.clear()

        # Step 1: Extract entities from each claim
        raw_entities: List[Tuple[str, str, str, str]] = []  # (claim_id, doc_id, entity_text, entity_type)

        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            doc_id = getattr(claim, 'doc_id', '')
            text = getattr(claim, 'text', str(claim))

            extracted = self._extract_entities(text)
            for entity_text, entity_type in extracted:
                raw_entities.append((cid, doc_id, entity_text, entity_type))

        # Step 2: Cluster and merge entities
        self._cluster_entities(raw_entities)

        # Step 3: Resolve coreferences — link pronouns/roles to named entities
        self._resolve_coreferences(claims)

        # Step 4: Apply coreference — extend claim entity sets with resolved references
        self._apply_coreferences(claims)

        # Step 5: Build claim -> entity mapping
        for canonical, entity in self._entities.items():
            for cid in entity.claim_ids:
                self._claim_entities[cid].add(canonical)

        self._built = True

        # Stats
        cross_doc = sum(1 for e in self._entities.values() if len(e.doc_ids) > 1)
        coref_count = len(self._coref_map)
        logger.info(
            "Entity graph built: %d entities (%d cross-document), %d coreferences, %d claims",
            len(self._entities), cross_doc, coref_count, len(self._claim_entities),
        )

    def entity_overlap(self, claim_a, claim_b) -> float:
        """
        Compute entity overlap score between two claims (0-1).

        Returns the Jaccard similarity of their entity sets.
        """
        id_a = getattr(claim_a, 'id', str(id(claim_a)))
        id_b = getattr(claim_b, 'id', str(id(claim_b)))

        ents_a = self._claim_entities.get(id_a, set())
        ents_b = self._claim_entities.get(id_b, set())

        if not ents_a and not ents_b:
            return 0.5  # Unknown - don't penalize

        if not ents_a or not ents_b:
            return 0.3  # One side has no entities

        intersection = ents_a & ents_b
        union = ents_a | ents_b

        return len(intersection) / len(union) if union else 0.0

    def shared_entities(self, claim_a, claim_b) -> List[Entity]:
        """
        Get shared entities between two claims.
        """
        id_a = getattr(claim_a, 'id', str(id(claim_a)))
        id_b = getattr(claim_b, 'id', str(id(claim_b)))

        ents_a = self._claim_entities.get(id_a, set())
        ents_b = self._claim_entities.get(id_b, set())

        shared = ents_a & ents_b
        return [self._entities[canonical] for canonical in shared if canonical in self._entities]

    def same_subject_score(self, claim_a, claim_b) -> float:
        """
        Compute probability that two claims discuss the same subject.

        Uses entity overlap weighted by entity types:
        - Shared PERSON entities: high weight (0.4)
        - Shared EVENT entities: high weight (0.3)
        - Shared DATE entities: medium weight (0.15)
        - Shared AMOUNT entities: medium weight (0.1)
        - Shared LOCATION entities: low weight (0.05)
        """
        id_a = getattr(claim_a, 'id', str(id(claim_a)))
        id_b = getattr(claim_b, 'id', str(id(claim_b)))

        ents_a = self._claim_entities.get(id_a, set())
        ents_b = self._claim_entities.get(id_b, set())

        if not ents_a and not ents_b:
            return 0.5  # Unknown

        shared = ents_a & ents_b
        if not shared:
            return 0.0

        type_weights = {
            EntityType.PERSON: 0.40,
            EntityType.EVENT: 0.30,
            EntityType.DATE: 0.15,
            EntityType.AMOUNT: 0.10,
            EntityType.LOCATION: 0.05,
            EntityType.DOCUMENT: 0.15,
            EntityType.ORGANIZATION: 0.20,
            EntityType.ROLE: 0.25,
        }

        score = 0.0
        max_possible = 0.0

        all_types_seen = set()
        for canonical in ents_a | ents_b:
            entity = self._entities.get(canonical)
            if entity:
                all_types_seen.add(entity.entity_type)

        for etype in all_types_seen:
            weight = type_weights.get(etype, 0.1)
            max_possible += weight

            # Count shared entities of this type
            shared_of_type = sum(
                1 for c in shared
                if self._entities.get(c) and self._entities[c].entity_type == etype
            )
            total_of_type = sum(
                1 for c in (ents_a | ents_b)
                if self._entities.get(c) and self._entities[c].entity_type == etype
            )

            if total_of_type > 0:
                score += weight * (shared_of_type / total_of_type)

        return score / max_possible if max_possible > 0 else 0.0

    def get_entity(self, canonical: str) -> Optional[Entity]:
        """Get entity by canonical name."""
        return self._entities.get(canonical)

    def get_claim_entities(self, claim_id: str) -> Set[str]:
        """Get entity canonicals for a claim."""
        return self._claim_entities.get(claim_id, set())

    # =========================================================================
    # Entity Extraction
    # =========================================================================

    def _extract_entities(self, text: str) -> List[Tuple[str, str]]:
        """
        Extract entities from text. Returns (entity_text, entity_type) tuples.

        Uses regex patterns as primary extraction, supplemented by QA model
        for speaker/subject identification when available.
        """
        entities = []

        # Roles (הנתבע, התובע, etc.)
        for match in _ROLE_PATTERNS.finditer(text):
            entities.append((match.group(), EntityType.ROLE))

        # Person names
        for match in _PERSON_PATTERN.finditer(text):
            full_name = match.group().strip()
            cleaned = _TITLE_STRIP.sub('', full_name).strip()
            if cleaned and len(cleaned) >= 4:
                entities.append((cleaned, EntityType.PERSON))

        # QA-based entity supplementation: extract entities regex might miss
        if not any(e[1] == EntityType.PERSON for e in entities):
            try:
                from .legal_qa import get_legal_qa
                qa = get_legal_qa()
                # Ask QA who is being discussed in the text
                for question in ["מי ביצע את הפעולה?", "על מי מדובר?"]:
                    result = qa.answer(question, text, min_confidence=0.30)
                    if result and len(result.answer) >= 3:
                        # Check it's not a role we already captured
                        answer = result.answer.strip()
                        existing_texts = {e[0] for e in entities}
                        if answer not in existing_texts:
                            entities.append((answer, EntityType.PERSON))
                        break
            except Exception:
                pass

        # Amounts
        for match in _AMOUNT_PATTERN.finditer(text):
            entities.append((match.group().strip(), EntityType.AMOUNT))

        # Dates
        for match in _DATE_PATTERN.finditer(text):
            entities.append((match.group().strip(), EntityType.DATE))

        # Locations
        for match in _LOCATION_PATTERN.finditer(text):
            loc = match.group(1).strip() if match.groups() else match.group().strip()
            if loc and len(loc) >= 3:
                entities.append((loc, EntityType.LOCATION))

        # Documents
        for match in _DOCUMENT_PATTERN.finditer(text):
            entities.append((match.group().strip(), EntityType.DOCUMENT))

        # Events
        for match in _EVENT_PATTERN.finditer(text):
            entities.append((match.group().strip(), EntityType.EVENT))

        return entities

    # =========================================================================
    # Entity Clustering & Merging
    # =========================================================================

    def _cluster_entities(self, raw_entities: List[Tuple[str, str, str, str]]) -> None:
        """
        Cluster raw entity mentions into canonical entities using fuzzy matching.
        """
        # Group by entity type first (only merge within same type)
        by_type: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
        for cid, doc_id, entity_text, entity_type in raw_entities:
            by_type[entity_type].append((cid, doc_id, entity_text))

        for entity_type, mentions in by_type.items():
            # Build clusters using greedy agglomerative approach
            clusters: List[List[Tuple[str, str, str]]] = []

            for mention in mentions:
                cid, doc_id, text = mention
                normalized = self._normalize_entity(text, entity_type)
                merged = False

                for cluster in clusters:
                    # Check if this mention matches any existing cluster member
                    representative = self._normalize_entity(cluster[0][2], entity_type)
                    similarity = self._entity_similarity(normalized, representative, entity_type)

                    if similarity >= self.merge_threshold:
                        cluster.append(mention)
                        merged = True
                        break

                if not merged:
                    clusters.append([mention])

            # Convert clusters to Entity objects
            for cluster in clusters:
                # Choose the longest mention as canonical
                canonical_mention = max(cluster, key=lambda x: len(x[2]))[2]
                canonical = self._normalize_entity(canonical_mention, entity_type)

                if canonical in self._entities:
                    # Merge with existing entity
                    entity = self._entities[canonical]
                else:
                    entity = Entity(
                        canonical=canonical,
                        entity_type=entity_type,
                    )
                    self._entities[canonical] = entity

                for cid, doc_id, text in cluster:
                    entity.mentions.add(text)
                    entity.claim_ids.add(cid)
                    if doc_id:
                        entity.doc_ids.add(doc_id)

    def _normalize_entity(self, text: str, entity_type: str) -> str:
        """Normalize entity text for comparison."""
        text = text.strip()

        if entity_type == EntityType.PERSON:
            # Strip titles
            text = _TITLE_STRIP.sub('', text).strip()
            # Normalize whitespace
            text = ' '.join(text.split())

        elif entity_type == EntityType.AMOUNT:
            # Normalize to digits only
            text = re.sub(r'[^\d.]', '', text)

        elif entity_type == EntityType.DATE:
            # Normalize separators
            text = re.sub(r'[/.\-]', '/', text)

        return text.strip()

    def _entity_similarity(self, a: str, b: str, entity_type: str) -> float:
        """
        Compute similarity between two entity strings.

        Uses type-specific strategies:
        - PERSON: Fuzzy string matching with Hebrew awareness
        - AMOUNT: Numeric comparison
        - DATE: Date normalization and comparison
        - Others: SequenceMatcher ratio
        """
        if not a or not b:
            return 0.0

        if a == b:
            return 1.0

        if entity_type == EntityType.PERSON:
            return self._person_similarity(a, b)

        if entity_type == EntityType.AMOUNT:
            return self._amount_similarity(a, b)

        if entity_type == EntityType.ROLE:
            # Roles are exact match (הנתבע != התובע)
            return 1.0 if a == b else 0.0

        # Default: SequenceMatcher
        return SequenceMatcher(None, a, b).ratio()

    def _person_similarity(self, a: str, b: str) -> float:
        """
        Hebrew-aware person name similarity.

        Handles:
        - Reversed names: "דוד כהן" ↔ "כהן דוד"
        - Partial names: "דוד כהן" ↔ "כהן"
        - Abbreviations: "ד. כהן" ↔ "דוד כהן"
        """
        # Try direct match
        ratio = SequenceMatcher(None, a, b).ratio()

        # Try reversed word order
        a_words = a.split()
        b_words = b.split()
        if len(a_words) > 1 and len(b_words) > 1:
            reversed_a = ' '.join(reversed(a_words))
            reversed_ratio = SequenceMatcher(None, reversed_a, b).ratio()
            ratio = max(ratio, reversed_ratio)

        # Try partial match (last name only)
        if len(a_words) >= 2 and len(b_words) >= 1:
            last_name_a = a_words[-1]
            for word in b_words:
                if SequenceMatcher(None, last_name_a, word).ratio() > 0.85:
                    ratio = max(ratio, 0.7)  # Partial match

        if len(b_words) >= 2 and len(a_words) >= 1:
            last_name_b = b_words[-1]
            for word in a_words:
                if SequenceMatcher(None, last_name_b, word).ratio() > 0.85:
                    ratio = max(ratio, 0.7)

        return ratio

    def _amount_similarity(self, a: str, b: str) -> float:
        """Numeric amount similarity."""
        try:
            val_a = float(a.replace(',', ''))
            val_b = float(b.replace(',', ''))
            if val_a == val_b:
                return 1.0
            if max(val_a, val_b) == 0:
                return 0.0
            # Close amounts are the "same entity"
            diff_ratio = abs(val_a - val_b) / max(val_a, val_b)
            if diff_ratio < 0.01:  # Within 1%
                return 0.95
            return 0.0  # Different amounts are different entities
        except ValueError:
            return SequenceMatcher(None, a, b).ratio()

    # =========================================================================
    # Coreference Resolution
    # =========================================================================

    def _resolve_coreferences(self, claims: list) -> None:
        """
        Resolve coreferences: link role mentions (הנתבע, התובע) and pronouns
        to specific named PERSON entities.

        Strategy:
        1. For each claim, if it contains both a ROLE and a PERSON → the person fills that role
        2. For each document, if one claim names the person and another uses the role → link
        3. Build global role→person mapping from document-level evidence
        """
        # Collect (doc_id -> role -> person) evidence
        doc_role_person: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))

        # First pass: find claims where ROLE and PERSON co-occur
        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            doc_id = getattr(claim, 'doc_id', '')
            text = getattr(claim, 'text', str(claim))

            extracted = self._extract_entities(text)
            roles_in_claim = [e[0] for e in extracted if e[1] == EntityType.ROLE]
            persons_in_claim = [e[0] for e in extracted if e[1] == EntityType.PERSON]

            # If exactly one role and at least one person in the same claim,
            # assume the person fills that role
            if len(roles_in_claim) == 1 and persons_in_claim:
                role = roles_in_claim[0]
                # Use the first person mentioned (most likely the subject)
                person = self._normalize_entity(persons_in_claim[0], EntityType.PERSON)
                doc_role_person[doc_id][role].add(person)

        # Also check for "X הוא הנתבע" / "הנתבע, מר X" patterns in raw text
        for claim in claims:
            doc_id = getattr(claim, 'doc_id', '')
            text = getattr(claim, 'text', str(claim))

            # Pattern: "הנתבע/התובע, מר/גברת <name>"
            coref_pattern = re.compile(
                r'(הנתבע|התובע|המשיב|המערער|המבקש|הנתבעת|התובעת|המשיבה)'
                r'[,\s]+(?:מר|גברת|גב)\s+'
                r'([\u0590-\u05FF]{2,}\s+[\u0590-\u05FF]{2,})',
                re.UNICODE,
            )
            for m in coref_pattern.finditer(text):
                role = m.group(1)
                person = self._normalize_entity(m.group(2), EntityType.PERSON)
                doc_role_person[doc_id][role].add(person)

        # Build global role -> person mapping (use most frequent mapping)
        global_role_person: Dict[str, str] = {}
        for doc_id, role_persons in doc_role_person.items():
            for role, persons in role_persons.items():
                if len(persons) == 1:
                    global_role_person[role] = next(iter(persons))
                else:
                    # Multiple persons for same role — don't resolve ambiguously
                    pass

        # Also collect across documents for roles consistently mapped
        all_role_persons: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for doc_id, role_persons in doc_role_person.items():
            for role, persons in role_persons.items():
                for person in persons:
                    all_role_persons[role][person] += 1

        for role, person_counts in all_role_persons.items():
            if role not in global_role_person:
                # Use majority vote
                best_person = max(person_counts, key=person_counts.get)
                if person_counts[best_person] >= 2 or len(person_counts) == 1:
                    global_role_person[role] = best_person

        self._coref_map = global_role_person
        if global_role_person:
            logger.info("Coreference resolved: %s", {k: v for k, v in global_role_person.items()})

    def _apply_coreferences(self, claims: list) -> None:
        """
        Apply resolved coreferences: for claims that mention a role (הנתבע),
        add the resolved person entity to that claim's entity set.
        """
        if not self._coref_map:
            return

        for claim in claims:
            cid = getattr(claim, 'id', str(id(claim)))
            text = getattr(claim, 'text', str(claim))

            for role_match in _ROLE_PATTERNS.finditer(text):
                role = role_match.group()
                if role in self._coref_map:
                    person_canonical = self._coref_map[role]
                    # Find or create the person entity
                    if person_canonical in self._entities:
                        self._entities[person_canonical].claim_ids.add(cid)
                    else:
                        # Create entity if needed
                        entity = Entity(
                            canonical=person_canonical,
                            entity_type=EntityType.PERSON,
                        )
                        entity.claim_ids.add(cid)
                        entity.mentions.add(role)
                        self._entities[person_canonical] = entity

            # Also resolve pronouns using closest antecedent heuristic
            for pronoun, gender in _PRONOUN_MAP.items():
                if pronoun in text:
                    # Find the closest PERSON entity in the same claim
                    extracted = self._extract_entities(text)
                    persons = [e[0] for e in extracted if e[1] == EntityType.PERSON]
                    if persons:
                        # Use the first person in the claim as the antecedent
                        person_canonical = self._normalize_entity(persons[0], EntityType.PERSON)
                        if person_canonical in self._entities:
                            self._entities[person_canonical].claim_ids.add(cid)


# =============================================================================
# Singleton
# =============================================================================

_graph: Optional[EntityGraph] = None


def get_entity_graph() -> EntityGraph:
    """Get singleton entity graph."""
    global _graph
    if _graph is None:
        _graph = EntityGraph()
    return _graph


def reset_entity_graph() -> None:
    """Reset the singleton (for new analysis runs)."""
    global _graph
    _graph = None
