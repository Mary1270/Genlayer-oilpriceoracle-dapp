"""
Tests that _build_prompt actually contains every guardrail this
contract claims to enforce - turning documentation claims into
checked properties of the code, same discipline as TruthBeacon.
"""

import unittest

from tests._bootstrap import OilPriceOracle, make_contract

# Shared helper instance used to call former classmethod/staticmethod
# helpers, which are now plain instance methods (GenVM lint rule E022
# requires self as the first parameter on every gl.Contract method).
_helper = make_contract()


class TestPromptGuardrails(unittest.TestCase):
    def setUp(self):
        self.prompt = _helper._build_prompt(
            "Brent crude oil", "80 USD per barrel", "Example source content"
        )

    def test_contains_injection_guardrail(self):
        self.assertIn("untrusted data", self.prompt)
        self.assertIn("HTML", self.prompt)

    def test_injection_guardrail_covers_all_three_fields(self):
        # The guardrail must explicitly cover the requested instrument
        # and threshold price, not just fetched source content - both
        # are caller-controlled at create_agreement time and are just
        # as attacker-controlled as fetched page content.
        self.assertIn("ALL THREE text blocks", self.prompt)

    def test_contains_instrument_question(self):
        self.assertIn("INSTRUMENT", self.prompt)
        self.assertIn("Mismatch", self.prompt)

    def test_contains_freshness_question(self):
        self.assertIn("FRESHNESS", self.prompt)
        self.assertIn("Stale", self.prompt)

    def test_contains_comparison_question(self):
        self.assertIn("COMPARISON", self.prompt)

    def test_contains_no_conversion_guardrail(self):
        # The model must NOT silently convert currency/units itself -
        # that's exactly the kind of per-validator arithmetic that
        # could diverge and break consensus.
        self.assertIn("do NOT attempt to convert", self.prompt)

    def test_fixed_output_format_specified(self):
        self.assertIn("INSTRUMENT: <your answer>", self.prompt)
        self.assertIn("FRESHNESS: <your answer>", self.prompt)
        self.assertIn("PRICE: <numeric value, or Unclear>", self.prompt)
        self.assertIn("COMPARISON: <your answer>", self.prompt)

    def test_price_field_present_and_no_conversion_or_invention(self):
        self.assertIn("PRICE", self.prompt)
        self.assertIn("do NOT perform currency conversion", self.prompt)
        self.assertIn("Do NOT invent a price", self.prompt)


class TestEquivalencePrinciple(unittest.TestCase):
    def test_references_actual_schema_fields(self):
        principle = OilPriceOracle.EQUIVALENCE_PRINCIPLE
        for field_name in (
            "final_verdict",
            "winner",
            "fetch_status",
            "quality_flag",
            "comparison",
            "independent_source_count",
        ):
            self.assertIn(field_name, principle)

    def test_is_nontrivial(self):
        self.assertGreater(len(OilPriceOracle.EQUIVALENCE_PRINCIPLE), 50)

    def test_price_field_explicitly_excluded_from_equivalence(self):
        # The exact numeric price is audit metadata only - different
        # validators may legitimately extract slightly different
        # numbers from a live source, and that must NOT by itself
        # make two results non-equivalent. The principle must say so
        # explicitly, not just omit mentioning "price" (an omission
        # could be misread by the NLP comparator as "price also
        # matters, it just wasn't listed").
        principle = OilPriceOracle.EQUIVALENCE_PRINCIPLE
        self.assertIn("price", principle.lower())
        self.assertIn("audit metadata", principle.lower())
        self.assertIn("NEVER considered for equivalence", principle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
