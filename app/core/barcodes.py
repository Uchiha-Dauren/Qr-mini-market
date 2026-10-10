"""Validate EAN syntax and checksums; generate local demo identifiers."""


def calculate_ean_check_digit(body: str) -> str:
    """Calculate GS1 modulo-10 for an EAN-8 or EAN-13 body without its last digit."""
    if (
        not isinstance(body, str)
        or len(body) not in (7, 12)
        or not body.isascii()
        or not body.isdigit()
    ):
        raise ValueError("EAN body must contain exactly 7 or 12 ASCII digits")
    total = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(body[::-1]))
    return str(-total % 10)


def validate_ean(barcode: str) -> str:
    """Return an unchanged valid EAN; this does not verify registration or ownership."""
    if (
        not isinstance(barcode, str)
        or len(barcode) not in (8, 13)
        or not barcode.isascii()
        or not barcode.isdigit()
    ):
        raise ValueError("EAN must contain exactly 8 or 13 ASCII digits")
    if barcode[-1] != calculate_ean_check_digit(barcode[:-1]):
        raise ValueError("EAN check digit is invalid")
    return barcode


def generate_internal_ean13(sequence: int) -> str:
    """Create a deterministic demo EAN-13; callers own sequence uniqueness."""
    if type(sequence) is not int or not 1 <= sequence <= 999_999_999:
        raise ValueError("EAN sequence must be an integer between 1 and 999999999")
    body = f"200{sequence:09d}"
    return body + calculate_ean_check_digit(body)
