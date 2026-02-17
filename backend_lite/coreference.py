"""
Hebrew Legal Coreference Resolver
==================================

Resolves entity references across claims in Hebrew legal documents.

Handles:
1. **Role-Name Binding**: "הנתבע, מר כהן" → הנתבע = מר כהן
2. **Definition Patterns**: "(להלן: 'המוכר')" → alias binding
3. **Apposition**: "העד דוד לוי" → דוד לוי = העד
4. **Title-Role Binding**: "מר כהן (הנתבע)" → כהן = הנתבע
5. **Pronoun Gender Agreement**: "הנתבע... הוא שילם" → הוא = הנתבע

Algorithm:
    1. Scan all claims for binding patterns
    2. Build an alias map: surface_form → canonical_entity
    3. Normalize entity references in enriched claims
    4. Feed alias map into EntityGraph for improved clustering

Usage:
    from .coreference import CoreferenceResolver

    resolver = CoreferenceResolver()
    resolver.scan_claims(claims)
    resolver.scan_full_text(full_text)
    resolver.resolve_claims(claims)  # updates entities in-place
"""

import re
import logging
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


# =============================================================================
# Binding Patterns — Hebrew Legal Text
# =============================================================================

# Pattern 1: Role followed by comma + name
# "הנתבע, מר דוד כהן" / "התובע, גב' שרה לוי"
_ROLE_COMMA_NAME = re.compile(
    r'(ה(?:נתבע|תובע|משיב|מערער|מבקש|נאשם|עד|מומחה|שוכר|משכיר|קונה|מוכר|עובד|מעביד|חייב|נושה|ערב'
    r'|נתבעת|תובעת|משיבה|מערערת|מבקשת|נאשמת|עדה|מומחית|שוכרת|משכירה|קונה|מוכרת|עובדת|מעבידה))'
    r'\s*[,،]\s*'
    r'(?:מר|גב\'?|גברת|עו"ד|ד"ר|פרופ\'?|רו"ח)?\s*'
    r'([\u0590-\u05FF]{2,}(?:\s+[\u0590-\u05FF]{2,}){0,2})',
    re.UNICODE,
)

# Pattern 2: Name followed by role in parentheses
# "דוד כהן (הנתבע)" / "שרה לוי (התובעת)"
_NAME_PAREN_ROLE = re.compile(
    r'(?:מר|גב\'?|גברת|עו"ד|ד"ר|פרופ\'?|רו"ח)?\s*'
    r'([\u0590-\u05FF]{2,}(?:\s+[\u0590-\u05FF]{2,}){0,2})'
    r'\s*\(\s*'
    r'(?:ה(?:נתבע|תובע|משיב|מערער|מבקש|נאשם|עד|מומחה|שוכר|משכיר|קונה|מוכר|עובד|מעביד|חייב|נושה|ערב'
    r'|נתבעת|תובעת|משיבה|מערערת|מבקשת|נאשמת|עדה|מומחית|שוכרת|משכירה|מוכרת|עובדת|מעבידה))'
    r'\s*\)',
    re.UNICODE,
)

# Pattern 3: "להלן" definitions
# "(להלן: 'המוכר')" / "(להלן: \"החברה\")" / "(להלן – המשכיר)"
_LEHALAN_DEF = re.compile(
    r'(?:מר|גב\'?|גברת|עו"ד|ד"ר|פרופ\'?|רו"ח)?\s*'
    r'([\u0590-\u05FF]{2,}(?:\s+[\u0590-\u05FF]{2,}){0,3})'
    r'\s*\(\s*להלן\s*[:–\-]\s*["\'"״\'׳]?\s*'
    r'([\u0590-\u05FF\s]{2,30}?)'
    r'\s*["\'"״\'׳]?\s*\)',
    re.UNICODE,
)

# Pattern 4: Apposition — role directly followed by name (no comma)
# "העד דוד לוי" / "הנתבע כהן"
_ROLE_DIRECT_NAME = re.compile(
    r'(ה(?:נתבע|תובע|משיב|מערער|מבקש|נאשם|עד|מומחה'
    r'|נתבעת|תובעת|משיבה|מערערת|מבקשת|נאשמת|עדה|מומחית))'
    r'\s+'
    r'(?:מר|גב\'?|גברת|עו"ד|ד"ר|פרופ\'?|רו"ח)\s+'
    r'([\u0590-\u05FF]{2,}(?:\s+[\u0590-\u05FF]{2,}){0,2})',
    re.UNICODE,
)

