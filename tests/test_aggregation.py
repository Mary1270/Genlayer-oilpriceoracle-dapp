"""
Tests for deterministic helper functions: domain extraction, content
classification, the fixed-word parser, and - most importantly -
_aggregate, which is the core mechanism that fixes the rejection's
"caller chooses the only source, no verification of authority" issue.
"""

import unittest

from tests._bootstrap import OilPriceOracle, make_contract

# Shared helper instance used to call former classmethod/staticmethod
# helpers, which are now plain instance methods (GenVM lint rule E022
# requires self as the first parameter on every gl.Contract method).
_helper = make_contract()


class TestDomainExtraction(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(
            _helper._extract_domain("https://www.reuters.com/markets/oil"),
            "reuters.com",
        )

    def test_subdomains_collapse_to_same_domain(self):
        variants = [
            "https://reuters.com/a",
            "https://www.reuters.com/a",
            "https://markets.reuters.com/a",
        ]
        domains = {_helper._extract_domain(u) for u in variants}
        self.assertEqual(domains, {"reuters.com"})

    def test_invalid_scheme_returns_empty(self):
        self.assertEqual(_helper._extract_domain("ftp://reuters.com"), "")

    def test_different_publishers_stay_distinct(self):
        a = _helper._extract_domain("https://reuters.com/a")
        b = _helper._extract_domain("https://bloomberg.com/a")
        self.assertNotEqual(a, b)

    def test_port_is_stripped(self):
        self.assertEqual(
            _helper._extract_domain("https://reuters.com:8443/markets/oil"),
            "reuters.com",
        )

    def test_fragment_is_stripped(self):
        self.assertEqual(
            _helper._extract_domain("https://reuters.com/markets/oil#live-price"),
            "reuters.com",
        )

    def test_query_string_is_stripped(self):
        self.assertEqual(
            _helper._extract_domain("https://reuters.com/markets/oil?symbol=BRENT&refresh=1"),
            "reuters.com",
        )

    def test_multi_part_tld_keeps_distinct_uk_publishers_independent(self):
        a = _helper._extract_domain("https://www.thisismoney.co.uk/oil")
        b = _helper._extract_domain("https://www.cityam.co.uk/oil")
        self.assertEqual(a, "thisismoney.co.uk")
        self.assertEqual(b, "cityam.co.uk")
        self.assertNotEqual(a, b)

    def test_multi_part_tld_merges_own_subdomains(self):
        a = _helper._extract_domain("https://markets.thisismoney.co.uk/oil")
        b = _helper._extract_domain("https://www.thisismoney.co.uk/oil")
        self.assertEqual(a, b)
        self.assertEqual(a, "thisismoney.co.uk")


class TestExtractPath(unittest.TestCase):
    """_extract_path is the new helper backing the domain+endpoint
    form of required_source_domains (the steward's follow-up
    improvement on top of the original domain-only commitment)."""

    def test_basic_path(self):
        self.assertEqual(
            _helper._extract_path("https://reuters.com/markets/energy"),
            "/markets/energy",
        )

    def test_root_path_is_empty(self):
        self.assertEqual(_helper._extract_path("https://reuters.com"), "")
        self.assertEqual(_helper._extract_path("https://reuters.com/"), "")

    def test_trailing_slash_stripped(self):
        self.assertEqual(
            _helper._extract_path("https://reuters.com/markets/energy/"),
            "/markets/energy",
        )

    def test_query_and_fragment_stripped(self):
        self.assertEqual(
            _helper._extract_path("https://reuters.com/markets/energy?x=1#frag"),
            "/markets/energy",
        )

    def test_invalid_scheme_returns_empty(self):
        self.assertEqual(_helper._extract_path("ftp://reuters.com/markets/energy"), "")

    def test_lowercased(self):
        self.assertEqual(
            _helper._extract_path("https://reuters.com/Markets/Energy"),
            "/markets/energy",
        )


class TestParseEndpointRequirement(unittest.TestCase):
    """_parse_endpoint_requirement parses the three accepted input
    forms for a required_source_domains entry."""

    def test_bare_domain_has_no_path(self):
        self.assertEqual(
            _helper._parse_endpoint_requirement("reuters.com"), ("reuters.com", "")
        )

    def test_domain_slash_path_form(self):
        self.assertEqual(
            _helper._parse_endpoint_requirement("reuters.com/markets/energy"),
            ("reuters.com", "/markets/energy"),
        )

    def test_full_url_form(self):
        self.assertEqual(
            _helper._parse_endpoint_requirement("https://reuters.com/markets/energy"),
            ("reuters.com", "/markets/energy"),
        )

    def test_trailing_slash_and_case_normalized(self):
        self.assertEqual(
            _helper._parse_endpoint_requirement("Reuters.com/Markets/Energy/"),
            ("reuters.com", "/markets/energy"),
        )

    def test_empty_entry_returns_empty_tuple(self):
        self.assertEqual(_helper._parse_endpoint_requirement(""), ("", ""))
        self.assertEqual(_helper._parse_endpoint_requirement(None), ("", ""))

    def test_bare_domain_with_trailing_slash_has_no_path(self):
        self.assertEqual(
            _helper._parse_endpoint_requirement("reuters.com/"), ("reuters.com", "")
        )


class TestReputableAllowlistRegression(unittest.TestCase):
    """
    Regression test for a real bug found during audit: an earlier
    version of REPUTABLE_PRICE_DOMAINS contained the literal string
    "markets.businessinsider.com", which could NEVER match, because
    _registrable_domain always normalizes to 2 labels (unless it's a
    known multi-part-suffix TLD) - so any businessinsider.com URL,
    with or without a "markets." subdomain, always resolves to
    "businessinsider.com", never the 3-label form. The allowlist entry
    was silently dead: no submitted URL could ever be credited as
    reputable via that domain. Fixed by using the correct 2-label form.
    """

    def test_businessinsider_domain_actually_matches_allowlist(self):
        for url in (
            "https://www.businessinsider.com/oil-prices",
            "https://markets.businessinsider.com/commodities/oil-price",
        ):
            domain = _helper._extract_domain(url)
            self.assertEqual(domain, "businessinsider.com")
            self.assertIn(domain, OilPriceOracle.REPUTABLE_PRICE_DOMAINS)

    def test_no_allowlist_entry_is_unreachable(self):
        # For every entry in the allowlist, confirm that a plausible
        # URL on that exact domain actually normalizes back to an
        # allowlisted value - i.e. no entry in the list is dead code
        # the way "markets.businessinsider.com" used to be.
        for domain in OilPriceOracle.REPUTABLE_PRICE_DOMAINS:
            url = f"https://{domain}/oil-price"
            extracted = _helper._extract_domain(url)
            self.assertEqual(
                extracted,
                domain,
                f"Allowlist entry {domain!r} does not round-trip through "
                f"_extract_domain (got {extracted!r}) - this entry can "
                f"never actually match and is dead.",
            )


class TestContentClassification(unittest.TestCase):
    def test_ok_content(self):
        status, usable = _helper._classify_content(
            "Brent crude oil is currently trading at $73.40 per barrel today. " * 2
        )
        self.assertEqual(status, "ok")
        self.assertTrue(usable)

    def test_empty(self):
        status, usable = _helper._classify_content("   ")
        self.assertEqual(status, "empty")
        self.assertFalse(usable)

    def test_too_short_is_malformed(self):
        status, usable = _helper._classify_content("n/a")
        self.assertEqual(status, "malformed")
        self.assertFalse(usable)


class TestParseFixedWord(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(
            _helper._parse_fixed_word("Match", OilPriceOracle.INSTRUMENT_WORDS, "Unclear"),
            "Match",
        )

    def test_labeled_line_extracted_with_label(self):
        raw = "INSTRUMENT: Match\nFRESHNESS: Current\nCOMPARISON: Above"
        self.assertEqual(
            _helper._parse_fixed_word(
                raw, OilPriceOracle.INSTRUMENT_WORDS, "Unclear", label="INSTRUMENT"
            ),
            "Match",
        )
        self.assertEqual(
            _helper._parse_fixed_word(
                raw, OilPriceOracle.FRESHNESS_WORDS, "Unknown", label="FRESHNESS"
            ),
            "Current",
        )
        self.assertEqual(
            _helper._parse_fixed_word(
                raw, OilPriceOracle.COMPARISON_WORDS, "Unclear", label="COMPARISON"
            ),
            "Above",
        )

    def test_labeled_line_not_matched_without_label_argument(self):
        # Without passing the matching label, "INSTRUMENT: Match" as a
        # whole line does not equal "Match" alone - this pins down
        # exactly the bug that was found and fixed: labels must be
        # explicitly stripped, they can't be guessed.
        raw = "INSTRUMENT: Match\nFRESHNESS: Current\nCOMPARISON: Above"
        self.assertEqual(
            _helper._parse_fixed_word(raw, OilPriceOracle.INSTRUMENT_WORDS, "Unclear"),
            "Unclear",
        )

    def test_wrong_label_does_not_match(self):
        # Passing the FRESHNESS label while scanning for an
        # INSTRUMENT-vocabulary word must not accidentally cross-match.
        raw = "INSTRUMENT: Match\nFRESHNESS: Current"
        self.assertEqual(
            _helper._parse_fixed_word(
                raw, OilPriceOracle.INSTRUMENT_WORDS, "Unclear", label="FRESHNESS"
            ),
            "Unclear",
        )

    def test_default_on_garbage(self):
        self.assertEqual(
            _helper._parse_fixed_word("blah blah", OilPriceOracle.FRESHNESS_WORDS, "Unknown"),
            "Unknown",
        )

    def test_empty_defaults(self):
        self.assertEqual(
            _helper._parse_fixed_word("", OilPriceOracle.COMPARISON_WORDS, "Unclear"),
            "Unclear",
        )


class TestParsePrice(unittest.TestCase):
    """
    Unit tests for _parse_price - the pure, deterministic helper that
    parses BOTH each source's self-reported PRICE line and the
    agreement's stored threshold_price, using identical logic for
    both. See _parse_price's own docstring for the full list of
    accepted/rejected formats this pins down.
    """

    def test_integer_price(self):
        self.assertEqual(_helper._parse_price("73"), 73.0)

    def test_decimal_price(self):
        self.assertEqual(_helper._parse_price("73.42"), 73.42)

    def test_dollar_prefixed_price(self):
        self.assertEqual(_helper._parse_price("$73.42"), 73.42)

    def test_comma_separated_price(self):
        self.assertEqual(_helper._parse_price("1,234.56"), 1234.56)

    def test_negative_price(self):
        # Real oil prices have gone negative historically (WTI, April
        # 2020) - _parse_price must support this, not just assume
        # prices are always positive.
        self.assertEqual(_helper._parse_price("-37.63"), -37.63)

    def test_trailing_unit_text_ignored(self):
        self.assertEqual(_helper._parse_price("80 USD per barrel"), 80.0)

    def test_malformed_string_returns_none(self):
        self.assertIsNone(_helper._parse_price("banana"))

    def test_empty_input_returns_none(self):
        self.assertIsNone(_helper._parse_price(""))
        self.assertIsNone(_helper._parse_price("   "))
        self.assertIsNone(_helper._parse_price(None))

    def test_ambiguous_two_numbers_returns_none(self):
        self.assertIsNone(_helper._parse_price("$73 or $85"))

    def test_number_not_at_start_returns_none(self):
        self.assertIsNone(_helper._parse_price("USD 80.00 per barrel"))

    def test_malformed_thousands_grouping_returns_none(self):
        self.assertIsNone(_helper._parse_price("1,23.45"))
        self.assertIsNone(_helper._parse_price("12,3456"))

    def test_bare_decimal_point_returns_none(self):
        self.assertIsNone(_helper._parse_price("."))
        self.assertIsNone(_helper._parse_price(".73"))

    def test_literal_unclear_returns_none(self):
        # The model is instructed to answer literally "Unclear" for
        # PRICE when it can't find a usable number.
        self.assertIsNone(_helper._parse_price("Unclear"))

    def test_threshold_and_source_price_use_identical_parsing(self):
        # Both call sites (threshold_price validation in
        # create_agreement, and each source's extracted PRICE in
        # resolve_agreement) go through this exact same function -
        # this test just re-confirms a representative threshold-style
        # string parses the same way a source-style string does.
        self.assertEqual(
            _helper._parse_price("80 USD per barrel"),
            _helper._parse_price("$80"),
        )


class TestExtractLabeledValue(unittest.TestCase):
    def test_extracts_value_after_label(self):
        raw = "INSTRUMENT: Match\nPRICE: 73.42\nCOMPARISON: Above"
        self.assertEqual(
            _helper._extract_labeled_value(raw, "PRICE"), "73.42"
        )

    def test_missing_label_returns_empty_string(self):
        raw = "INSTRUMENT: Match\nCOMPARISON: Above"
        self.assertEqual(_helper._extract_labeled_value(raw, "PRICE"), "")

    def test_case_insensitive_label_matching(self):
        raw = "price: 73.42"
        self.assertEqual(
            _helper._extract_labeled_value(raw, "PRICE"), "73.42"
        )



    """
    The core corroboration fix. Only records that are fetch-ok,
    non-duplicate, reputable, AND quality_flag=='ok' (correct
    instrument/unit AND fresh) count toward the final verdict.
    """

    def _rec(
        self,
        comparison,
        domain,
        fetch_status="ok",
        dup=False,
        reputable=True,
        quality="ok",
    ):
        return {
            "url": f"https://{domain}/a",
            "domain": domain,
            "is_duplicate_domain": dup,
            "is_reputable": reputable,
            "fetch_status": fetch_status,
            "quality_flag": quality,
            "comparison": comparison,
        }

    def test_two_independent_above_yields_above(self):
        records = [
            self._rec("Above", "reuters.com"),
            self._rec("Above", "bloomberg.com"),
        ]
        self.assertEqual(_helper._aggregate(records), "Above")

    def test_two_independent_below_yields_below(self):
        records = [
            self._rec("Below", "reuters.com"),
            self._rec("Below", "bloomberg.com"),
        ]
        self.assertEqual(_helper._aggregate(records), "Below")

    def test_single_source_never_enough(self):
        records = [self._rec("Above", "reuters.com")]
        self.assertEqual(_helper._aggregate(records), "Indeterminate")

    def test_non_reputable_source_excluded_even_if_agreeing(self):
        # Two sources say "Above", but one isn't on the allowlist -
        # only one REAL independent source remains -> Indeterminate.
        records = [
            self._rec("Above", "reuters.com"),
            self._rec("Above", "some-random-blog.example", reputable=False),
        ]
        self.assertEqual(_helper._aggregate(records), "Indeterminate")

    def test_stale_source_excluded_even_if_reputable(self):
        records = [
            self._rec("Above", "reuters.com"),
            self._rec("Above", "bloomberg.com", quality="stale_or_unknown_freshness"),
        ]
        self.assertEqual(_helper._aggregate(records), "Indeterminate")

    def test_instrument_mismatch_excluded_even_if_reputable_and_fresh(self):
        records = [
            self._rec("Above", "reuters.com"),
            self._rec("Above", "bloomberg.com", quality="instrument_or_unit_mismatch"),
        ]
        self.assertEqual(_helper._aggregate(records), "Indeterminate")

    def test_duplicate_domain_not_counted_twice(self):
        records = [
            self._rec("Above", "reuters.com"),
            self._rec("Above", "reuters.com", dup=True),
        ]
        self.assertEqual(_helper._aggregate(records), "Indeterminate")

    def test_conflicting_evidence_yields_indeterminate(self):
        records = [
            self._rec("Above", "reuters.com"),
            self._rec("Below", "bloomberg.com"),
        ]
        self.assertEqual(_helper._aggregate(records), "Indeterminate")

    def test_majority_with_dissent_still_resolves(self):
        records = [
            self._rec("Above", "reuters.com"),
            self._rec("Above", "bloomberg.com"),
            self._rec("Below", "wsj.com"),
        ]
        self.assertEqual(_helper._aggregate(records), "Above")

    def test_equal_requires_same_threshold_as_above_below(self):
        records = [
            self._rec("Equal", "reuters.com"),
            self._rec("Equal", "bloomberg.com"),
        ]
        self.assertEqual(_helper._aggregate(records), "Equal")

    def test_failed_fetches_excluded(self):
        records = [
            self._rec("Unclear", "reuters.com", fetch_status="timeout", quality="instrument_or_unit_mismatch"),
            self._rec("Unclear", "bloomberg.com", fetch_status="inaccessible", quality="instrument_or_unit_mismatch"),
            self._rec("Above", "wsj.com"),
        ]
        self.assertEqual(_helper._aggregate(records), "Indeterminate")


if __name__ == "__main__":
    unittest.main(verbosity=2)
