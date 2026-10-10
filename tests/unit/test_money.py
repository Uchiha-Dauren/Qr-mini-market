"""Verify integer arithmetic, weight rounding, and strict domain inputs."""

from decimal import Decimal

import pytest

from app.core.enums import ProductUnit
from app.core.money import calculate_line_total


@pytest.mark.parametrize(
    ("price_minor", "quantity", "expected"),
    [(125000, 3, 375000), (1, 1, 1), (0, 5, 0)],
)
def test_piece_total(price_minor: int, quantity: int, expected: int) -> None:
    result = calculate_line_total(ProductUnit.PIECE, price_minor, quantity)
    assert result == expected
    assert type(result) is int


@pytest.mark.parametrize(
    ("price_minor", "grams", "expected"),
    [
        (1, 499, 0),
        (1, 500, 1),
        (1, 501, 1),
        (1, 1499, 1),
        (1, 1500, 2),
        (1, 1501, 2),
        (499, 1, 0),
        (500, 1, 1),
        (501, 1, 1),
        (125000, 333, 41625),
        (129999, 333, 43290),
        (125000, 1000, 125000),
        (125000, 1500, 187500),
        (0, 500, 0),
    ],
)
def test_weight_total_rounds_half_up(price_minor: int, grams: int, expected: int) -> None:
    result = calculate_line_total(ProductUnit.KG, price_minor, grams)
    assert result == expected
    assert type(result) is int


def test_large_integer_prices_remain_exact() -> None:
    price_minor = 2**53 + 1
    assert calculate_line_total(ProductUnit.PIECE, price_minor, 3) == 27021597764222979
    assert calculate_line_total(ProductUnit.KG, price_minor, 1000) == price_minor
    assert calculate_line_total(ProductUnit.KG, price_minor, 500) == 4503599627370497


def test_repeated_scans_must_recalculate_the_combined_quantity() -> None:
    combined = calculate_line_total(ProductUnit.KG, 1, 500 + 500)
    separate = calculate_line_total(ProductUnit.KG, 1, 500) * 2
    assert combined == 1
    assert separate == 2


@pytest.mark.parametrize("unit", list(ProductUnit))
@pytest.mark.parametrize("price_minor", [-1, True, False, 100.0, "100", Decimal("100"), None])
def test_invalid_prices_are_rejected(unit: ProductUnit, price_minor: object) -> None:
    with pytest.raises(ValueError, match="price_minor"):
        calculate_line_total(unit, price_minor, 1)


@pytest.mark.parametrize("unit", list(ProductUnit))
@pytest.mark.parametrize("quantity", [0, -1, True, False, 1.0, "1", Decimal("1"), None])
def test_invalid_quantities_are_rejected(unit: ProductUnit, quantity: object) -> None:
    with pytest.raises(ValueError, match="quantity"):
        calculate_line_total(unit, 100, quantity)


@pytest.mark.parametrize("unit", ["PIECE", "KG", "LITRE", "", None, 1])
def test_units_require_an_explicit_enum(unit: object) -> None:
    with pytest.raises(ValueError, match="unit"):
        calculate_line_total(unit, 100, 1)


def test_unit_values_are_stable_for_storage() -> None:
    assert str(ProductUnit.PIECE) == "PIECE"
    assert str(ProductUnit.KG) == "KG"
    with pytest.raises(ValueError):
        ProductUnit("LITRE")
