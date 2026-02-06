"""Unit tests for mathematical utility functions."""

import pytest

from utils.math_utils import hypergeometric_at_least, hypergeometric_probability


class TestHypergeometricProbability:
    """Tests for hypergeometric_probability function."""

    def test_opening_hand_exactly_one_playset(self) -> None:
        """Probability of exactly 1 copy of a 4-of in 7-card opening hand (60-card deck).

        Reference: https://aetherhub.com/Apps/HyperGeometric
        Expected: ~33.63%
        """
        prob = hypergeometric_probability(
            population=60,
            successes_in_pop=4,
            sample_size=7,
            successes_in_sample=1,
        )
        assert 0.335 <= prob <= 0.337

    def test_opening_hand_exactly_two_playset(self) -> None:
        """Probability of exactly 2 copies of a 4-of in 7-card opening hand.

        Expected: ~5.93%
        """
        prob = hypergeometric_probability(60, 4, 7, 2)
        assert 0.058 <= prob <= 0.060

    def test_limited_format_40_card_deck(self) -> None:
        """Probability of exactly 1 bomb in 7-card hand from 40-card limited deck (1 copy).

        Expected: 17.5%
        """
        prob = hypergeometric_probability(40, 1, 7, 1)
        assert abs(prob - 0.175) < 0.001

    def test_drawing_zero(self) -> None:
        """Probability of drawing 0 copies of a 4-of.

        Expected: ~60.05% (more likely to miss than hit)
        """
        prob = hypergeometric_probability(60, 4, 7, 0)
        assert 0.599 <= prob <= 0.602

    def test_impossible_draw_raises_error(self) -> None:
        """Requesting more target cards than exist in deck raises ValueError."""
        with pytest.raises(ValueError, match="cannot exceed successes in population"):
            hypergeometric_probability(60, 4, 7, 5)

    def test_guaranteed_draw(self) -> None:
        """Drawing all copies when sample equals available copies.

        If deck has 4 copies and we draw all 60 cards, P(draw all 4) = 1.0
        """
        prob = hypergeometric_probability(60, 4, 60, 4)
        assert prob == 1.0

    def test_single_card_deck(self) -> None:
        """Edge case: 1-card deck with 1 copy, draw 1."""
        prob = hypergeometric_probability(1, 1, 1, 1)
        assert prob == 1.0

    def test_zero_copies_in_deck_raises_error(self) -> None:
        """If no target cards in deck, requesting any raises ValueError."""
        with pytest.raises(ValueError, match="cannot exceed successes in population"):
            hypergeometric_probability(60, 0, 7, 1)

    def test_zero_copies_zero_target(self) -> None:
        """If no target cards and we want 0, probability is 1."""
        prob = hypergeometric_probability(60, 0, 7, 0)
        assert prob == 1.0


class TestHypergeometricAtLeast:
    """Tests for hypergeometric_at_least function."""

    def test_at_least_one_playset_opening_hand(self) -> None:
        """Probability of at least 1 copy of a 4-of in 7-card hand.

        P(X >= 1) = 1 - P(X = 0) = 1 - 0.6005 = ~39.95%
        """
        prob = hypergeometric_at_least(60, 4, 7, 1)
        assert 0.398 <= prob <= 0.401

    def test_at_least_zero_always_one(self) -> None:
        """P(X >= 0) should always be 1.0."""
        prob = hypergeometric_at_least(60, 4, 7, 0)
        assert prob == 1.0

    def test_at_least_more_than_possible(self) -> None:
        """Requesting more than available returns 0."""
        prob = hypergeometric_at_least(60, 4, 7, 5)
        assert prob == 0.0

    def test_turn_three_on_play(self) -> None:
        """P(at least 1 of a 4-of by turn 3 on the play: 9 cards seen).

        Expected: ~48.75%
        """
        prob = hypergeometric_at_least(60, 4, 9, 1)
        assert 0.486 <= prob <= 0.489

    def test_turn_three_on_draw(self) -> None:
        """P(at least 1 of a 4-of by turn 3 on the draw: 10 cards seen).

        Expected: ~52.35%
        """
        prob = hypergeometric_at_least(60, 4, 10, 1)
        assert 0.52 <= prob <= 0.53

    def test_limited_deck_at_least_one_land(self) -> None:
        """P(at least 1 land in 7 cards from 40-card deck with 17 lands).

        Expected: very high (~98.69%)
        """
        prob = hypergeometric_at_least(40, 17, 7, 1)
        assert prob > 0.98


