from __future__ import annotations

import base64
import hashlib
import os

from orchestration.logging import get_logger

logger = get_logger("elyon.sandbox.crypto")

_HAS_CRYPTOGRAPHY = False
try:
    from cryptography.fernet import Fernet

    _HAS_CRYPTOGRAPHY = True
except ImportError:
    Fernet = None


def _derive_fernet_key(key: str | bytes) -> bytes:
    if isinstance(key, str):
        key_bytes = key.encode("utf-8")
    else:
        key_bytes = key
    digest = hashlib.sha256(key_bytes).digest()
    return base64.urlsafe_b64encode(digest)


def _generate_fallback_key() -> bytes:
    return base64.urlsafe_b64encode(os.urandom(32))


class KeyEncryptor:
    def __init__(self, key: str | bytes | None = None) -> None:
        if key is None:
            fernet_key = _generate_fallback_key()
            logger.warning("No encryption key provided; using ephemeral key")
        else:
            fernet_key = _derive_fernet_key(key)

        if _HAS_CRYPTOGRAPHY:
            self._fernet = Fernet(fernet_key)
            self._mode = "fernet"
        else:
            self._key = fernet_key
            self._mode = "fallback"
            logger.warning("cryptography not installed; using fallback XOR encryption")

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        if self._mode == "fernet":
            return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return self._xor_encrypt(plaintext)

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        if self._mode == "fernet":
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        return self._xor_decrypt(ciphertext)

    def _xor_encrypt(self, plaintext: str) -> str:
        data = plaintext.encode("utf-8")
        key = self._key
        encrypted = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
        return base64.urlsafe_b64encode(encrypted).decode("utf-8")

    def _xor_decrypt(self, ciphertext: str) -> str:
        encrypted = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
        key = self._key
        decrypted = bytes(encrypted[i] ^ key[i % len(key)] for i in range(len(encrypted)))
        return decrypted.decode("utf-8")

    def zero_key(self) -> None:
        if hasattr(self, "_key"):
            self._key = b"\x00" * len(self._key)
        if hasattr(self, "_fernet"):
            self._fernet = None
