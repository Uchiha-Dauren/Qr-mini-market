"use strict";

// Decimal-string API fields preserve every minor unit beyond Number.MAX_SAFE_INTEGER.
function formatBankMoney(value) {
  const minor = BigInt(value);
  const negative = minor < 0n;
  const absolute = negative ? -minor : minor;
  const whole = (absolute / 100n).toLocaleString("ru-RU");
  const fraction = String(absolute % 100n).padStart(2, "0");
  return `${negative ? "−" : ""}${whole},${fraction} ₸`;
}
