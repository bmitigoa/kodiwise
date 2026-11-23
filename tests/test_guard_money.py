import pytest

from chat import guard

ALLOWED = [45510.0, 30244.0, 67019.0, 60000.0, 2.0]


@pytest.mark.parametrize("raw,expected", [
    ("The rent is KES45,510 a month.", "The rent is KES 45,510 a month."),
    ("The rent is KES 45, 510 a month.", "The rent is KES 45,510 a month."),
    ("The rent is 45,510KES a month.", "The rent is KES 45,510 a month."),
    ("The rent is 45,510 KES a month.", "The rent is KES 45,510 a month."),
    ("Between K ES 30,244 and K ES 67,019.", "Between KES 30,244 and KES 67,019."),
    ("From KES30,244to KES67,019.", "From KES 30,244 to KES 67,019."),
    ("It is Ksh 45,510.", "It is KES 45,510."),
    ("It is kes 45510.", "It is KES 45,510."),
    ("About KES 45,510, typically.", "About KES 45,510, typically."),
    ("Around KES 60k a month.", "Around KES 60,000 a month."),
    ("Roughly KES 45,600.", "Roughly KES 45,510."),            # within 1%: the tool's own value is used
])
def test_broken_forms_are_rewritten_to_the_standard_format(raw, expected):
    assert guard.normalize_money(raw, ALLOWED) == expected


def test_unmatched_figure_returns_none():
    assert guard.normalize_money("It is KES 99,500.", ALLOWED) is None
    assert guard.normalize_money("It is 99,500 KES.", ALLOWED) is None
    assert guard.normalize_money("Between KES 45,510 and KES 52,000.", ALLOWED) is None


def test_text_without_money_is_unchanged_and_counts_are_not_touched():
    s = "A 2 bedroom with 2 bathrooms; likes parking."
    assert guard.normalize_money(s, ALLOWED) == s


def test_words_ending_in_kes_are_not_mistaken_for_the_currency():
    s = "She likes 2 bedrooms."
    assert guard.normalize_money(s, ALLOWED) == s


def test_exact_case_from_review_gets_a_space_on_both_sides_of_each_figure():
    assert guard.normalize_money("KES30,244to KES67,019", ALLOWED) == "KES 30,244 to KES 67,019"
    assert guard.normalize_money("Range:KES30,244to KES67,019.", ALLOWED) == "Range: KES 30,244 to KES 67,019."
    assert guard.normalize_money("(KES 45,510)", ALLOWED) == "(KES 45,510)"
    assert guard.normalize_money("It is KES 45,510, or 60,000KES!", ALLOWED) == "It is KES 45,510, or KES 60,000!"
