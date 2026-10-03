"""The engine was lifted from a bank agent; nothing of the bank may remain in the application.

Every source file under app/ is scanned for banking vocabulary. The one exception is the module
that *refuses* such requests (identity documents, financing promises): it must name them in order
to recognise them, and it is the only place that may.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

# Detection patterns for refusing callers live here and nowhere else.
ALLOWED = {APP / "domain" / "real_estate" / "sensitive.py"}

BANKING = re.compile(
    r"\b(loans?|emis?|kyc|otp|ifsc|cvv|atm|banks?|banking|sunrise|sunriseconnect|sunb\d*|"
    r"account\s+numbers?|fixed\s+deposits?|savings\s+accounts?|interest\s+rates?|customer\s+care|"
    r"debit\s+cards?|credit\s+cards?|net\s*banking|branch(?:es)?|cooperative|co-operative|"
    r"rbi|ombudsman|cibil|overdraft|passbook|cheque)\b",
    re.IGNORECASE,
)


def test_no_banking_vocabulary_in_the_application():
    offenders = []
    for path in sorted(APP.rglob("*")):
        if path.suffix not in {".py", ".json", ".md", ".txt", ".yaml", ".yml"} or path in ALLOWED:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if (match := BANKING.search(line)):
                offenders.append(f"{path.relative_to(APP.parent)}:{number}: {match.group(0)!r}")
    assert not offenders, "banking vocabulary found:\n" + "\n".join(offenders)


def test_the_scan_itself_catches_banking_words():
    for sample in ("What is the EMI?", "share your OTP", "KYC pending", "Sunrise Cooperative Bank",
                   "your account number", "home loan rate"):
        assert BANKING.search(sample), sample
    for sample in ("2 BHK in Baner", "site visit on Saturday", "possession in 2027"):
        assert not BANKING.search(sample), sample
