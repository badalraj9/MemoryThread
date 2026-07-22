"""Tests for contradiction classifier."""

import pytest
from memory_thread.nervous.contradiction_classifier import (
    LightweightClassifier,
    CONTRADICTION,
    ENTAILMENT,
    NEUTRAL,
)


class TestLightweightClassifier:
    def setup_method(self):
        self.clf = LightweightClassifier()

    def test_antonym_contradiction(self):
        label, conf = self.clf.classify("User likes dark mode", "User hates dark mode")
        assert label == CONTRADICTION
        assert conf > 0.5

    def test_neutral_unrelated(self):
        label, conf = self.clf.classify("User likes dark mode", "The sky is blue")
        assert label == NEUTRAL

    def test_empty_strings(self):
        label, conf = self.clf.classify("", "")
        assert label == NEUTRAL

    def test_entailment_shared_keywords(self):
        label, conf = self.clf.classify("User likes dark mode", "User likes cats")
        assert label == ENTAILMENT

    def test_identical_texts(self):
        label, conf = self.clf.classify("hello world", "hello world")
        assert label in (ENTAILMENT, NEUTRAL)