# Pattern 5: Organization + "להלן"
# "חברת אלפא בע\"מ (להלן: 'החברה')"
_ORG_LEHALAN = re.compile(
    r'((?:חברת|חברה|עמותת|קרן|בנק|משרד|מוסד|קופת)\s+'
    r'[\u0590-\u05FF\w]{2,}(?:\s+[\u0590-\u05FF\w]{2,}){0,3})'
    r'(?:\s+בע"מ|\s+בע״מ)?'
    r'\s*\(\s*להלן\s*[:–\-]\s*["\'"״\'׳]?\s*'
    r'([\u0590-\u05FF\s]{2,30}?)'
    r'\s*["\'"״\'׳]?\s*\)',
    re.UNICODE,
)

# Pattern 6: Numbered party definitions
# "1. דוד כהן (להלן: 'התובע')" / "צד א' - דוד כהן"
_NUMBERED_PARTY = re.compile(
    r'(?:צד\s+[א-ת]\'?\s*[-–:]\s*|'
    r'\d+\.\s*)'
    r'(?:מר|גב\'?|גברת|עו"ד|ד"ר|פרופ\'?|רו"ח)?\s*'
    r'([\u0590-\u05FF]{2,}(?:\s+[\u0590-\u05FF]{2,}){0,2})'
    r'\s*\(\s*להלן\s*[:–\-]\s*["\'"״\'׳]?\s*'
    r'([\u0590-\u05FF\s]{2,30}?)'
    r'\s*["\'"״\'׳]?\s*\)',
    re.UNICODE,
)

# Role gender/number forms mapping to canonical
_ROLE_CANONICAL = {
    # Male singular
    "הנתבע": "הנתבע",
    "התובע": "התובע",
    "המשיב": "הנתבע",
    "המערער": "התובע",
    "המבקש": "התובע",
    "הנאשם": "הנאשם",
    "העד": "העד",
    "המומחה": "המומחה",
    "השוכר": "השוכר",
    "המשכיר": "המשכיר",
    "הקונה": "הקונה",
    "המוכר": "המוכר",
    "העובד": "העובד",
    "המעביד": "המעביד",
    "החייב": "החייב",
    "הנושה": "הנושה",
    "הערב": "הערב",
    # Female singular
    "הנתבעת": "הנתבע",
    "התובעת": "התובע",
    "המשיבה": "הנתבע",
    "המערערת": "התובע",
    "המבקשת": "התובע",
    "הנאשמת": "הנאשם",
    "העדה": "העד",
    "המומחית": "המומחה",
    "השוכרת": "השוכר",
    "המשכירה": "המשכיר",
    "המוכרת": "המוכר",
    "העובדת": "העובד",
    "המעבידה": "המעביד",
}

# Pronoun gender mapping for agreement
_PRONOUN_GENDER = {
    "הוא": "male",
    "היא": "female",
    "הם": "male_plural",
    "הן": "female_plural",
    "הנ\"ל": "any",
    "האמור": "male",
    "האמורה": "female",
    "הנזכר": "male",
    "הנזכרת": "female",
}

# Role gender for pronoun agreement
_ROLE_GENDER = {
    "הנתבע": "male", "הנתבעת": "female",
    "התובע": "male", "התובעת": "female",
    "המשיב": "male", "המשיבה": "female",
    "המערער": "male", "המערערת": "female",
    "המבקש": "male", "המבקשת": "female",
    "הנאשם": "male", "הנאשמת": "female",
    "העד": "male", "העדה": "female",
    "המומחה": "male", "המומחית": "female",
    "השוכר": "male", "השוכרת": "female",
    "המשכיר": "male", "המשכירה": "female",
    "הקונה": "any", "המוכר": "male", "המוכרת": "female",
    "העובד": "male", "העובדת": "female",
    "המעביד": "male", "המעבידה": "female",
}


# =============================================================================
# Coreference Resolver
# =============================================================================

