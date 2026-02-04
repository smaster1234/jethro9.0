"""
מנוע אסטרטגי לחקירה נגדית - Strategic Cross-Examination Engine

מודול זה מיישם:
1. תורת משחקים (Game Theory) - Nash Equilibrium, Minimax
2. מודלי חיזוי תגובות (Predictive Response Models)
3. ניהול אי-ודאות (Uncertainty Management)
4. אופטימיזציה טקטית (Tactical Optimization)

המטרה: להפוך חקירה נגדית למשהו שמעבר ליכולת עורך דין אנושי
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any, Set
import math
import random
from collections import defaultdict


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class WitnessProfile(Enum):
    """פרופיל פסיכולוגי של עד"""
    COOPERATIVE = "cooperative"          # משתף פעולה, עלול להיות תמים
    DEFENSIVE = "defensive"              # מתגונן, חשדן
    HOSTILE = "hostile"                  # עוין, מתנגד
    EVASIVE = "evasive"                  # מתחמק, לא ישיר
    CONFIDENT = "confident"              # בטוח בעצמו, עלול להיות יהיר
    NERVOUS = "nervous"                  # עצבני, עלול לטעות תחת לחץ
    CALCULATED = "calculated"            # מחושב, זהיר בתשובות


class QuestionIntent(Enum):
    """כוונה אסטרטגית של שאלה"""
    ESTABLISH_BASELINE = "establish_baseline"      # קביעת קו בסיס
    BUILD_RAPPORT = "build_rapport"                # בניית אמון (לפני תקיפה)
    PROBE_WEAKNESS = "probe_weakness"              # בדיקת נקודת תורפה
    LOCK_TESTIMONY = "lock_testimony"              # נעילת עדות
    CREATE_CONTRADICTION = "create_contradiction"  # יצירת סתירה
    EXPLOIT_CONTRADICTION = "exploit_contradiction" # ניצול סתירה
    PSYCHOLOGICAL_PRESSURE = "psychological_pressure" # לחץ פסיכולוגי
    STRATEGIC_RETREAT = "strategic_retreat"        # נסיגה אסטרטגית
    SURPRISE_ATTACK = "surprise_attack"            # תקיפת הפתעה
    CLOSING_TRAP = "closing_trap"                  # מלכודת סגירה


class ResponsePrediction(Enum):
    """חיזוי תגובה אפשרית"""
    ADMIT = "admit"                      # יודה
    DENY = "deny"                        # יכחיש
    EVADE = "evade"                      # יתחמק
    QUALIFY = "qualify"                  # יסייג
    CONTRADICT_SELF = "contradict_self"  # יסתור את עצמו
    BECOME_HOSTILE = "become_hostile"    # יהפוך עוין
    BREAK_DOWN = "break_down"            # יישבר
    SURPRISE = "surprise"                # תגובה מפתיעה


@dataclass
class StrategicQuestion:
    """שאלה עם מטא-דאטה אסטרטגי"""
    question: str
    intent: QuestionIntent
    position: int                        # מיקום מומלץ בחקירה (0-100%)
    time_allocation: float               # זמן מומלץ בדקות
    risk_level: float                    # רמת סיכון (0-1)
    reward_potential: float              # פוטנציאל תגמול (0-1)
    
    # חיזויים
    predicted_responses: Dict[ResponsePrediction, float] = field(default_factory=dict)
    
    # תוכניות חלופיות
    followup_if_admit: Optional[str] = None
    followup_if_deny: Optional[str] = None
    followup_if_evade: Optional[str] = None
    
    # מטא-דאטה
    dependencies: List[int] = field(default_factory=list)  # שאלות שחייבות להישאל קודם
    blocks: List[int] = field(default_factory=list)        # שאלות שלא לשאול אם זו נשאלה
    
    # הערות אסטרטגיות
    strategic_notes: str = ""
    psychological_notes: str = ""


@dataclass
class ExaminationPlan:
    """תוכנית חקירה מלאה"""
    questions: List[StrategicQuestion]
    witness_profile: WitnessProfile
    total_time_minutes: float
    
    # ניתוח אסטרטגי
    critical_path: List[int]             # מסלול קריטי
    alternative_paths: List[List[int]]   # מסלולים חלופיים
    decision_points: Dict[int, Dict[ResponsePrediction, int]]  # נקודות החלטה
    
    # מדדים
    expected_value: float                # תוחלת ערך
    risk_score: float                    # ציון סיכון
    confidence_score: float              # ציון ביטחון
    
    # סיכום אסטרטגי
    strategy_summary: str = ""
    key_objectives: List[str] = field(default_factory=list)
    potential_pitfalls: List[str] = field(default_factory=list)


@dataclass
class GameState:
    """מצב המשחק הנוכחי"""
    questions_asked: List[int] = field(default_factory=list)
    responses_received: List[Tuple[int, ResponsePrediction]] = field(default_factory=list)
    witness_state: WitnessProfile = WitnessProfile.COOPERATIVE
    credibility_damage: float = 0.0      # נזק למהימנות (0-1)
    time_remaining: float = 30.0         # זמן שנותר בדקות
    momentum: float = 0.5                # מומנטום (0=נתבע, 1=תובע)


# =============================================================================
# GAME THEORY ENGINE
# =============================================================================

class GameTheoryEngine:
    """
    מנוע תורת משחקים לחקירה נגדית
    
    מיישם:
    - Nash Equilibrium לחיזוי אסטרטגיות אופטימליות
    - Minimax לתכנון worst-case
    - עץ החלטות דינמי
    """
    
    # מטריצת תשלומים (Payoff Matrix) - [שואל][עד]
    # ערכים: (תועלת לשואל, תועלת לעד)
    PAYOFF_MATRIX = {
        QuestionIntent.ESTABLISH_BASELINE: {
            ResponsePrediction.ADMIT: (0.3, 0.1),
            ResponsePrediction.DENY: (0.1, 0.2),
            ResponsePrediction.EVADE: (0.2, 0.3),
        },
        QuestionIntent.PROBE_WEAKNESS: {
            ResponsePrediction.ADMIT: (0.7, -0.3),
            ResponsePrediction.DENY: (0.2, 0.1),
            ResponsePrediction.EVADE: (0.4, 0.0),
            ResponsePrediction.CONTRADICT_SELF: (0.9, -0.5),
        },
        QuestionIntent.LOCK_TESTIMONY: {
            ResponsePrediction.ADMIT: (0.5, 0.0),
            ResponsePrediction.DENY: (0.3, 0.1),
            ResponsePrediction.QUALIFY: (0.2, 0.2),
        },
        QuestionIntent.CREATE_CONTRADICTION: {
            ResponsePrediction.ADMIT: (0.4, -0.1),
            ResponsePrediction.DENY: (0.6, -0.2),
            ResponsePrediction.CONTRADICT_SELF: (1.0, -0.7),
        },
        QuestionIntent.EXPLOIT_CONTRADICTION: {
            ResponsePrediction.ADMIT: (0.9, -0.5),
            ResponsePrediction.DENY: (0.5, -0.2),
            ResponsePrediction.EVADE: (0.7, -0.3),
            ResponsePrediction.BREAK_DOWN: (1.0, -0.8),
        },
        QuestionIntent.PSYCHOLOGICAL_PRESSURE: {
            ResponsePrediction.ADMIT: (0.6, -0.4),
            ResponsePrediction.BECOME_HOSTILE: (0.3, 0.1),
            ResponsePrediction.BREAK_DOWN: (0.8, -0.6),
        },
        QuestionIntent.SURPRISE_ATTACK: {
            ResponsePrediction.ADMIT: (0.8, -0.4),
            ResponsePrediction.CONTRADICT_SELF: (1.0, -0.6),
            ResponsePrediction.SURPRISE: (0.2, 0.3),
        },
        QuestionIntent.CLOSING_TRAP: {
            ResponsePrediction.ADMIT: (0.9, -0.5),
            ResponsePrediction.DENY: (0.7, -0.3),
            ResponsePrediction.CONTRADICT_SELF: (1.0, -0.8),
        },
    }
    
    @classmethod
    def calculate_nash_equilibrium(
        cls,
        intent: QuestionIntent,
        witness_profile: WitnessProfile
    ) -> Dict[ResponsePrediction, float]:
        """
        חישוב Nash Equilibrium - האסטרטגיה האופטימלית של העד
        
        מחזיר התפלגות הסתברויות לתגובות העד
        """
        payoffs = cls.PAYOFF_MATRIX.get(intent, {})
        if not payoffs:
            return {ResponsePrediction.EVADE: 1.0}
        
        # התאמה לפרופיל העד
        profile_adjustments = cls._get_profile_adjustments(witness_profile)
        
        # חישוב תועלת מותאמת לכל תגובה
        adjusted_utilities = {}
        for response, (attacker_payoff, defender_payoff) in payoffs.items():
            adjustment = profile_adjustments.get(response, 0.0)
            adjusted_utilities[response] = defender_payoff + adjustment
        
        # המרה להסתברויות (softmax)
        probabilities = cls._softmax(adjusted_utilities)
        
        return probabilities
    
    @classmethod
    def minimax_analysis(
        cls,
        questions: List[StrategicQuestion],
        depth: int = 3
    ) -> Tuple[List[int], float]:
        """
        ניתוח Minimax עם Alpha-Beta Pruning.

        מציאת סדר שאלות שממקסם את התוצאה הגרועה ביותר (worst-case optimization).
        Uses alpha-beta pruning to avoid exploring clearly suboptimal branches.

        מחזיר: (סדר שאלות אופטימלי, ערך מינימקס)
        """
        if not questions:
            return [], 0.0

        n = len(questions)
        actual_depth = min(depth, n)

        best_sequence = []
        best_value = float('-inf')

        def _alphabeta(
            seq: List[int], remaining: Set[int],
            current_depth: int, alpha: float, beta: float,
            is_maximizing: bool,
        ) -> float:
            """Alpha-beta pruning over question sequences."""
            if current_depth == 0 or not remaining:
                return cls._evaluate_sequence_v2(questions, seq)

            if is_maximizing:
                value = float('-inf')
                for idx in sorted(remaining, key=lambda i: questions[i].reward_potential, reverse=True):
                    new_remaining = remaining - {idx}
                    child_value = _alphabeta(
                        seq + [idx], new_remaining,
                        current_depth - 1, alpha, beta, False,
                    )
                    value = max(value, child_value)
                    alpha = max(alpha, value)
                    if alpha >= beta:
                        break  # Beta cutoff
                return value
            else:
                # Minimizing (witness chooses worst response)
                value = float('+inf')
                for idx in sorted(remaining, key=lambda i: questions[i].risk_level, reverse=True):
                    new_remaining = remaining - {idx}
                    child_value = _alphabeta(
                        seq + [idx], new_remaining,
                        current_depth - 1, alpha, beta, True,
                    )
                    value = min(value, child_value)
                    beta = min(beta, value)
                    if alpha >= beta:
                        break  # Alpha cutoff
                return value

        # Start search from each possible first question
        all_indices = set(range(n))
        for start_idx in range(n):
            remaining = all_indices - {start_idx}
            value = _alphabeta(
                [start_idx], remaining,
                actual_depth - 1, float('-inf'), float('+inf'), True,
            )
            if value > best_value:
                best_value = value
                best_sequence = [start_idx]

        # Build full sequence greedily after finding best start
        if best_sequence:
            used = set(best_sequence)
            while len(best_sequence) < n:
                remaining = [i for i in range(n) if i not in used]
                if not remaining:
                    break
                # Pick next question that maximizes worst-case value
                best_next = max(
                    remaining,
                    key=lambda i: cls._evaluate_sequence_v2(questions, best_sequence + [i]),
                )
                best_sequence.append(best_next)
                used.add(best_next)

        return best_sequence, best_value
    
    @classmethod
    def _get_profile_adjustments(cls, profile: WitnessProfile) -> Dict[ResponsePrediction, float]:
        """התאמות לפי פרופיל העד"""
        adjustments = {
            WitnessProfile.COOPERATIVE: {
                ResponsePrediction.ADMIT: 0.3,
                ResponsePrediction.EVADE: -0.2,
            },
            WitnessProfile.DEFENSIVE: {
                ResponsePrediction.DENY: 0.2,
                ResponsePrediction.QUALIFY: 0.2,
                ResponsePrediction.ADMIT: -0.2,
            },
            WitnessProfile.HOSTILE: {
                ResponsePrediction.DENY: 0.3,
                ResponsePrediction.BECOME_HOSTILE: 0.3,
                ResponsePrediction.ADMIT: -0.4,
            },
            WitnessProfile.EVASIVE: {
                ResponsePrediction.EVADE: 0.4,
                ResponsePrediction.QUALIFY: 0.2,
                ResponsePrediction.ADMIT: -0.3,
            },
            WitnessProfile.CONFIDENT: {
                ResponsePrediction.DENY: 0.2,
                ResponsePrediction.ADMIT: -0.1,
                ResponsePrediction.BREAK_DOWN: -0.3,
            },
            WitnessProfile.NERVOUS: {
                ResponsePrediction.CONTRADICT_SELF: 0.3,
                ResponsePrediction.BREAK_DOWN: 0.2,
                ResponsePrediction.EVADE: 0.1,
            },
            WitnessProfile.CALCULATED: {
                ResponsePrediction.QUALIFY: 0.3,
                ResponsePrediction.EVADE: 0.2,
                ResponsePrediction.CONTRADICT_SELF: -0.3,
            },
        }
        return adjustments.get(profile, {})
    
    @classmethod
    def _softmax(cls, utilities: Dict[ResponsePrediction, float]) -> Dict[ResponsePrediction, float]:
        """המרת תועלות להסתברויות"""
        if not utilities:
            return {}
        
        # Temperature parameter - נמוך יותר = יותר דטרמיניסטי
        temperature = 0.5
        
        max_util = max(utilities.values())
        exp_utils = {k: math.exp((v - max_util) / temperature) for k, v in utilities.items()}
        total = sum(exp_utils.values())
        
        return {k: v / total for k, v in exp_utils.items()}
    
    @classmethod
    def _generate_sequences(cls, n: int, depth: int) -> List[List[int]]:
        """יצירת רצפים אפשריים"""
        if depth == 0:
            return [[]]
        if depth == 1:
            return [[i] for i in range(n)]
        
        sequences = []
        for i in range(n):
            for sub_seq in cls._generate_sequences(n, depth - 1):
                if i not in sub_seq:
                    sequences.append([i] + sub_seq)
        return sequences[:100]  # הגבלה למניעת פיצוץ קומבינטורי
    
    @classmethod
    def _evaluate_sequence(cls, questions: List[StrategicQuestion], sequence: List[int]) -> float:
        """הערכת רצף שאלות (legacy)"""
        return cls._evaluate_sequence_v2(questions, sequence)

    @classmethod
    def _evaluate_sequence_v2(cls, questions: List[StrategicQuestion], sequence: List[int]) -> float:
        """
        הערכת רצף שאלות עם מודל משופר.

        מתחשב ב:
        1. התאמת מיקום (position fitness) — שאלה במיקום הנכון
        2. רצף לוגי (logical flow) — בסיס → נעילה → עימות → ניצול
        3. ניהול סיכון (risk management) — לא מרכזים סיכון גבוה ברצף
        4. תלויות (dependencies) — שאלות עם תלויות נשמרות בסדר
        5. Worst-case value — ערך מינימלי בכל שלב
        """
        if not sequence:
            return 0.0

        n = len(sequence)
        total_value = 0.0
        cumulative_risk = 0.0
        prev_intent = None

        # Define logical flow order (preferred sequence of intents)
        INTENT_ORDER = {
            QuestionIntent.ESTABLISH_BASELINE: 0,
            QuestionIntent.BUILD_RAPPORT: 1,
            QuestionIntent.LOCK_TESTIMONY: 2,
            QuestionIntent.PROBE_WEAKNESS: 3,
            QuestionIntent.CREATE_CONTRADICTION: 4,
            QuestionIntent.EXPLOIT_CONTRADICTION: 5,
            QuestionIntent.PSYCHOLOGICAL_PRESSURE: 6,
            QuestionIntent.SURPRISE_ATTACK: 7,
            QuestionIntent.CLOSING_TRAP: 8,
            QuestionIntent.STRATEGIC_RETREAT: 4,  # Can appear anywhere mid
        }

        for i, q_idx in enumerate(sequence):
            if q_idx >= len(questions):
                continue
            q = questions[q_idx]

            # 1. Base value: reward minus risk
            base = q.reward_potential * (1.0 - q.risk_level * 0.4)

            # 2. Position fitness: how close to optimal position
            expected_pct = q.position / 100.0
            actual_pct = i / max(n - 1, 1)
            position_fit = 1.0 - abs(expected_pct - actual_pct)

            # 3. Logical flow bonus: reward correct ordering of intents
            current_order = INTENT_ORDER.get(q.intent, 4)
            flow_bonus = 0.0
            if prev_intent is not None:
                prev_order = INTENT_ORDER.get(prev_intent, 4)
                if current_order >= prev_order:
                    flow_bonus = 0.15  # Correct flow
                else:
                    flow_bonus = -0.10  # Backwards flow penalty

            # 4. Risk management: penalize consecutive high-risk questions
            cumulative_risk += q.risk_level
            risk_penalty = 0.0
            if i > 0 and cumulative_risk / (i + 1) > 0.5:
                risk_penalty = -0.1  # Too much risk concentrated early

            # 5. Dependency check: EXPLOIT must come after CREATE
            dependency_bonus = 0.0
            if q.intent == QuestionIntent.EXPLOIT_CONTRADICTION:
                # Check if CREATE came before
                preceding_intents = [
                    questions[sequence[j]].intent
                    for j in range(i)
                    if j < len(sequence) and sequence[j] < len(questions)
                ]
                if QuestionIntent.CREATE_CONTRADICTION in preceding_intents:
                    dependency_bonus = 0.2
                else:
                    dependency_bonus = -0.15

            step_value = base * position_fit + flow_bonus + risk_penalty + dependency_bonus
            total_value += step_value

            prev_intent = q.intent

        # Normalize and apply conservatism factor
        normalized = total_value / max(n, 1)
        return normalized * 0.85  # Conservative estimate


# =============================================================================
# PREDICTIVE RESPONSE MODEL
# =============================================================================

class PredictiveResponseModel:
    """
    מודל חיזוי תגובות העד
    
    משתמש ב:
    - ניתוח היסטוריית תגובות
    - פרופיל פסיכולוגי
    - הקשר השאלה
    """
    
    # מילון מילות מפתח לזיהוי נקודות תורפה
    WEAKNESS_INDICATORS = {
        'hebrew': {
            'uncertainty': ['אולי', 'יכול להיות', 'לא בטוח', 'כנראה', 'אני חושב'],
            'evasion': ['לא זוכר', 'לא יודע', 'לא שמתי לב', 'לא בדיוק'],
            'contradiction_risk': ['תמיד', 'אף פעם', 'בוודאות', 'מאה אחוז'],
            'emotional': ['כועס', 'עצבני', 'מתוסכל', 'לא הוגן'],
        }
    }
    
    # מודל מעבר מצבים (State Transition Model)
    STATE_TRANSITIONS = {
        WitnessProfile.COOPERATIVE: {
            QuestionIntent.PSYCHOLOGICAL_PRESSURE: (WitnessProfile.NERVOUS, 0.4),
            QuestionIntent.SURPRISE_ATTACK: (WitnessProfile.DEFENSIVE, 0.5),
        },
        WitnessProfile.DEFENSIVE: {
            QuestionIntent.BUILD_RAPPORT: (WitnessProfile.COOPERATIVE, 0.3),
            QuestionIntent.PSYCHOLOGICAL_PRESSURE: (WitnessProfile.HOSTILE, 0.4),
        },
        WitnessProfile.NERVOUS: {
            QuestionIntent.PSYCHOLOGICAL_PRESSURE: (WitnessProfile.EVASIVE, 0.5),
            QuestionIntent.BUILD_RAPPORT: (WitnessProfile.COOPERATIVE, 0.4),
        },
        WitnessProfile.HOSTILE: {
            QuestionIntent.STRATEGIC_RETREAT: (WitnessProfile.DEFENSIVE, 0.3),
            QuestionIntent.PSYCHOLOGICAL_PRESSURE: (WitnessProfile.HOSTILE, 0.8),
        },
    }
    
    @classmethod
    def predict_response(
        cls,
        question: StrategicQuestion,
        witness_profile: WitnessProfile,
        game_state: GameState
    ) -> Dict[ResponsePrediction, float]:
        """
        חיזוי תגובת העד לשאלה
        
        מחזיר התפלגות הסתברויות
        """
        # התחל עם Nash Equilibrium
        base_probs = GameTheoryEngine.calculate_nash_equilibrium(
            question.intent, witness_profile
        )
        
        # התאמה למצב המשחק
        adjusted_probs = cls._adjust_for_game_state(base_probs, game_state)
        
        # התאמה להיסטוריית תגובות
        adjusted_probs = cls._adjust_for_history(adjusted_probs, game_state)
        
        return adjusted_probs
    
    @classmethod
    def predict_witness_state_change(
        cls,
        current_profile: WitnessProfile,
        question_intent: QuestionIntent
    ) -> Tuple[WitnessProfile, float]:
        """
        חיזוי שינוי במצב הפסיכולוגי של העד
        
        מחזיר: (פרופיל חדש, הסתברות לשינוי)
        """
        transitions = cls.STATE_TRANSITIONS.get(current_profile, {})
        if question_intent in transitions:
            return transitions[question_intent]
        return (current_profile, 0.0)
    
    @classmethod
    def identify_breaking_point(
        cls,
        witness_profile: WitnessProfile,
        game_state: GameState
    ) -> float:
        """
        זיהוי קרבה לנקודת שבירה של העד
        
        מחזיר: ציון 0-1 (1 = קרוב לשבירה)
        """
        base_resilience = {
            WitnessProfile.COOPERATIVE: 0.3,
            WitnessProfile.DEFENSIVE: 0.5,
            WitnessProfile.HOSTILE: 0.7,
            WitnessProfile.EVASIVE: 0.4,
            WitnessProfile.CONFIDENT: 0.6,
            WitnessProfile.NERVOUS: 0.2,
            WitnessProfile.CALCULATED: 0.8,
        }
        
        resilience = base_resilience.get(witness_profile, 0.5)
        
        # גורמים שמפחיתים עמידות
        pressure_factor = game_state.credibility_damage * 0.5
        momentum_factor = (1 - game_state.momentum) * 0.3
        
        breaking_point = 1 - resilience + pressure_factor + momentum_factor
        return min(1.0, max(0.0, breaking_point))
    
    @classmethod
    def _adjust_for_game_state(
        cls,
        probs: Dict[ResponsePrediction, float],
        game_state: GameState
    ) -> Dict[ResponsePrediction, float]:
        """התאמה למצב המשחק"""
        adjusted = probs.copy()
        
        # אם העד כבר ניזוק, סיכוי גבוה יותר להודאה
        if game_state.credibility_damage > 0.5:
            adjusted[ResponsePrediction.ADMIT] = adjusted.get(ResponsePrediction.ADMIT, 0) * 1.3
            adjusted[ResponsePrediction.BREAK_DOWN] = adjusted.get(ResponsePrediction.BREAK_DOWN, 0) * 1.5
        
        # נרמול
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: v / total for k, v in adjusted.items()}
        
        return adjusted
    
    @classmethod
    def _adjust_for_history(
        cls,
        probs: Dict[ResponsePrediction, float],
        game_state: GameState
    ) -> Dict[ResponsePrediction, float]:
        """התאמה להיסטוריית תגובות"""
        if not game_state.responses_received:
            return probs
        
        adjusted = probs.copy()
        
        # ספירת תגובות קודמות
        response_counts = defaultdict(int)
        for _, response in game_state.responses_received:
            response_counts[response] += 1
        
        # עד שהתחמק הרבה - ימשיך להתחמק
        if response_counts[ResponsePrediction.EVADE] >= 2:
            adjusted[ResponsePrediction.EVADE] = adjusted.get(ResponsePrediction.EVADE, 0) * 1.4
        
        # עד שסתר את עצמו - עלול לעשות זאת שוב
        if response_counts[ResponsePrediction.CONTRADICT_SELF] >= 1:
            adjusted[ResponsePrediction.CONTRADICT_SELF] = adjusted.get(ResponsePrediction.CONTRADICT_SELF, 0) * 1.3
        
        # נרמול
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: v / total for k, v in adjusted.items()}
        
        return adjusted


# =============================================================================
# UNCERTAINTY MANAGEMENT
# =============================================================================

class UncertaintyManager:
    """
    ניהול אי-ודאות והפתעות
    
    מספק:
    - תוכניות חלופיות
    - נקודות החלטה דינמיות
    - מנגנון התאוששות
    """
    
    @classmethod
    def generate_contingency_plans(
        cls,
        question: StrategicQuestion,
        predicted_responses: Dict[ResponsePrediction, float]
    ) -> Dict[ResponsePrediction, str]:
        """
        יצירת תוכניות חלופיות לכל תגובה אפשרית
        """
        plans = {}
        
        for response, probability in predicted_responses.items():
            if probability < 0.05:  # התעלם מתגובות נדירות מאוד
                continue
            
            plans[response] = cls._generate_plan_for_response(question, response)
        
        return plans
    
    @classmethod
    def create_decision_tree(
        cls,
        questions: List[StrategicQuestion],
        max_depth: int = 4
    ) -> Dict[int, Dict[ResponsePrediction, int]]:
        """
        יצירת עץ החלטות דינמי
        
        מחזיר: מיפוי של (שאלה -> תגובה -> שאלה הבאה)
        """
        decision_tree = {}
        
        for i, question in enumerate(questions):
            decision_tree[i] = {}
            
            # לכל תגובה אפשרית, מה השאלה הבאה האופטימלית?
            for response in ResponsePrediction:
                next_question = cls._find_optimal_next(
                    questions, i, response
                )
                if next_question is not None:
                    decision_tree[i][response] = next_question
        
        return decision_tree
    
    @classmethod
    def calculate_surprise_factor(
        cls,
        expected_response: ResponsePrediction,
        actual_response: ResponsePrediction,
        confidence: float
    ) -> float:
        """
        חישוב פקטור הפתעה
        
        מחזיר: ציון 0-1 (1 = הפתעה גדולה)
        """
        if expected_response == actual_response:
            return 0.0
        
        # הפתעות "טובות" (העד הודה כשציפינו להכחשה)
        good_surprises = {
            (ResponsePrediction.DENY, ResponsePrediction.ADMIT),
            (ResponsePrediction.EVADE, ResponsePrediction.ADMIT),
            (ResponsePrediction.DENY, ResponsePrediction.CONTRADICT_SELF),
        }
        
        # הפתעות "רעות"
        bad_surprises = {
            (ResponsePrediction.ADMIT, ResponsePrediction.DENY),
            (ResponsePrediction.ADMIT, ResponsePrediction.BECOME_HOSTILE),
        }
        
        pair = (expected_response, actual_response)
        
        if pair in good_surprises:
            return confidence * 0.5  # הפתעה חיובית
        elif pair in bad_surprises:
            return confidence * -0.8  # הפתעה שלילית
        else:
            return confidence * 0.3  # הפתעה ניטרלית
    
    @classmethod
    def recovery_strategy(
        cls,
        game_state: GameState,
        last_response: ResponsePrediction
    ) -> QuestionIntent:
        """
        אסטרטגיית התאוששות אחרי תגובה לא צפויה
        """
        # אם העד הפך עוין - נסיגה טקטית
        if last_response == ResponsePrediction.BECOME_HOSTILE:
            return QuestionIntent.STRATEGIC_RETREAT
        
        # אם העד התחמק - ניסיון נוסף מזווית אחרת
        if last_response == ResponsePrediction.EVADE:
            return QuestionIntent.PROBE_WEAKNESS
        
        # אם העד הפתיע בתשובה - נעילה מיידית
        if last_response == ResponsePrediction.SURPRISE:
            return QuestionIntent.LOCK_TESTIMONY
        
        # ברירת מחדל - המשך לפי תוכנית
        return QuestionIntent.ESTABLISH_BASELINE
    
    @classmethod
    def _generate_plan_for_response(
        cls,
        question: StrategicQuestion,
        response: ResponsePrediction
    ) -> str:
        """יצירת תוכנית לתגובה ספציפית"""
        plans = {
            ResponsePrediction.ADMIT: "נעילת ההודאה ומעבר לניצול",
            ResponsePrediction.DENY: "הצגת ראיה סותרת או מעבר לזווית אחרת",
            ResponsePrediction.EVADE: "חזרה על השאלה בניסוח ישיר יותר",
            ResponsePrediction.QUALIFY: "בקשת הבהרה ונעילת הסייג",
            ResponsePrediction.CONTRADICT_SELF: "הדגשת הסתירה והגברת לחץ",
            ResponsePrediction.BECOME_HOSTILE: "נסיגה טקטית ושינוי גישה",
            ResponsePrediction.BREAK_DOWN: "ניצול מקסימלי של הרגע",
            ResponsePrediction.SURPRISE: "הערכה מחדש והתאמת אסטרטגיה",
        }
        return plans.get(response, "המשך לפי תוכנית")
    
    @classmethod
    def _find_optimal_next(
        cls,
        questions: List[StrategicQuestion],
        current_idx: int,
        response: ResponsePrediction
    ) -> Optional[int]:
        """מציאת השאלה הבאה האופטימלית"""
        if current_idx >= len(questions) - 1:
            return None
        
        current = questions[current_idx]
        
        # אם יש followup מוגדר
        if response == ResponsePrediction.ADMIT and current.followup_if_admit:
            # מצא שאלה דומה
            for i, q in enumerate(questions):
                if i > current_idx and current.followup_if_admit in q.question:
                    return i
        
        # ברירת מחדל - השאלה הבאה
        return current_idx + 1


# =============================================================================
# TIME & POSITION OPTIMIZER
# =============================================================================

class TimePositionOptimizer:
    """
    אופטימיזציה של זמן ומיקום שאלות
    
    מיישם:
    - ניהול זמן דינמי
    - מיקום אופטימלי של שאלות
    - מקסום ROI לכל שאלה
    """
    
    # מודל זמן תגובה ממוצע לפי סוג שאלה
    AVERAGE_RESPONSE_TIME = {
        QuestionIntent.ESTABLISH_BASELINE: 1.0,
        QuestionIntent.BUILD_RAPPORT: 1.5,
        QuestionIntent.PROBE_WEAKNESS: 2.0,
        QuestionIntent.LOCK_TESTIMONY: 1.5,
        QuestionIntent.CREATE_CONTRADICTION: 2.5,
        QuestionIntent.EXPLOIT_CONTRADICTION: 2.0,
        QuestionIntent.PSYCHOLOGICAL_PRESSURE: 2.5,
        QuestionIntent.STRATEGIC_RETREAT: 1.0,
        QuestionIntent.SURPRISE_ATTACK: 1.5,
        QuestionIntent.CLOSING_TRAP: 2.0,
    }
    
    # מיקום אופטימלי לפי סוג (אחוז מהחקירה)
    OPTIMAL_POSITION = {
        QuestionIntent.ESTABLISH_BASELINE: (0, 15),
        QuestionIntent.BUILD_RAPPORT: (5, 20),
        QuestionIntent.PROBE_WEAKNESS: (20, 50),
        QuestionIntent.LOCK_TESTIMONY: (30, 60),
        QuestionIntent.CREATE_CONTRADICTION: (40, 70),
        QuestionIntent.EXPLOIT_CONTRADICTION: (50, 80),
        QuestionIntent.PSYCHOLOGICAL_PRESSURE: (60, 85),
        QuestionIntent.STRATEGIC_RETREAT: (30, 70),
        QuestionIntent.SURPRISE_ATTACK: (70, 90),
        QuestionIntent.CLOSING_TRAP: (85, 100),
    }
    
    @classmethod
    def optimize_question_order(
        cls,
        questions: List[StrategicQuestion],
        total_time: float
    ) -> List[StrategicQuestion]:
        """
        אופטימיזציה של סדר השאלות
        
        מחזיר: רשימת שאלות בסדר אופטימלי
        """
        if not questions:
            return []
        
        # חישוב ציון לכל שאלה בכל מיקום
        n = len(questions)
        scores = {}
        
        for i, q in enumerate(questions):
            for position in range(n):
                position_pct = (position / n) * 100
                score = cls._calculate_position_score(q, position_pct)
                scores[(i, position)] = score
        
        # מציאת ההקצאה האופטימלית (greedy)
        assigned = set()
        positions_used = set()
        order = [None] * n
        
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        for (q_idx, pos), score in sorted_scores:
            if q_idx not in assigned and pos not in positions_used:
                order[pos] = questions[q_idx]
                assigned.add(q_idx)
                positions_used.add(pos)
        
        # מילוי חורים
        remaining = [q for i, q in enumerate(questions) if i not in assigned]
        for i, slot in enumerate(order):
            if slot is None and remaining:
                order[i] = remaining.pop(0)
        
        return [q for q in order if q is not None]
    
    @classmethod
    def allocate_time(
        cls,
        questions: List[StrategicQuestion],
        total_time: float
    ) -> List[float]:
        """
        הקצאת זמן לכל שאלה
        
        מחזיר: רשימת זמנים בדקות
        """
        if not questions:
            return []
        
        # חישוב זמן בסיסי לכל שאלה
        base_times = []
        for q in questions:
            base = cls.AVERAGE_RESPONSE_TIME.get(q.intent, 1.5)
            # שאלות עם פוטנציאל גבוה מקבלות יותר זמן
            adjusted = base * (1 + q.reward_potential * 0.5)
            base_times.append(adjusted)
        
        # נרמול לזמן הכולל
        total_base = sum(base_times)
        if total_base > 0:
            factor = total_time / total_base
            return [t * factor for t in base_times]
        
        return [total_time / len(questions)] * len(questions)
    
    @classmethod
    def calculate_roi(
        cls,
        question: StrategicQuestion,
        time_allocated: float
    ) -> float:
        """
        חישוב ROI (Return on Investment) לשאלה
        
        מחזיר: ציון ROI
        """
        if time_allocated <= 0:
            return 0.0
        
        expected_value = question.reward_potential * (1 - question.risk_level)
        roi = expected_value / time_allocated
        
        return roi
    
    @classmethod
    def suggest_time_adjustment(
        cls,
        game_state: GameState,
        remaining_questions: int
    ) -> str:
        """
        המלצה להתאמת זמן
        """
        time_per_question = game_state.time_remaining / max(1, remaining_questions)
        
        if time_per_question < 1.0:
            return "זמן קצר - התמקד בשאלות קריטיות בלבד"
        elif time_per_question < 2.0:
            return "זמן מוגבל - דלג על שאלות בניית אמון"
        elif time_per_question > 4.0:
            return "יש זמן - אפשר להעמיק בנקודות חשובות"
        else:
            return "זמן סביר - המשך לפי תוכנית"
    
    @classmethod
    def _calculate_position_score(
        cls,
        question: StrategicQuestion,
        position_pct: float
    ) -> float:
        """חישוב ציון מיקום לשאלה"""
        optimal_range = cls.OPTIMAL_POSITION.get(question.intent, (0, 100))
        min_pos, max_pos = optimal_range
        
        if min_pos <= position_pct <= max_pos:
            # בתוך הטווח האופטימלי
            center = (min_pos + max_pos) / 2
            distance = abs(position_pct - center) / ((max_pos - min_pos) / 2)
            return 1.0 - distance * 0.3
        else:
            # מחוץ לטווח
            if position_pct < min_pos:
                distance = min_pos - position_pct
            else:
                distance = position_pct - max_pos
            return max(0, 0.5 - distance / 100)


# =============================================================================
# STRATEGIC EXAMINATION PLANNER
# =============================================================================

class StrategicExaminationPlanner:
    """
    מתכנן חקירה אסטרטגי ראשי
    
    משלב את כל המודולים ליצירת תוכנית חקירה מושלמת
    """
    
    def __init__(self):
        self.game_theory = GameTheoryEngine()
        self.predictor = PredictiveResponseModel()
        self.uncertainty = UncertaintyManager()
        self.optimizer = TimePositionOptimizer()
    
    def create_examination_plan(
        self,
        contradiction_type: str,
        contradiction_confidence: float,
        claim_a: str,
        claim_b: str,
        witness_profile: WitnessProfile = WitnessProfile.COOPERATIVE,
        total_time_minutes: float = 30.0
    ) -> ExaminationPlan:
        """
        יצירת תוכנית חקירה מלאה
        """
        # שלב 1: יצירת שאלות אסטרטגיות
        questions = self._generate_strategic_questions(
            contradiction_type, contradiction_confidence, claim_a, claim_b
        )
        
        # שלב 2: חיזוי תגובות לכל שאלה
        for q in questions:
            q.predicted_responses = self.predictor.predict_response(
                q, witness_profile, GameState()
            )
        
        # שלב 3: אופטימיזציה של סדר ומיקום
        questions = self.optimizer.optimize_question_order(questions, total_time_minutes)
        
        # שלב 4: הקצאת זמן
        times = self.optimizer.allocate_time(questions, total_time_minutes)
        for q, t in zip(questions, times):
            q.time_allocation = t
        
        # שלב 5: יצירת עץ החלטות
        decision_tree = self.uncertainty.create_decision_tree(questions)
        
        # שלב 6: ניתוח מינימקס
        critical_path, minimax_value = self.game_theory.minimax_analysis(questions)
        
        # שלב 7: חישוב מדדים
        expected_value = self._calculate_expected_value(questions, witness_profile)
        risk_score = self._calculate_risk_score(questions)
        confidence_score = self._calculate_confidence_score(questions)
        
        # שלב 8: יצירת סיכום אסטרטגי
        strategy_summary = self._generate_strategy_summary(
            questions, witness_profile, contradiction_type
        )
        
        return ExaminationPlan(
            questions=questions,
            witness_profile=witness_profile,
            total_time_minutes=total_time_minutes,
            critical_path=critical_path,
            alternative_paths=self._generate_alternative_paths(questions, decision_tree),
            decision_points=decision_tree,
            expected_value=expected_value,
            risk_score=risk_score,
            confidence_score=confidence_score,
            strategy_summary=strategy_summary,
            key_objectives=self._identify_key_objectives(contradiction_type),
            potential_pitfalls=self._identify_pitfalls(witness_profile),
        )
    
    def _generate_strategic_questions(
        self,
        contradiction_type: str,
        confidence: float,
        claim_a: str,
        claim_b: str
    ) -> List[StrategicQuestion]:
        """יצירת שאלות אסטרטגיות"""
        questions = []
        
        # שאלה 1: קביעת קו בסיס (פתוחה)
        questions.append(StrategicQuestion(
            question=f"ספר לי במילים שלך מה קרה באותו יום",
            intent=QuestionIntent.ESTABLISH_BASELINE,
            position=5,
            time_allocation=2.0,
            risk_level=0.1,
            reward_potential=0.4,
            strategic_notes="שאלה פתוחה לקיבוע גרסה ראשונית",
            psychological_notes="מאפשרת לעד להרגיש בשליטה",
        ))
        
        # שאלה 2: נעילת טענה ראשונה
        questions.append(StrategicQuestion(
            question=f"אתה מאשר שאמרת: '{claim_a[:50]}...'?",
            intent=QuestionIntent.LOCK_TESTIMONY,
            position=20,
            time_allocation=1.5,
            risk_level=0.2,
            reward_potential=0.5,
            followup_if_deny="מתי בדיוק אמרת את זה?",
            strategic_notes="נעילת הטענה הראשונה לפני עימות",
        ))
        
        # שאלה 3: בדיקת נקודת תורפה
        questions.append(StrategicQuestion(
            question=self._generate_probe_question(contradiction_type, claim_a, claim_b),
            intent=QuestionIntent.PROBE_WEAKNESS,
            position=35,
            time_allocation=2.0,
            risk_level=0.3,
            reward_potential=0.6,
            strategic_notes="בדיקה עדינה של הסתירה",
        ))
        
        # שאלה 4: יצירת סתירה
        questions.append(StrategicQuestion(
            question=f"אבל קודם אמרת '{claim_a[:40]}...'. איך זה מסתדר עם '{claim_b[:40]}...'?",
            intent=QuestionIntent.CREATE_CONTRADICTION,
            position=50,
            time_allocation=2.5,
            risk_level=0.4,
            reward_potential=0.8,
            followup_if_evade="אני שואל שאלה פשוטה - מה נכון?",
            strategic_notes="עימות ישיר עם הסתירה",
            psychological_notes="נקודת לחץ מרכזית",
        ))
        
        # שאלה 5: ניצול סתירה
        questions.append(StrategicQuestion(
            question="אז מה נכון - הגרסה הראשונה או השנייה?",
            intent=QuestionIntent.EXPLOIT_CONTRADICTION,
            position=65,
            time_allocation=2.0,
            risk_level=0.3,
            reward_potential=0.9,
            strategic_notes="ניצול הסתירה שנחשפה",
        ))
        
        # שאלה 6: לחץ פסיכולוגי (אם ביטחון גבוה)
        if confidence > 0.7:
            questions.append(StrategicQuestion(
                question="אתה מבין שהעדות שלך סותרת את עצמה?",
                intent=QuestionIntent.PSYCHOLOGICAL_PRESSURE,
                position=75,
                time_allocation=2.0,
                risk_level=0.5,
                reward_potential=0.7,
                strategic_notes="הגברת לחץ לקראת סיום",
                psychological_notes="עלול לגרום לעד להיסגר או להישבר",
            ))
        
        # שאלה 7: תקיפת הפתעה
        questions.append(StrategicQuestion(
            question=self._generate_surprise_question(contradiction_type, claim_a, claim_b),
            intent=QuestionIntent.SURPRISE_ATTACK,
            position=85,
            time_allocation=1.5,
            risk_level=0.4,
            reward_potential=0.8,
            strategic_notes="שאלה מפתיעה מזווית לא צפויה",
        ))
        
        # שאלה 8: מלכודת סגירה
        questions.append(StrategicQuestion(
            question="אז לסיכום, אתה עומד מאחורי כל מה שאמרת היום?",
            intent=QuestionIntent.CLOSING_TRAP,
            position=95,
            time_allocation=1.5,
            risk_level=0.2,
            reward_potential=0.6,
            strategic_notes="מלכודת סגירה - נועלת את כל הסתירות",
        ))
        
        return questions
    
    def _generate_probe_question(
        self,
        contradiction_type: str,
        claim_a: str,
        claim_b: str
    ) -> str:
        """יצירת שאלת בדיקה לפי סוג הסתירה"""
        probes = {
            'TEMPORAL': "בוא נדבר על התאריכים - אתה בטוח בזמנים שציינת?",
            'QUANTITATIVE': "לגבי הסכומים שהזכרת - איך אתה זוכר את המספרים האלה?",
            'PRESENCE': "אתה זוכר בדיוק מי היה שם?",
            'IDENTITY': "ספר לי שוב מי בדיוק היה מעורב",
            'NEGATION': "אתה בטוח במה שקרה או לא קרה?",
        }
        
        for key, question in probes.items():
            if key in contradiction_type.upper():
                return question
        
        return "ספר לי עוד על הנסיבות"
    
    def _generate_surprise_question(
        self,
        contradiction_type: str,
        claim_a: str,
        claim_b: str
    ) -> str:
        """יצירת שאלת הפתעה"""
        surprises = {
            'TEMPORAL': "אם אראה לך יומן מאותו יום, מה נראה שם?",
            'QUANTITATIVE': "יש לי כאן מסמך עם מספרים אחרים - איך תסביר את זה?",
            'PRESENCE': "מישהו אחר טוען שלא היית שם בכלל",
            'IDENTITY': "יש עד נוסף שמזהה מישהו אחר לגמרי",
        }
        
        for key, question in surprises.items():
            if key in contradiction_type.upper():
                return question
        
        return "יש לי מידע שסותר את מה שאמרת - מה תגיד על זה?"
    
    def _calculate_expected_value(
        self,
        questions: List[StrategicQuestion],
        witness_profile: WitnessProfile
    ) -> float:
        """חישוב תוחלת ערך"""
        total = 0.0
        for q in questions:
            # ערך = פוטנציאל * (1 - סיכון) * הסתברות להצלחה
            success_prob = 0.6  # בסיס
            if witness_profile == WitnessProfile.NERVOUS:
                success_prob = 0.7
            elif witness_profile == WitnessProfile.HOSTILE:
                success_prob = 0.4
            
            value = q.reward_potential * (1 - q.risk_level) * success_prob
            total += value
        
        return total / len(questions) if questions else 0.0
    
    def _calculate_risk_score(self, questions: List[StrategicQuestion]) -> float:
        """חישוב ציון סיכון"""
        if not questions:
            return 0.0
        return sum(q.risk_level for q in questions) / len(questions)
    
    def _calculate_confidence_score(self, questions: List[StrategicQuestion]) -> float:
        """חישוב ציון ביטחון"""
        if not questions:
            return 0.0
        return sum(q.reward_potential for q in questions) / len(questions)
    
    def _generate_strategy_summary(
        self,
        questions: List[StrategicQuestion],
        witness_profile: WitnessProfile,
        contradiction_type: str
    ) -> str:
        """יצירת סיכום אסטרטגי"""
        profile_strategies = {
            WitnessProfile.COOPERATIVE: "גישה רכה בהתחלה, הגברת לחץ הדרגתית",
            WitnessProfile.DEFENSIVE: "בניית אמון לפני עימות, שאלות עקיפות",
            WitnessProfile.HOSTILE: "שאלות ישירות וקצרות, הימנעות מעימות מיותר",
            WitnessProfile.EVASIVE: "שאלות סגורות, דרישה לתשובות ישירות",
            WitnessProfile.CONFIDENT: "ערעור הביטחון בהדרגה, הפתעות",
            WitnessProfile.NERVOUS: "הגברת לחץ מהירה, ניצול חרדה",
            WitnessProfile.CALCULATED: "שאלות מפתיעות, שבירת דפוס",
        }
        
        strategy = profile_strategies.get(witness_profile, "גישה מאוזנת")
        
        return f"""
