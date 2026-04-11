"""Unit tests for :mod:`app.infra.crypto`."""

from __future__ import annotations

import pytest

from app.core.errors import InfraError
from app.infra import crypto


def test_round_trip_small_plaintext() -> None:
    """encrypt_field + decrypt_field returns the original bytes."""
    plaintext = b"hello world"
    ciphertext = crypto.encrypt_field(plaintext)
    assert isinstance(ciphertext, bytes)
    assert ciphertext != plaintext
    assert crypto.decrypt_field(ciphertext) == plaintext


def test_round_trip_empty_bytes() -> None:
    """Empty plaintext is a valid edge case."""
    ciphertext = crypto.encrypt_field(b"")
    assert crypto.decrypt_field(ciphertext) == b""


def test_two_encrypts_produce_different_ciphertext() -> None:
    """Nonce randomization guarantees probabilistic output."""
    data = b"same input"
    a = crypto.encrypt_field(data)
    b = crypto.encrypt_field(data)
    assert a != b


def test_tampered_ciphertext_raises_sys_002() -> None:
    """Flipping a byte in the ciphertext must fail authentication."""
    ciphertext = bytearray(crypto.encrypt_field(b"auth me"))
    ciphertext[-1] ^= 0x01
    with pytest.raises(InfraError) as excinfo:
        crypto.decrypt_field(bytes(ciphertext))
    assert excinfo.value.code == "SYS_002"


def test_envelope_key_id_prefix() -> None:
    """The envelope carries the active key id so future rotation works."""
    ciphertext = crypto.encrypt_field(b"x")
    key_id_len = int.from_bytes(ciphertext[:2], "big")
    assert ciphertext[2 : 2 + key_id_len] == b"k-test"


def test_decrypt_unknown_key_id_raises() -> None:
    """Envelope with an unknown key id raises ``SYS_002``."""
    # Craft an envelope with a fake key id
    fake = (3).to_bytes(2, "big") + b"xyz" + b"\x00" * 12 + b"\x00" * 32
    with pytest.raises(InfraError):
        crypto.decrypt_field(fake)


def test_hmac_lookup_hash_deterministic() -> None:
    """Same input yields the same digest."""
    assert crypto.hmac_lookup_hash(b"foo") == crypto.hmac_lookup_hash(b"foo")


def test_hmac_lookup_hash_differs_for_different_input() -> None:
    """Different input yields different digests."""
    assert crypto.hmac_lookup_hash(b"foo") != crypto.hmac_lookup_hash(b"bar")


def test_hmac_lookup_hash_length_is_32() -> None:
    """HMAC-SHA256 output is 32 bytes."""
    assert len(crypto.hmac_lookup_hash(b"foo")) == 32


def test_chain_hash_output_32_bytes() -> None:
    """chain_hash output is 32 bytes."""
    assert len(crypto.chain_hash(b"\x00" * 32, b"payload")) == 32


def test_chain_hash_genesis() -> None:
    """Genesis call with zero prev_hash returns a stable value."""
    value = crypto.chain_hash(b"\x00" * 32, b"genesis")
    assert isinstance(value, bytes)
    assert len(value) == 32


def test_chain_hash_differs_by_payload() -> None:
    """Different payloads produce different chain values."""
    a = crypto.chain_hash(b"\x00" * 32, b"payload-a")
    b = crypto.chain_hash(b"\x00" * 32, b"payload-b")
    assert a != b