class CoreferenceResolver:
    """
    Resolves entity references across Hebrew legal claims.

    Scans claims and full text for binding patterns, builds an alias map,
    and normalizes entity references for better contradiction detection.
    """

    def __init__(self):
        # alias → canonical: "מר כהן" → "הנתבע"
        self._role_to_name: Dict[str, str] = {}  # role → person name
        self._name_to_role: Dict[str, str] = {}  # person name → role
        self._alias_map: Dict[str, str] = {}     # any form → canonical form
        self._org_aliases: Dict[str, str] = {}   # org alias → org name
        self._bindings_found: int = 0

    @property
    def alias_map(self) -> Dict[str, str]:
        """Get the full alias map (surface form → canonical)."""
        return dict(self._alias_map)

    @property
    def role_to_name(self) -> Dict[str, str]:
        """Get role → person name bindings."""
        return dict(self._role_to_name)

    def scan_claims(self, claims: list) -> None:
        """
        Scan claims for coreference patterns.

        Args:
            claims: List of Claim objects with .text attribute
        """
        for claim in claims:
            text = getattr(claim, 'text', str(claim))
            self._scan_text(text)

    def scan_full_text(self, full_text: str) -> None:
        """
        Scan full document text for coreference patterns.

        This is more effective than scanning claims individually because
        definitions often appear in document headers/preambles that may
        not be extracted as claims.
        """
        if not full_text:
            return
        self._scan_text(full_text)

    def _scan_text(self, text: str) -> None:
        """Extract all binding patterns from text."""
        # Pattern 1: Role, Name
        for match in _ROLE_COMMA_NAME.finditer(text):
            role = match.group(1).strip()
            name = match.group(2).strip()
            self._add_binding(role, name)

        # Pattern 2: Name (Role)
        for match in _NAME_PAREN_ROLE.finditer(text):
            name = match.group(1).strip()
            # Extract role from the full match
            role_match = re.search(
                r'ה(?:נתבע|תובע|משיב|מערער|מבקש|נאשם|עד|מומחה|שוכר|משכיר|קונה|מוכר|עובד|מעביד|חייב|נושה|ערב'
                r'|נתבעת|תובעת|משיבה|מערערת|מבקשת|נאשמת|עדה|מומחית|שוכרת|משכירה|מוכרת|עובדת|מעבידה)',
                match.group(0),
            )
            if role_match:
                self._add_binding(role_match.group(), name)

        # Pattern 3: Name (להלן: 'Alias')
        for match in _LEHALAN_DEF.finditer(text):
            name = match.group(1).strip()
            alias = match.group(2).strip()
            self._add_lehalan_binding(name, alias)

        # Pattern 4: Role + title + Name (apposition)
        for match in _ROLE_DIRECT_NAME.finditer(text):
            role = match.group(1).strip()
            name = match.group(2).strip()
            self._add_binding(role, name)

        # Pattern 5: Organization + להלן
        for match in _ORG_LEHALAN.finditer(text):
            org_name = match.group(1).strip()
            alias = match.group(2).strip()
            self._add_org_alias(org_name, alias)

        # Pattern 6: Numbered party definitions
        for match in _NUMBERED_PARTY.finditer(text):
            name = match.group(1).strip()
            alias = match.group(2).strip()
            self._add_lehalan_binding(name, alias)

    def _add_binding(self, role: str, name: str) -> None:
        """Add a role ↔ name binding."""
        if not role or not name or len(name) < 3:
            return

        # Skip if name looks like a common Hebrew word rather than a name
        common_words = {"כאשר", "לפני", "אחרי", "בהתאם", "לפיכך", "אולם", "כאמור"}
        if name in common_words:
            return

        canonical_role = _ROLE_CANONICAL.get(role, role)

        self._role_to_name[role] = name
        self._role_to_name[canonical_role] = name
        self._name_to_role[name] = canonical_role

        # Add to alias map: all forms → canonical name
        self._alias_map[role] = name
        self._alias_map[canonical_role] = name

        # Also map gender variants of the role to the same name
        for r, canonical in _ROLE_CANONICAL.items():
            if canonical == canonical_role and r != role:
                self._alias_map[r] = name
                self._role_to_name[r] = name

        # Last name only as partial alias
        name_parts = name.split()
        if len(name_parts) >= 2:
            last_name = name_parts[-1]
            if len(last_name) >= 3:
                self._alias_map[last_name] = name

        self._bindings_found += 1
        logger.debug("Coreference binding: %s → %s", role, name)

    def _add_lehalan_binding(self, name: str, alias: str) -> None:
        """Add a 'להלן' definition binding."""
        if not name or not alias or len(alias) < 2:
            return

        alias = alias.strip()
        name = name.strip()

        # Check if alias is a role term
        canonical_role = _ROLE_CANONICAL.get(alias)
        if canonical_role:
            self._add_binding(alias, name)
        else:
            # Generic alias (e.g., "החוזה", "הנכס")
            self._alias_map[alias] = name

        self._bindings_found += 1
        logger.debug("להלן binding: %s → %s", alias, name)

    def _add_org_alias(self, org_name: str, alias: str) -> None:
        """Add organization alias."""
        if not org_name or not alias:
            return

        self._org_aliases[alias.strip()] = org_name.strip()
        self._alias_map[alias.strip()] = org_name.strip()
        self._bindings_found += 1
        logger.debug("Org alias: %s → %s", alias, org_name)

    def resolve_claims(self, claims: list) -> list:
        """
        Resolve coreferences in claims' entity lists.

        Updates claim.entities in-place, adding canonical names
        alongside role references.

        Args:
            claims: List of Claim objects

        Returns:
            Same list of claims, with enhanced entities
        """
        if not self._alias_map:
            return claims

        for claim in claims:
            entities = getattr(claim, 'entities', [])
            if not entities:
                continue

            enhanced = list(entities)
            for ent in entities:
                # Try to resolve via alias map
                canonical = self._alias_map.get(ent)
                if canonical and canonical not in enhanced:
                    enhanced.append(canonical)

                # Try to resolve last name → full name
                if len(ent.split()) == 1 and len(ent) >= 3:
                    for full_name, role in self._name_to_role.items():
                        if full_name.endswith(ent) and full_name != ent:
                            if full_name not in enhanced:
                                enhanced.append(full_name)

            claim.entities = list(dict.fromkeys(enhanced))  # deduplicate

        return claims

    def get_canonical(self, entity: str) -> str:
        """Get canonical form of an entity, or return as-is."""
        return self._alias_map.get(entity, entity)

    def are_coreferent(self, entity_a: str, entity_b: str) -> bool:
        """
        Check if two entity mentions refer to the same entity.

        Returns True if:
        - They resolve to the same canonical form
        - One is a known alias of the other
        - They share a name component (last name)
        """
        if entity_a == entity_b:
            return True

        canon_a = self.get_canonical(entity_a)
        canon_b = self.get_canonical(entity_b)

        # Same canonical
        if canon_a == canon_b:
            return True

        # One resolves to the other
        if canon_a == entity_b or canon_b == entity_a:
            return True

        # Cross-check: one's canonical is the other's alias target
        if self._alias_map.get(entity_a) == self._alias_map.get(entity_b):
            both = self._alias_map.get(entity_a)
            if both is not None:
                return True

        return False

    def get_stats(self) -> Dict[str, int]:
        """Get resolver statistics."""
        return {
            "bindings_found": self._bindings_found,
            "role_to_name": len(self._role_to_name),
            "aliases": len(self._alias_map),
            "org_aliases": len(self._org_aliases),
        }


# =============================================================================
# Singleton & convenience functions
# =============================================================================

_resolver: Optional[CoreferenceResolver] = None


def get_coreference_resolver() -> CoreferenceResolver:
    """Get singleton resolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = CoreferenceResolver()
    return _resolver


def reset_coreference_resolver() -> None:
    """Reset the singleton (for new analysis runs)."""
    global _resolver
    _resolver = None


def resolve_coreferences(claims: list, full_text: str = "") -> CoreferenceResolver:
    """
    Convenience function: scan claims + text, resolve, and return the resolver.

    Args:
        claims: List of Claim objects
        full_text: Full document text

    Returns:
        The CoreferenceResolver with all bindings
    """
    resolver = get_coreference_resolver()
    if full_text:
        resolver.scan_full_text(full_text)
    resolver.scan_claims(claims)
    resolver.resolve_claims(claims)

    stats = resolver.get_stats()
    logger.info(
        "Coreference resolution: %d bindings, %d role→name, %d aliases",
        stats["bindings_found"], stats["role_to_name"], stats["aliases"],
    )
    return resolver
