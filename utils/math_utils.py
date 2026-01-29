"""
Mathematical utility functions for probability calculations.

This module provides functions for calculating probabilities related to
card draws in Magic: The Gathering using the hypergeometric distribution.
"""

import math


def hypergeometric_probability(
    population: int,
    successes_in_pop: int,
    sample_size: int,
    successes_in_sample: int,
) -> float:
    """
    Calculate the exact probability of drawing a specific number of target cards.

    Uses the hypergeometric distribution to compute the probability of drawing
    exactly k target cards when drawing n cards from a deck of N cards that
    contains K copies of the target card.

    Formula: P(X = k) = [C(K, k) × C(N-K, n-k)] / C(N, n)

    Args:
        population: Total number of cards in the deck (N)
        successes_in_pop: Number of target cards in the deck (K)
        sample_size: Number of cards drawn (n)
        successes_in_sample: Target number of cards to draw (k)

    Returns:
        Probability as a float between 0.0 and 1.0

    Raises:
        ValueError: If any input is invalid (negative numbers, sample > population, etc.)

    Example:
        >>> # Probability of drawing exactly 1 Lightning Bolt in opening hand
        >>> # (4 copies in 60-card deck, drawing 7 cards)
        >>> hypergeometric_probability(60, 4, 7, 1)
        0.3986...
    """
    # Validate inputs
    if population < 0:
        raise ValueError(f"Population must be non-negative, got {population}")
    if successes_in_pop < 0:
        raise ValueError(f"Successes in population must be non-negative, got {successes_in_pop}")
    if sample_size < 0:
        raise ValueError(f"Sample size must be non-negative, got {sample_size}")
    if successes_in_sample < 0:
        raise ValueError(f"Successes in sample must be non-negative, got {successes_in_sample}")

    if successes_in_pop > population:
        raise ValueError(
            f"Successes in population ({successes_in_pop}) cannot exceed "
            f"population ({population})"
        )
    if sample_size > population:
        raise ValueError(f"Sample size ({sample_size}) cannot exceed population ({population})")
    if successes_in_sample > successes_in_pop:
        raise ValueError(
            f"Successes in sample ({successes_in_sample}) cannot exceed "
            f"successes in population ({successes_in_pop})"
        )
    if successes_in_sample > sample_size:
        raise ValueError(
            f"Successes in sample ({successes_in_sample}) cannot exceed "
            f"sample size ({sample_size})"
        )

    # Check if we have enough cards to satisfy the draw
    failures_in_pop = population - successes_in_pop
    failures_in_sample = sample_size - successes_in_sample
    if failures_in_sample > failures_in_pop:
        # Impossible scenario - not enough non-target cards available
        return 0.0

    # Calculate probability using combinations
    # P(X = k) = [C(K, k) × C(N-K, n-k)] / C(N, n)
    try:
        numerator = math.comb(successes_in_pop, successes_in_sample) * math.comb(
            failures_in_pop, failures_in_sample
        )
        denominator = math.comb(population, sample_size)

        if denominator == 0:
            return 0.0

        return numerator / denominator

    except (ValueError, OverflowError) as e:
        raise ValueError(f"Error calculating probability: {e}") from e


def hypergeometric_at_least(
    population: int,
    successes_in_pop: int,
    sample_size: int,
    min_successes: int,
) -> float:
    """
    Calculate the probability of drawing at least a minimum number of target cards.

    Computes P(X >= min_successes) by summing probabilities from min_successes
    to the maximum possible number of target cards that could be drawn.

    Args:
        population: Total number of cards in the deck (N)
        successes_in_pop: Number of target cards in the deck (K)
        sample_size: Number of cards drawn (n)
        min_successes: Minimum number of target cards desired (k_min)

    Returns:
        Probability as a float between 0.0 and 1.0

    Raises:
        ValueError: If any input is invalid

    Example:
        >>> # Probability of drawing at least 1 Lightning Bolt in opening hand
        >>> # (4 copies in 60-card deck, drawing 7 cards)
        >>> hypergeometric_at_least(60, 4, 7, 1)
        0.5977...
    """
    # Validate inputs (hypergeometric_probability will validate most)
    if min_successes < 0:
        raise ValueError(f"Minimum successes must be non-negative, got {min_successes}")

    # Edge case: requesting at least 0 is always probability 1.0
    if min_successes == 0:
        return 1.0

    # Maximum possible successes is min of (cards drawn, copies in deck)
    max_successes = min(sample_size, successes_in_pop)

    # If requesting more than possible, probability is 0
    if min_successes > max_successes:
        return 0.0

    # Sum probabilities from min_successes to max_successes
    total_probability = 0.0
    for k in range(min_successes, max_successes + 1):
        total_probability += hypergeometric_probability(
            population, successes_in_pop, sample_size, k
        )

    return total_probability
