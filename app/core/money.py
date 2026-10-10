"""Calculate line totals using integer minor units only."""

from app.core.enums import ProductUnit

GRAMS_PER_KILOGRAM = 1000
MAX_SAFE_MINOR = 2**53 - 1


def calculate_line_total(unit: ProductUnit, price_minor: int, quantity: int) -> int:
    """Price pieces or grams, rounding a weight-based line once, half up.

    The price is per piece for PIECE and per kilogram for KG. Quantity is
    positive whole pieces or grams. Zero-priced products are allowed.
    """
    if not isinstance(unit, ProductUnit):
        raise ValueError("unit must be a ProductUnit member")
    if type(price_minor) is not int or price_minor < 0:
        raise ValueError("price_minor must be a nonnegative integer")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("quantity must be a positive integer")

    subtotal = price_minor * quantity
    if unit is ProductUnit.PIECE:
        return subtotal
    return (subtotal + GRAMS_PER_KILOGRAM // 2) // GRAMS_PER_KILOGRAM
