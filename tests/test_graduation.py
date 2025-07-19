import pytest
from bot.utils.graduation import calculate_graduation_year

@pytest.mark.parametrize(
    "group, expected_year",
    [
        ("Б20-505", 2024),
        ("С20-2131", 2025),
        ("М22-1232", 2024),
        ("b20-505", 2024),
        ("c20-2131", 2025),
        ("m22-1232", 2024),
        ("asdf", None),
        (None, None),
        ("", None),
    ],
)
def test_calculate_graduation_year(group, expected_year):
    assert calculate_graduation_year(group) == expected_year
