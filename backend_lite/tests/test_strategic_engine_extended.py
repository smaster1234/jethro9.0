"""
Extended Logical Tests — Strategic Cross-Examination Engine
============================================================

~90 tests covering:
- Enum value correctness (WitnessProfile, QuestionIntent, ResponsePrediction)
- Dataclass defaults and construction (StrategicQuestion, ExaminationPlan, GameState)
- GameTheoryEngine (payoff matrix, Nash equilibrium, minimax, profile adjustments, softmax)
- PredictiveResponseModel (predict_response, state transitions, breaking point)
- UncertaintyManager (contingency plans, decision tree, surprise factor, recovery)
- TimePositionOptimizer (response times, optimal positions, ordering, allocation, ROI, adjustment)
- StrategicExaminationPlanner (full plan creation, metrics, objectives, pitfalls)
"""

import math
import pytest

from backend_lite.strategic_engine import (
    WitnessProfile,
    QuestionIntent,
    ResponsePrediction,
    StrategicQuestion,
    ExaminationPlan,
    GameState,
    GameTheoryEngine,
    PredictiveResponseModel,
    UncertaintyManager,
    TimePositionOptimizer,
    StrategicExaminationPlanner,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _question(
    intent: QuestionIntent = QuestionIntent.ESTABLISH_BASELINE,
    position: int = 10,
    time_allocation: float = 1.5,
    risk_level: float = 0.2,
    reward_potential: float = 0.5,
    question_text: str = "שאלה לדוגמה?",
    **kwargs,
) -> StrategicQuestion:
    """Quick StrategicQuestion factory."""
    return StrategicQuestion(
        question=question_text,
        intent=intent,
        position=position,
        time_allocation=time_allocation,
        risk_level=risk_level,
        reward_potential=reward_potential,
        **kwargs,
    )


def _make_question_sequence() -> list:
    """Build a logical BASELINE -> LOCK -> CREATE -> EXPLOIT sequence."""
    return [
        _question(QuestionIntent.ESTABLISH_BASELINE, position=5, risk_level=0.1, reward_potential=0.4),
        _question(QuestionIntent.LOCK_TESTIMONY, position=25, risk_level=0.2, reward_potential=0.5),
        _question(QuestionIntent.CREATE_CONTRADICTION, position=50, risk_level=0.4, reward_potential=0.8),
        _question(QuestionIntent.EXPLOIT_CONTRADICTION, position=65, risk_level=0.3, reward_potential=0.9),
    ]


# ===================================================================
# 1. Enum Values
# ===================================================================

class TestWitnessProfileEnum:
    """Verify all WitnessProfile members and string values."""

    def test_cooperative_value(self):
        assert WitnessProfile.COOPERATIVE.value == "cooperative"

    def test_defensive_value(self):
        assert WitnessProfile.DEFENSIVE.value == "defensive"

    def test_hostile_value(self):
        assert WitnessProfile.HOSTILE.value == "hostile"

    def test_evasive_value(self):
        assert WitnessProfile.EVASIVE.value == "evasive"

    def test_confident_value(self):
        assert WitnessProfile.CONFIDENT.value == "confident"

    def test_nervous_value(self):
        assert WitnessProfile.NERVOUS.value == "nervous"

    def test_calculated_value(self):
        assert WitnessProfile.CALCULATED.value == "calculated"

    def test_member_count(self):
        assert len(WitnessProfile) == 7


class TestQuestionIntentEnum:
    """Verify QuestionIntent members."""

    def test_has_all_ten_intents(self):
        expected = {
            "ESTABLISH_BASELINE", "BUILD_RAPPORT", "PROBE_WEAKNESS",
            "LOCK_TESTIMONY", "CREATE_CONTRADICTION", "EXPLOIT_CONTRADICTION",
            "PSYCHOLOGICAL_PRESSURE", "STRATEGIC_RETREAT", "SURPRISE_ATTACK",
            "CLOSING_TRAP",
        }
        assert {m.name for m in QuestionIntent} == expected

    def test_closing_trap_value(self):
        assert QuestionIntent.CLOSING_TRAP.value == "closing_trap"


class TestResponsePredictionEnum:
    """Verify ResponsePrediction members."""

    def test_has_all_eight_predictions(self):
        expected = {
            "ADMIT", "DENY", "EVADE", "QUALIFY",
            "CONTRADICT_SELF", "BECOME_HOSTILE", "BREAK_DOWN", "SURPRISE",
        }
        assert {m.name for m in ResponsePrediction} == expected

    def test_break_down_value(self):
        assert ResponsePrediction.BREAK_DOWN.value == "break_down"


# ===================================================================
# 2. Dataclass Tests
# ===================================================================

class TestStrategicQuestionDataclass:
    """Verify StrategicQuestion construction and defaults."""

    def test_create_with_required_fields(self):
        q = _question()
        assert q.question == "שאלה לדוגמה?"
        assert q.intent == QuestionIntent.ESTABLISH_BASELINE
        assert q.position == 10
        assert isinstance(q.time_allocation, float)

    def test_predicted_responses_default_empty_dict(self):
        q = _question()
        assert q.predicted_responses == {}

    def test_dependencies_default_empty_list(self):
        q = _question()
        assert q.dependencies == []

    def test_blocks_default_empty_list(self):
        q = _question()
        assert q.blocks == []

    def test_followup_fields_default_none(self):
        q = _question()
        assert q.followup_if_admit is None
        assert q.followup_if_deny is None
        assert q.followup_if_evade is None

    def test_strategic_notes_default_empty(self):
        q = _question()
        assert q.strategic_notes == ""


class TestExaminationPlanDataclass:
    """Verify ExaminationPlan construction."""

    def test_create_minimal_plan(self):
        plan = ExaminationPlan(
            questions=[_question()],
            witness_profile=WitnessProfile.COOPERATIVE,
            total_time_minutes=20.0,
            critical_path=[0],
            alternative_paths=[],
            decision_points={},
            expected_value=0.5,
            risk_score=0.2,
            confidence_score=0.6,
        )
        assert len(plan.questions) == 1
        assert plan.total_time_minutes == 20.0

    def test_alternative_paths_default(self):
        plan = ExaminationPlan(
            questions=[], witness_profile=WitnessProfile.DEFENSIVE,
            total_time_minutes=10.0, critical_path=[], alternative_paths=[],
            decision_points={}, expected_value=0.0, risk_score=0.0,
            confidence_score=0.0,
        )
        assert plan.alternative_paths == []

    def test_key_objectives_default(self):
        plan = ExaminationPlan(
            questions=[], witness_profile=WitnessProfile.HOSTILE,
            total_time_minutes=5.0, critical_path=[], alternative_paths=[],
            decision_points={}, expected_value=0.0, risk_score=0.0,
            confidence_score=0.0,
        )
        assert plan.key_objectives == []


class TestGameStateDataclass:
    """Verify GameState defaults."""

    def test_default_time_remaining(self):
        gs = GameState()
        assert gs.time_remaining == 30.0

    def test_default_momentum(self):
        gs = GameState()
        assert gs.momentum == 0.5

    def test_default_credibility_damage(self):
        gs = GameState()
        assert gs.credibility_damage == 0.0

    def test_questions_asked_default_empty(self):
        gs = GameState()
        assert gs.questions_asked == []

    def test_responses_received_default_empty(self):
        gs = GameState()
        assert gs.responses_received == []


# ===================================================================
# 3. GameTheoryEngine Tests
# ===================================================================

class TestPayoffMatrix:
    """Verify structure and specific values in the payoff matrix."""

    def test_matrix_has_eight_intents(self):
        expected_intents = {
            QuestionIntent.ESTABLISH_BASELINE,
            QuestionIntent.PROBE_WEAKNESS,
            QuestionIntent.LOCK_TESTIMONY,
            QuestionIntent.CREATE_CONTRADICTION,
            QuestionIntent.EXPLOIT_CONTRADICTION,
            QuestionIntent.PSYCHOLOGICAL_PRESSURE,
            QuestionIntent.SURPRISE_ATTACK,
            QuestionIntent.CLOSING_TRAP,
        }
        assert set(GameTheoryEngine.PAYOFF_MATRIX.keys()) == expected_intents

    def test_each_entry_maps_response_to_tuple(self):
        for intent, payoffs in GameTheoryEngine.PAYOFF_MATRIX.items():
            for resp, (att, defn) in payoffs.items():
                assert isinstance(resp, ResponsePrediction), f"Bad key in {intent}"
                assert isinstance(att, float), f"Attacker payoff not float in {intent}"
                assert isinstance(defn, float), f"Defender payoff not float in {intent}"

    def test_exploit_contradiction_break_down_highest_attacker(self):
        att, defn = GameTheoryEngine.PAYOFF_MATRIX[QuestionIntent.EXPLOIT_CONTRADICTION][ResponsePrediction.BREAK_DOWN]
        assert att == 1.0
        assert defn == -0.8

    def test_establish_baseline_admit_payoff(self):
        att, defn = GameTheoryEngine.PAYOFF_MATRIX[QuestionIntent.ESTABLISH_BASELINE][ResponsePrediction.ADMIT]
        assert att == 0.3
        assert defn == 0.1


class TestNashEquilibrium:
    """Verify calculate_nash_equilibrium behavior."""

    def test_returns_dict_of_response_to_float(self):
        result = GameTheoryEngine.calculate_nash_equilibrium(
            QuestionIntent.PROBE_WEAKNESS, WitnessProfile.COOPERATIVE
        )
        for k, v in result.items():
            assert isinstance(k, ResponsePrediction)
            assert isinstance(v, float)

    def test_probabilities_sum_to_one(self):
        result = GameTheoryEngine.calculate_nash_equilibrium(
            QuestionIntent.PROBE_WEAKNESS, WitnessProfile.COOPERATIVE
        )
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_cooperative_probe_admit_relatively_high(self):
        result = GameTheoryEngine.calculate_nash_equilibrium(
            QuestionIntent.PROBE_WEAKNESS, WitnessProfile.COOPERATIVE
        )
        # COOPERATIVE gets +0.3 on ADMIT; it should be a significant portion
        assert ResponsePrediction.ADMIT in result
        assert result[ResponsePrediction.ADMIT] > 0.1

    def test_hostile_probe_deny_higher_than_cooperative(self):
        coop = GameTheoryEngine.calculate_nash_equilibrium(
            QuestionIntent.PROBE_WEAKNESS, WitnessProfile.COOPERATIVE
        )
        hostile = GameTheoryEngine.calculate_nash_equilibrium(
            QuestionIntent.PROBE_WEAKNESS, WitnessProfile.HOSTILE
        )
        # HOSTILE gets DENY +0.3, so DENY should be higher for hostile
        assert hostile.get(ResponsePrediction.DENY, 0) > coop.get(ResponsePrediction.DENY, 0)

    def test_unknown_intent_returns_evade_1(self):
        # BUILD_RAPPORT is not in the payoff matrix
        result = GameTheoryEngine.calculate_nash_equilibrium(
            QuestionIntent.BUILD_RAPPORT, WitnessProfile.COOPERATIVE
        )
        assert result == {ResponsePrediction.EVADE: 1.0}


class TestMinimaxAnalysis:
    """Verify minimax_analysis returns valid sequences and values."""

    def test_empty_questions_returns_empty(self):
        seq, val = GameTheoryEngine.minimax_analysis([])
        assert seq == []
        assert val == 0.0

    def test_single_question_returns_index_zero(self):
        seq, val = GameTheoryEngine.minimax_analysis([_question()])
        assert seq == [0]
        assert isinstance(val, float)

    def test_multiple_questions_all_indices_present(self):
        qs = _make_question_sequence()
        seq, val = GameTheoryEngine.minimax_analysis(qs)
        assert sorted(seq) == list(range(len(qs)))

    def test_result_indices_within_range(self):
        qs = _make_question_sequence()
        seq, _ = GameTheoryEngine.minimax_analysis(qs)
        for idx in seq:
            assert 0 <= idx < len(qs)

    def test_value_is_float(self):
        _, val = GameTheoryEngine.minimax_analysis([_question(), _question()])
        assert isinstance(val, float)


class TestProfileAdjustments:
    """Verify _get_profile_adjustments returns correct dicts."""

    def test_cooperative_adjustments(self):
        adj = GameTheoryEngine._get_profile_adjustments(WitnessProfile.COOPERATIVE)
        assert adj[ResponsePrediction.ADMIT] == 0.3
        assert adj[ResponsePrediction.EVADE] == -0.2

    def test_hostile_adjustments(self):
        adj = GameTheoryEngine._get_profile_adjustments(WitnessProfile.HOSTILE)
        assert adj[ResponsePrediction.DENY] == 0.3
        assert adj[ResponsePrediction.BECOME_HOSTILE] == 0.3
        assert adj[ResponsePrediction.ADMIT] == -0.4

    def test_nervous_adjustments(self):
        adj = GameTheoryEngine._get_profile_adjustments(WitnessProfile.NERVOUS)
        assert adj[ResponsePrediction.CONTRADICT_SELF] == 0.3
        assert adj[ResponsePrediction.BREAK_DOWN] == 0.2

    def test_unknown_profile_returns_empty(self):
        # Passing a non-existent profile would need a hack;
        # instead verify that all 7 known profiles return something
        for profile in WitnessProfile:
            adj = GameTheoryEngine._get_profile_adjustments(profile)
            assert isinstance(adj, dict)


class TestSoftmax:
    """Verify _softmax probability conversion."""

    def test_empty_dict_returns_empty(self):
        result = GameTheoryEngine._softmax({})
        assert result == {}

    def test_single_entry_returns_one(self):
        result = GameTheoryEngine._softmax({ResponsePrediction.ADMIT: 0.5})
        assert abs(result[ResponsePrediction.ADMIT] - 1.0) < 1e-6

    def test_multiple_entries_sum_to_one(self):
        utils = {
            ResponsePrediction.ADMIT: 0.5,
            ResponsePrediction.DENY: 0.3,
            ResponsePrediction.EVADE: 0.1,
        }
        result = GameTheoryEngine._softmax(utils)
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_higher_utility_gets_higher_probability(self):
        utils = {
            ResponsePrediction.ADMIT: 1.0,
            ResponsePrediction.DENY: -1.0,
        }
        result = GameTheoryEngine._softmax(utils)
        assert result[ResponsePrediction.ADMIT] > result[ResponsePrediction.DENY]


class TestEvaluateSequence:
    """Verify _evaluate_sequence_v2 scoring logic."""

    def test_empty_sequence_returns_zero(self):
        assert GameTheoryEngine._evaluate_sequence_v2([], []) == 0.0

    def test_correct_flow_order_scores_positive(self):
        qs = _make_question_sequence()
        score = GameTheoryEngine._evaluate_sequence_v2(qs, [0, 1, 2, 3])
        assert score > 0.0

    def test_backwards_flow_lower_score(self):
        qs = _make_question_sequence()
        forward = GameTheoryEngine._evaluate_sequence_v2(qs, [0, 1, 2, 3])
        backward = GameTheoryEngine._evaluate_sequence_v2(qs, [3, 2, 1, 0])
        assert forward > backward

    def test_exploit_after_create_gets_dependency_bonus(self):
        qs = [
            _question(QuestionIntent.CREATE_CONTRADICTION, position=50, risk_level=0.4, reward_potential=0.8),
            _question(QuestionIntent.EXPLOIT_CONTRADICTION, position=65, risk_level=0.3, reward_potential=0.9),
        ]
        with_dep = GameTheoryEngine._evaluate_sequence_v2(qs, [0, 1])
        without_dep = GameTheoryEngine._evaluate_sequence_v2(qs, [1, 0])
        # [CREATE, EXPLOIT] should score higher than [EXPLOIT, CREATE]
        assert with_dep > without_dep


# ===================================================================
# 4. PredictiveResponseModel Tests
# ===================================================================

class TestPredictResponse:
    """Verify predict_response returns valid distributions."""

    def test_returns_dict_of_response_to_float(self):
        result = PredictiveResponseModel.predict_response(
            _question(QuestionIntent.PROBE_WEAKNESS),
            WitnessProfile.COOPERATIVE,
            GameState(),
        )
        for k, v in result.items():
            assert isinstance(k, ResponsePrediction)
            assert isinstance(v, float)

    def test_probabilities_non_negative(self):
        result = PredictiveResponseModel.predict_response(
            _question(QuestionIntent.CREATE_CONTRADICTION),
            WitnessProfile.NERVOUS,
            GameState(),
        )
        for v in result.values():
            assert v >= 0.0

    def test_different_profiles_produce_different_distributions(self):
        q = _question(QuestionIntent.PROBE_WEAKNESS)
        gs = GameState()
        coop = PredictiveResponseModel.predict_response(q, WitnessProfile.COOPERATIVE, gs)
        hostile = PredictiveResponseModel.predict_response(q, WitnessProfile.HOSTILE, gs)
        # At least one probability should differ
        assert coop != hostile


class TestWitnessStateChange:
    """Verify predict_witness_state_change transitions."""

    def test_cooperative_pressure_becomes_nervous(self):
        new_profile, prob = PredictiveResponseModel.predict_witness_state_change(
            WitnessProfile.COOPERATIVE, QuestionIntent.PSYCHOLOGICAL_PRESSURE
        )
        assert new_profile == WitnessProfile.NERVOUS
        assert prob == 0.4

    def test_cooperative_surprise_becomes_defensive(self):
        new_profile, prob = PredictiveResponseModel.predict_witness_state_change(
            WitnessProfile.COOPERATIVE, QuestionIntent.SURPRISE_ATTACK
        )
        assert new_profile == WitnessProfile.DEFENSIVE
        assert prob == 0.5

    def test_defensive_rapport_becomes_cooperative(self):
        new_profile, prob = PredictiveResponseModel.predict_witness_state_change(
            WitnessProfile.DEFENSIVE, QuestionIntent.BUILD_RAPPORT
        )
        assert new_profile == WitnessProfile.COOPERATIVE
        assert prob == 0.3

    def test_nervous_rapport_becomes_cooperative(self):
        new_profile, prob = PredictiveResponseModel.predict_witness_state_change(
            WitnessProfile.NERVOUS, QuestionIntent.BUILD_RAPPORT
        )
        assert new_profile == WitnessProfile.COOPERATIVE
        assert prob == 0.4

    def test_hostile_pressure_stays_hostile(self):
        new_profile, prob = PredictiveResponseModel.predict_witness_state_change(
            WitnessProfile.HOSTILE, QuestionIntent.PSYCHOLOGICAL_PRESSURE
        )
        assert new_profile == WitnessProfile.HOSTILE
        assert prob == 0.8

    def test_unknown_transition_returns_same_profile(self):
        new_profile, prob = PredictiveResponseModel.predict_witness_state_change(
            WitnessProfile.CONFIDENT, QuestionIntent.ESTABLISH_BASELINE
        )
        assert new_profile == WitnessProfile.CONFIDENT
        assert prob == 0.0


class TestBreakingPoint:
    """Verify identify_breaking_point calculations."""

    def test_nervous_witness_high_breaking_point(self):
        bp = PredictiveResponseModel.identify_breaking_point(
            WitnessProfile.NERVOUS, GameState()
        )
        # NERVOUS resilience=0.2, so base = 1 - 0.2 = 0.8, plus momentum_factor
        assert bp > 0.7

    def test_calculated_witness_low_breaking_point(self):
        bp = PredictiveResponseModel.identify_breaking_point(
            WitnessProfile.CALCULATED, GameState()
        )
        # CALCULATED resilience=0.8, so base = 1 - 0.8 = 0.2
        assert bp < 0.5

    def test_credibility_damage_increases_breaking_point(self):
        gs_low = GameState(credibility_damage=0.0)
        gs_high = GameState(credibility_damage=0.8)
        bp_low = PredictiveResponseModel.identify_breaking_point(WitnessProfile.DEFENSIVE, gs_low)
        bp_high = PredictiveResponseModel.identify_breaking_point(WitnessProfile.DEFENSIVE, gs_high)
        assert bp_high > bp_low

    def test_low_momentum_increases_breaking_point(self):
        gs_high_m = GameState(momentum=0.9)
        gs_low_m = GameState(momentum=0.1)
        bp_high = PredictiveResponseModel.identify_breaking_point(WitnessProfile.COOPERATIVE, gs_high_m)
        bp_low = PredictiveResponseModel.identify_breaking_point(WitnessProfile.COOPERATIVE, gs_low_m)
        # Low momentum means (1 - momentum) is higher, adding more pressure
        assert bp_low > bp_high

    def test_result_always_in_zero_one(self):
        extreme = GameState(credibility_damage=1.0, momentum=0.0)
        bp = PredictiveResponseModel.identify_breaking_point(WitnessProfile.NERVOUS, extreme)
        assert 0.0 <= bp <= 1.0


class TestStateTransitions:
    """Verify STATE_TRANSITIONS structure."""

    def test_cooperative_has_pressure_and_surprise(self):
        transitions = PredictiveResponseModel.STATE_TRANSITIONS[WitnessProfile.COOPERATIVE]
        assert QuestionIntent.PSYCHOLOGICAL_PRESSURE in transitions
        assert QuestionIntent.SURPRISE_ATTACK in transitions

    def test_defensive_has_rapport_and_pressure(self):
        transitions = PredictiveResponseModel.STATE_TRANSITIONS[WitnessProfile.DEFENSIVE]
        assert QuestionIntent.BUILD_RAPPORT in transitions
        assert QuestionIntent.PSYCHOLOGICAL_PRESSURE in transitions

    def test_hostile_has_retreat_and_pressure(self):
        transitions = PredictiveResponseModel.STATE_TRANSITIONS[WitnessProfile.HOSTILE]
        assert QuestionIntent.STRATEGIC_RETREAT in transitions
        assert QuestionIntent.PSYCHOLOGICAL_PRESSURE in transitions


# ===================================================================
# 5. UncertaintyManager Tests
# ===================================================================

class TestContingencyPlans:
    """Verify generate_contingency_plans behavior."""

    def test_returns_dict_of_response_to_string(self):
        q = _question(QuestionIntent.PROBE_WEAKNESS)
        preds = {ResponsePrediction.ADMIT: 0.6, ResponsePrediction.DENY: 0.4}
        plans = UncertaintyManager.generate_contingency_plans(q, preds)
        for k, v in plans.items():
            assert isinstance(k, ResponsePrediction)
            assert isinstance(v, str)

    def test_skips_low_probability_responses(self):
        q = _question()
        preds = {
            ResponsePrediction.ADMIT: 0.9,
            ResponsePrediction.SURPRISE: 0.03,  # Below threshold
        }
        plans = UncertaintyManager.generate_contingency_plans(q, preds)
        assert ResponsePrediction.ADMIT in plans
        assert ResponsePrediction.SURPRISE not in plans

    def test_admit_plan_contains_hebrew_keyword(self):
        q = _question()
        preds = {ResponsePrediction.ADMIT: 0.8}
        plans = UncertaintyManager.generate_contingency_plans(q, preds)
        assert "נעילת" in plans[ResponsePrediction.ADMIT]

    def test_all_response_types_have_plans(self):
        q = _question()
        preds = {resp: 0.125 for resp in ResponsePrediction}
        plans = UncertaintyManager.generate_contingency_plans(q, preds)
        assert len(plans) == len(ResponsePrediction)


class TestDecisionTree:
    """Verify create_decision_tree structure."""

    def test_returns_dict_of_int_to_dict(self):
        qs = [_question(), _question()]
        tree = UncertaintyManager.create_decision_tree(qs)
        for q_idx, branches in tree.items():
            assert isinstance(q_idx, int)
            assert isinstance(branches, dict)

    def test_each_question_has_branches(self):
        qs = [_question(), _question(), _question()]
        tree = UncertaintyManager.create_decision_tree(qs)
        # First two questions should have at least one branch
        assert len(tree[0]) > 0
        assert len(tree[1]) > 0

    def test_last_question_has_no_next(self):
        qs = [_question()]
        tree = UncertaintyManager.create_decision_tree(qs)
        # Only one question, so it should have no branches (returns None internally, excluded)
        assert tree[0] == {}


class TestSurpriseFactor:
    """Verify calculate_surprise_factor logic."""

    def test_same_expected_actual_returns_zero(self):
        result = UncertaintyManager.calculate_surprise_factor(
            ResponsePrediction.ADMIT, ResponsePrediction.ADMIT, 0.8
        )
        assert result == 0.0

    def test_deny_expected_admit_actual_positive(self):
        result = UncertaintyManager.calculate_surprise_factor(
            ResponsePrediction.DENY, ResponsePrediction.ADMIT, 0.8
        )
        assert result > 0.0

    def test_admit_expected_deny_actual_negative(self):
        result = UncertaintyManager.calculate_surprise_factor(
            ResponsePrediction.ADMIT, ResponsePrediction.DENY, 0.8
        )
        assert result < 0.0

    def test_result_is_float(self):
        result = UncertaintyManager.calculate_surprise_factor(
            ResponsePrediction.EVADE, ResponsePrediction.QUALIFY, 0.5
        )
        assert isinstance(result, float)

    def test_neutral_surprise_is_moderate(self):
        # Not in good_surprises or bad_surprises -> neutral
        result = UncertaintyManager.calculate_surprise_factor(
            ResponsePrediction.QUALIFY, ResponsePrediction.EVADE, 1.0
        )
        assert abs(result - 0.3) < 1e-6  # confidence * 0.3


class TestRecoveryStrategy:
    """Verify recovery_strategy returns correct intents."""

    def test_become_hostile_returns_strategic_retreat(self):
        gs = GameState()
        result = UncertaintyManager.recovery_strategy(gs, ResponsePrediction.BECOME_HOSTILE)
        assert result == QuestionIntent.STRATEGIC_RETREAT

    def test_evade_returns_probe_weakness(self):
        gs = GameState()
        result = UncertaintyManager.recovery_strategy(gs, ResponsePrediction.EVADE)
        assert result == QuestionIntent.PROBE_WEAKNESS

    def test_surprise_returns_lock_testimony(self):
        gs = GameState()
        result = UncertaintyManager.recovery_strategy(gs, ResponsePrediction.SURPRISE)
        assert result == QuestionIntent.LOCK_TESTIMONY

    def test_default_returns_establish_baseline(self):
        gs = GameState()
        result = UncertaintyManager.recovery_strategy(gs, ResponsePrediction.ADMIT)
        assert result == QuestionIntent.ESTABLISH_BASELINE


# ===================================================================
# 6. TimePositionOptimizer Tests
# ===================================================================

class TestAverageResponseTime:
    """Verify AVERAGE_RESPONSE_TIME constants."""

    def test_establish_baseline_time(self):
        assert TimePositionOptimizer.AVERAGE_RESPONSE_TIME[QuestionIntent.ESTABLISH_BASELINE] == 1.0

    def test_create_contradiction_time(self):
        assert TimePositionOptimizer.AVERAGE_RESPONSE_TIME[QuestionIntent.CREATE_CONTRADICTION] == 2.5

    def test_has_entries_for_all_intents(self):
        for intent in QuestionIntent:
            assert intent in TimePositionOptimizer.AVERAGE_RESPONSE_TIME


class TestOptimalPosition:
    """Verify OPTIMAL_POSITION constants."""

    def test_establish_baseline_position(self):
        assert TimePositionOptimizer.OPTIMAL_POSITION[QuestionIntent.ESTABLISH_BASELINE] == (0, 15)

    def test_closing_trap_position(self):
        assert TimePositionOptimizer.OPTIMAL_POSITION[QuestionIntent.CLOSING_TRAP] == (85, 100)

    def test_has_entries_for_all_intents(self):
        for intent in QuestionIntent:
            assert intent in TimePositionOptimizer.OPTIMAL_POSITION


class TestOptimizeQuestionOrder:
    """Verify optimize_question_order behavior."""

    def test_empty_list_returns_empty(self):
        result = TimePositionOptimizer.optimize_question_order([], 30.0)
        assert result == []

    def test_returns_same_number_of_questions(self):
        qs = _make_question_sequence()
        result = TimePositionOptimizer.optimize_question_order(qs, 30.0)
        assert len(result) == len(qs)

    def test_result_items_are_strategic_questions(self):
        qs = [_question(), _question(QuestionIntent.CLOSING_TRAP, position=95)]
        result = TimePositionOptimizer.optimize_question_order(qs, 20.0)
        for item in result:
            assert isinstance(item, StrategicQuestion)


class TestAllocateTime:
    """Verify allocate_time distribution."""

    def test_empty_list_returns_empty(self):
        result = TimePositionOptimizer.allocate_time([], 30.0)
        assert result == []

    def test_total_allocated_roughly_equals_input(self):
        qs = _make_question_sequence()
        total_time = 25.0
        times = TimePositionOptimizer.allocate_time(qs, total_time)
        assert abs(sum(times) - total_time) < 1e-6

    def test_higher_reward_gets_more_time(self):
        low_reward = _question(reward_potential=0.1, intent=QuestionIntent.ESTABLISH_BASELINE)
        high_reward = _question(reward_potential=0.9, intent=QuestionIntent.ESTABLISH_BASELINE)
        times = TimePositionOptimizer.allocate_time([low_reward, high_reward], 10.0)
        assert times[1] > times[0]


class TestCalculateROI:
    """Verify calculate_roi logic."""

    def test_zero_time_returns_zero(self):
        q = _question(reward_potential=0.8, risk_level=0.2)
        assert TimePositionOptimizer.calculate_roi(q, 0.0) == 0.0

    def test_higher_reward_lower_risk_higher_roi(self):
        good = _question(reward_potential=0.9, risk_level=0.1)
        bad = _question(reward_potential=0.2, risk_level=0.8)
        roi_good = TimePositionOptimizer.calculate_roi(good, 2.0)
        roi_bad = TimePositionOptimizer.calculate_roi(bad, 2.0)
        assert roi_good > roi_bad

    def test_result_is_float(self):
        q = _question()
        roi = TimePositionOptimizer.calculate_roi(q, 1.0)
        assert isinstance(roi, float)


class TestSuggestTimeAdjustment:
    """Verify suggest_time_adjustment messages."""

    def test_very_low_time_per_question(self):
        gs = GameState(time_remaining=3.0)
        msg = TimePositionOptimizer.suggest_time_adjustment(gs, remaining_questions=5)
        # 3.0 / 5 = 0.6 < 1.0 -> critical message
        assert "קריטיות" in msg

    def test_high_time_per_question(self):
        gs = GameState(time_remaining=50.0)
        msg = TimePositionOptimizer.suggest_time_adjustment(gs, remaining_questions=5)
        # 50 / 5 = 10.0 > 4.0 -> deepening message
        assert "להעמיק" in msg

    def test_moderate_time_returns_plan_message(self):
        gs = GameState(time_remaining=9.0)
        msg = TimePositionOptimizer.suggest_time_adjustment(gs, remaining_questions=3)
        # 9 / 3 = 3.0 -> "reasonable time"
        assert "תוכנית" in msg


# ===================================================================
# 7. StrategicExaminationPlanner Tests
# ===================================================================

class TestCreateExaminationPlan:
    """Verify full plan creation from StrategicExaminationPlanner."""

    @pytest.fixture
    def planner(self):
        return StrategicExaminationPlanner()

    def test_returns_examination_plan(self, planner):
        plan = planner.create_examination_plan(
            "TEMPORAL", 0.8, "קרה ב-1 בינואר", "קרה ב-15 בפברואר",
        )
        assert isinstance(plan, ExaminationPlan)

    def test_questions_non_empty(self, planner):
        plan = planner.create_examination_plan(
            "QUANTITATIVE", 0.9, "הסכום היה 100", "הסכום היה 200",
        )
        assert len(plan.questions) > 0

    def test_witness_profile_matches_input(self, planner):
        plan = planner.create_examination_plan(
            "TEMPORAL", 0.8, "a", "b",
            witness_profile=WitnessProfile.HOSTILE,
        )
        assert plan.witness_profile == WitnessProfile.HOSTILE

    def test_total_time_matches_input(self, planner):
        plan = planner.create_examination_plan(
            "TEMPORAL", 0.7, "a", "b", total_time_minutes=45.0,
        )
        assert plan.total_time_minutes == 45.0

    def test_critical_path_is_list_of_ints(self, planner):
        plan = planner.create_examination_plan("TEMPORAL", 0.8, "a", "b")
        assert isinstance(plan.critical_path, list)
        for idx in plan.critical_path:
            assert isinstance(idx, int)

    def test_expected_value_is_reasonable_float(self, planner):
        plan = planner.create_examination_plan("TEMPORAL", 0.8, "a", "b")
        assert isinstance(plan.expected_value, float)
        assert 0.0 <= plan.expected_value <= 1.0

    def test_risk_score_is_reasonable_float(self, planner):
        plan = planner.create_examination_plan("TEMPORAL", 0.8, "a", "b")
        assert isinstance(plan.risk_score, float)
        assert 0.0 <= plan.risk_score <= 1.0

    def test_confidence_score_is_reasonable_float(self, planner):
        plan = planner.create_examination_plan("TEMPORAL", 0.8, "a", "b")
        assert isinstance(plan.confidence_score, float)
        assert 0.0 <= plan.confidence_score <= 1.0

    def test_key_objectives_non_empty(self, planner):
        plan = planner.create_examination_plan("TEMPORAL", 0.8, "a", "b")
        assert isinstance(plan.key_objectives, list)
        assert len(plan.key_objectives) > 0
        for obj in plan.key_objectives:
            assert isinstance(obj, str)

    def test_hostile_pitfalls_contain_hebrew_warning(self, planner):
        plan = planner.create_examination_plan(
            "TEMPORAL", 0.8, "a", "b",
            witness_profile=WitnessProfile.HOSTILE,
        )
        combined = " ".join(plan.potential_pitfalls)
        assert "אגרסיבי" in combined

    def test_strategy_summary_non_empty(self, planner):
        plan = planner.create_examination_plan("TEMPORAL", 0.8, "a", "b")
        assert isinstance(plan.strategy_summary, str)
        assert len(plan.strategy_summary.strip()) > 0

    def test_alternative_paths_is_list_of_lists(self, planner):
        plan = planner.create_examination_plan("TEMPORAL", 0.8, "a", "b")
        assert isinstance(plan.alternative_paths, list)
        for path in plan.alternative_paths:
            assert isinstance(path, list)
