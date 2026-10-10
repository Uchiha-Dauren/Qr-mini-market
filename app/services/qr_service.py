"""Generate a high contrast QR image without storing payment links on disk."""

from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def make_qr_png(data: str) -> bytes:
    if not isinstance(data, str) or not data or len(data) > 2048:
        raise ValueError("QR payload must contain between 1 and 2048 characters")
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    qr.box_size = max(10, (300 + qr.modules_count + 7) // (qr.modules_count + 8))
    image = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