class TestInputValidation:
    """Tests for input validation error handling."""

    def test_negative_population_raises(self) -> None:
        """Negative population should raise ValueError."""
        with pytest.raises(ValueError, match="Population must be non-negative"):
            hypergeometric_probability(-1, 4, 7, 1)

    def test_negative_successes_raises(self) -> None:
        """Negative successes in population should raise ValueError."""
        with pytest.raises(ValueError, match="Successes in population must be non-negative"):
            hypergeometric_probability(60, -1, 7, 1)

    def test_negative_sample_raises(self) -> None:
        """Negative sample size should raise ValueError."""
        with pytest.raises(ValueError, match="Sample size must be non-negative"):
            hypergeometric_probability(60, 4, -1, 1)

    def test_negative_target_raises(self) -> None:
        """Negative target successes should raise ValueError."""
        with pytest.raises(ValueError, match="Successes in sample must be non-negative"):
            hypergeometric_probability(60, 4, 7, -1)

    def test_successes_exceed_population_raises(self) -> None:
        """Successes in population exceeding population should raise."""
        with pytest.raises(ValueError, match="cannot exceed population"):
            hypergeometric_probability(60, 61, 7, 1)

    def test_sample_exceed_population_raises(self) -> None:
        """Sample size exceeding population should raise."""
        with pytest.raises(ValueError, match="cannot exceed population"):
            hypergeometric_probability(60, 4, 61, 1)

    def test_target_exceed_successes_raises(self) -> None:
        """Target successes exceeding available successes should raise."""
        with pytest.raises(ValueError, match="cannot exceed successes in population"):
            hypergeometric_probability(60, 4, 7, 5)

    def test_target_exceed_sample_raises(self) -> None:
        """Target successes exceeding sample size should raise."""
        with pytest.raises(ValueError, match="cannot exceed sample size"):
            hypergeometric_probability(60, 10, 7, 8)

    def test_at_least_negative_min_raises(self) -> None:
        """Negative minimum successes in at_least should raise."""
        with pytest.raises(ValueError, match="Minimum successes must be non-negative"):
            hypergeometric_at_least(60, 4, 7, -1)


class TestProbabilityBounds:
    """Tests to verify probability values are always in valid range."""

    def test_probability_between_zero_and_one(self) -> None:
        """Probabilities should always be in [0, 1]."""
        test_cases = [
            (60, 4, 7, 0),
            (60, 4, 7, 1),
            (60, 4, 7, 2),
            (60, 4, 7, 3),
            (60, 4, 7, 4),
            (100, 20, 15, 5),
            (40, 17, 7, 3),
        ]
        for pop, k, n, x in test_cases:
            prob = hypergeometric_probability(pop, k, n, x)
            assert 0.0 <= prob <= 1.0, f"Probability out of bounds for ({pop}, {k}, {n}, {x})"

    def test_at_least_probability_bounds(self) -> None:
        """At-least probabilities should be in [0, 1]."""
        test_cases = [
            (60, 4, 7, 0),
            (60, 4, 7, 1),
            (60, 4, 7, 2),
            (100, 20, 15, 5),
        ]
        for pop, k, n, min_x in test_cases:
            prob = hypergeometric_at_least(pop, k, n, min_x)
            assert (
                0.0 <= prob <= 1.0
            ), f"At-least probability out of bounds for ({pop}, {k}, {n}, {min_x})"

    def test_sum_of_all_probabilities_equals_one(self) -> None:
        """Sum of P(X=k) for all valid k should equal 1.0."""
        pop, k_pop, n = 60, 4, 7
        total = sum(hypergeometric_probability(pop, k_pop, n, k) for k in range(min(k_pop, n) + 1))
        assert abs(total - 1.0) < 1e-10
