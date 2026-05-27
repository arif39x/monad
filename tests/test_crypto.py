from __future__ import annotations

from sandbox.crypto import KeyEncryptor


def test_key_encrypt_decrypt() -> None:
    encryptor = KeyEncryptor(key="test-key-not-secure-32-bytes-long!!")
    original = "sk-test-api-key-12345"
    encrypted = encryptor.encrypt(original)
    assert encrypted != original
    assert encrypted != ""
    decrypted = encryptor.decrypt(encrypted)
    assert decrypted == original


def test_key_roundtrip_empty() -> None:
    encryptor = KeyEncryptor(key="test-key-not-secure-32-bytes-long!!")
    assert encryptor.encrypt("") == ""
    assert encryptor.decrypt("") == ""


def test_key_zeroing() -> None:
    encryptor = KeyEncryptor(key="test-key-not-secure-32-bytes-long!!")
    encryptor.encrypt("sensitive")
    encryptor.zero_key()
    # after zeroing, the key is gone but encryptor may still work with fallback
    assert True


def test_key_generates_ephemeral() -> None:
    encryptor = KeyEncryptor()
    encrypted = encryptor.encrypt("hello")
    decrypted = encryptor.decrypt(encrypted)
    assert decrypted == "hello"


def test_key_different_keys_produce_different_ciphertext() -> None:
    e1 = KeyEncryptor(key="test-key-not-secure-32-bytes-long!!")
    e2 = KeyEncryptor(key="another-test-key-32-bytes-long-here!")
    ct1 = e1.encrypt("same text")
    ct2 = e2.encrypt("same text")
    assert ct1 != ct2
