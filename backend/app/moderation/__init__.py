"""Screening of what people type into the assistant: profanity, personal insults, discrimination and threats in Vietnamese.

`check(text)` is a rule layer: a lexicon (lexicon.yaml) matched after the normalisations people use to slip past a plain word list.
It is deliberately conservative (no ambiguous words) because a false alarm on an ordinary military or administrative sentence is
worse than a miss that the next layer, or a person reading the audit trail, catches.
"""
from .check import CATEGORY_LABELS, Hit, Verdict, check
from .policy import screen

__all__ = ["CATEGORY_LABELS", "Hit", "Verdict", "check", "screen"]
