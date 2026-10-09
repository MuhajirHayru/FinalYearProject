"""Encryption helpers for payout bank-account numbers."""

import base64
import hashlib
import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from rest_framework.exceptions import APIException


class BankAccountEncryptionError(APIException):
    status_code = 500
    default_detail = "Bank account details are unavailable."
    default_code = "bank_account_encryption_error"


def normalize_account_number(value):
    normalized = re.sub(r"[\s-]", "", value or "")
    if not normalized.isdigit() or not 6 <= len(normalized) <= 34:
        raise ValueError("Enter an account number containing 6 to 34 digits.")
    return normalized


def _fernet():
    key_material = settings.BANK_ACCOUNT_ENCRYPTION_KEY or settings.SECRET_KEY
    digest = hashlib.sha256(
        f"greenpath-bank-account-v1:{key_material}".encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_account_number(value):
    normalized = normalize_account_number(value)
    try:
        return _fernet().encrypt(normalized.encode("ascii")).decode("ascii"), normalized[-4:]
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError) as exc:
        raise BankAccountEncryptionError() from exc


def decrypt_account_number(ciphertext):
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise BankAccountEncryptionError() from exc