אסטרטגיה מומלצת: {strategy}

סוג סתירה: {contradiction_type}
מספר שאלות: {len(questions)}
זמן משוער: {sum(q.time_allocation for q in questions):.1f} דקות

מבנה החקירה:
1. פתיחה (0-20%): קביעת קו בסיס ונעילת גרסה
2. בנייה (20-50%): בדיקת נקודות תורפה
3. עימות (50-80%): חשיפת וניצול סתירות
4. סגירה (80-100%): מלכודות ונעילה סופית
"""
    
    def _generate_alternative_paths(
        self,
        questions: List[StrategicQuestion],
        decision_tree: Dict
    ) -> List[List[int]]:
        """יצירת מסלולים חלופיים"""
        paths = []
        
        # מסלול אגרסיבי
        aggressive = [i for i, q in enumerate(questions) 
                     if q.intent in [QuestionIntent.PSYCHOLOGICAL_PRESSURE, 
                                    QuestionIntent.SURPRISE_ATTACK,
                                    QuestionIntent.EXPLOIT_CONTRADICTION]]
        if aggressive:
            paths.append(aggressive)
        
        # מסלול זהיר
        cautious = [i for i, q in enumerate(questions)
                   if q.intent in [QuestionIntent.ESTABLISH_BASELINE,
                                  QuestionIntent.BUILD_RAPPORT,
                                  QuestionIntent.LOCK_TESTIMONY]]
        if cautious:
            paths.append(cautious)
        
        return paths
    
    def _identify_key_objectives(self, contradiction_type: str) -> List[str]:
        """זיהוי מטרות מפתח"""
        objectives = [
            "נעילת גרסה ראשונית",
            "חשיפת הסתירה",
            "ניצול הסתירה לפגיעה במהימנות",
        ]
        
        if 'TEMPORAL' in contradiction_type.upper():
            objectives.append("קיבוע תאריכים וזמנים מדויקים")
        elif 'QUANTITATIVE' in contradiction_type.upper():
            objectives.append("קיבוע מספרים וסכומים")
        
        return objectives
    
    def _identify_pitfalls(self, witness_profile: WitnessProfile) -> List[str]:
        """זיהוי מלכודות פוטנציאליות"""
        pitfalls = {
            WitnessProfile.HOSTILE: [
                "העד עלול להפוך אגרסיבי",
                "סיכון להתנגדות מצד השופט",
            ],
            WitnessProfile.EVASIVE: [
                "העד עלול להתחמק מכל שאלה",
                "צורך בשאלות סגורות מאוד",
            ],
            WitnessProfile.CALCULATED: [
                "העד עלול לצפות את המלכודות",
                "צורך בהפתעות יצירתיות",
            ],
            WitnessProfile.NERVOUS: [
                "סיכון שהשופט יראה את הלחץ כהתעמרות",
                "העד עלול להתמוטט מוקדם מדי",
            ],
        }
        
        return pitfalls.get(witness_profile, ["אין מלכודות מיוחדות זוהו"])


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    'WitnessProfile',
    'QuestionIntent',
    'ResponsePrediction',
    'StrategicQuestion',
    'ExaminationPlan',
    'GameState',
    'GameTheoryEngine',
    'PredictiveResponseModel',
    'UncertaintyManager',
    'TimePositionOptimizer',
    'StrategicExaminationPlanner',
]
