"""Text similarity helpers shared by the license detection tiers."""

from typing import Set


def create_bigrams(text: str) -> Set[str]:
    """Create character bigrams from text."""
    return {text[i:i + 2] for i in range(len(text) - 1)}


def dice_coefficient(set1: Set[str], set2: Set[str]) -> float:
    """Calculate the Dice-Sørensen coefficient between two sets."""
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    return (2.0 * intersection) / (len(set1) + len(set2))
