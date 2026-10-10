"""Check known EAN vectors, exact input preservation, and demo generation bounds."""

from decimal import Decimal

import pytest

from app.core.barcodes import (
    calculate_ean_check_digit,
    generate_internal_ean13,
    validate_ean,
)

KNOWN_EANS = (
    "6291041500213",  # Published GS1 manual-calculation example.
    "4006381333931",
    "5901234123457",
    "73513537",
    "96385074",
    "12345670",  # Weighted sum is 60; the check digit is zero.
    "5012345678900",  # Weighted sum is 90; the check digit is zero.
    "00000017",
    "0036000241457",
)


@pytest.mark.parametrize("barcode", KNOWN_EANS)
def test_known_ean_and_check_digit(barcode: str) -> None:
    assert calculate_ean_check_digit(barcode[:-1]) == barcode[-1]
    assert validate_ean(barcode) == barcode


@pytest.mark.parametrize("barcode", KNOWN_EANS)
def test_every_wrong_check_digit_is_rejected(barcode: str) -> None:
    for check_digit in "0123456789":
        if check_digit != barcode[-1]:
            with pytest.raises(ValueError, match="^EAN check digit is invalid$"):
                validate_ean(barcode[:-1] + check_digit)


@pytest.mark.parametrize("barcode", ["00000000", "0000000000000"])
def test_checksum_validation_does_not_claim_registration(barcode: str) -> None:
    assert validate_ean(barcode) == barcode


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        73513537,
        73513537.0,
        b"73513537",
        ["73513537"],
        "",
        "7351353",
        "735135370",
        "036000241457",
        "04006381333931",
        " 73513537",
        "73513537 ",
        "73513537\n",
        "7351 537",
        "7351353x",
        "+3513537",
        "７３５１３５３７",
        "٧٣٥١٣٥٣٧",
        "²3513537",
    ],
)
def test_ean_rejects_invalid_format_without_normalizing(value: object) -> None:
    with pytest.raises(ValueError, match="^EAN must contain exactly 8 or 13 ASCII digits$"):
        validate_ean(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        7351353,
        b"7351353",
        "",
        "123456",
        "12345678",
        "12345678901",
        "1234567890123",
        " 351353",
        "735135\n",
        "7351x53",
        "７３５１３５３",
        "٧٣٥١٣٥٣",
    ],
)
def test_check_digit_rejects_invalid_body(value: object) -> None:
    with pytest.raises(ValueError, match="^EAN body must contain exactly 7 or 12 ASCII digits$"):
        calculate_ean_check_digit(value)


@pytest.mark.parametrize(
    ("sequence", "barcode"),
    [(1, "2000000000015"), (40, "2000000000404"), (999_999_999, "2009999999997")],
)
def test_internal_generator_known_boundaries(sequence: int, barcode: str) -> None:
    assert generate_internal_ean13(sequence) == barcode


def test_internal_generator_is_stable_and_unique_for_seed_items() -> None:
    barcodes = [generate_internal_ean13(sequence) for sequence in range(1, 41)]
    assert len(set(barcodes)) == 40
    assert barcodes == [generate_internal_ean13(sequence) for sequence in range(1, 41)]
    for barcode in barcodes:
        assert barcode.startswith("200")
        assert len(barcode) == 13
        assert validate_ean(barcode) == barcode


@pytest.mark.parametrize(
    "sequence", [0, -1, 1_000_000_000, True, False, 1.0, "1", None, Decimal(1)]
)
def test_internal_generator_rejects_invalid_sequence(sequence: object) -> None:
    with pytest.raises(
        ValueError, match="^EAN sequence must be an integer between 1 and 999999999$"
    ):
        generate_internal_ean13(sequence)
