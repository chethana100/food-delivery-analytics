from datetime import date

import pytest

from src import periods as p


def test_week_is_monday_to_sunday_across_year_end():
    assert p.week_range(date(2026, 1, 1)) == (date(2025, 12, 29), date(2026, 1, 4))   # Thursday
    assert p.week_range(date(2026, 10, 19)) == (date(2026, 10, 19), date(2026, 10, 25))  # Monday
    assert p.week_range(date(2026, 10, 18)) == (date(2026, 10, 12), date(2026, 10, 18))  # Sunday


@pytest.mark.parametrize("d,exp", [
    (date(2026, 2, 10), (date(2026, 2, 1), date(2026, 2, 28))),
    (date(2028, 2, 10), (date(2028, 2, 1), date(2028, 2, 29))),     # leap year
    (date(2026, 12, 31), (date(2026, 12, 1), date(2026, 12, 31))),
])
def test_month_range(d, exp):
    assert p.month_range(d) == exp


def test_year_and_resolve():
    assert p.year_range(date(2026, 6, 6)) == (date(2026, 1, 1), date(2026, 12, 31))
    assert p.resolve_period("Current year", date(2026, 6, 6)) == (date(2026, 1, 1), date(2026, 12, 31))
    assert p.resolve_period("Custom range", date(2026, 1, 1),
                            (date(2026, 3, 5), date(2026, 3, 1))) == (date(2026, 3, 1), date(2026, 3, 5))
    with pytest.raises(ValueError):
        p.resolve_period("Custom range", date(2026, 1, 1))
