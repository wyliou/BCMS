"""AES-256-GCM field encryption + HMAC-SHA256 lookup and audit-chain primitives.

All symmetric encryption for database columns is performed here — never via
``pgcrypto`` (keys would leak into ``pg_stat_statements``). The ciphertext
envelope is self-describing so that future key rotation is a matter of adding
additional entries to the key store; the active key id is read from
:attr:`Settings.crypto_key_id`.

Envelope layout (bytes)::

    [2 bytes big-endian uint16 key_id_len]
    [key_id_len bytes ASCII key_id]
    [12 bytes random nonce]
    [N bytes AES-GCM ciphertext + 16-byte tag]

All helpers raise :class:`app.core.errors.InfraError` with code ``SYS_002`` on
any cryptographic failure (including tampered ciphertext, missing keys, wrong
key id).
"""

from __future__ import annotations

import hmac
import os
import struct
from hashlib import sha256

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings
from app.core.errors import InfraError

__all__ = [
    "KEY_VERSION",
    "encrypt_field",
    "decrypt_field",
    "hmac_lookup_hash",
    "chain_hash",
]


KEY_VERSION = 1
_NONCE_LEN = 12


def _load_aes_key(key_id: str | None = None) -> tuple[str, bytes]:
    """Return ``(key_id, raw_bytes)`` for the AES key selected by ``key_id``.

    Batch 0 supports only one active key. The envelope stores ``key_id`` so
    that future rotation can load additional keys from configuration without
    breaking existing ciphertexts.

    Args:
        key_id: Optional key identifier; defaults to the active one from
            settings.

    Returns:
        tuple[str, bytes]: Resolved ``(key_id, raw_32_bytes)``.

    Raises:
        InfraError: ``SYS_002`` if the key cannot be decoded or if a
            ``key_id`` other than the active one is requested.
    """
    settings = get_settings()
    active_id = settings.crypto_key_id
    resolved_id = key_id if key_id is not None else active_id
    if resolved_id != active_id:
        raise InfraError("SYS_002", f"Unknown crypto key_id: {resolved_id!r}")
    try:
        raw = bytes.fromhex(settings.crypto_key)
    except ValueError as exc:
        raise InfraError("SYS_002", "BC_CRYPTO_KEY is not hex") from exc
    if len(raw) != 32:
        raise InfraError("SYS_002", f"BC_CRYPTO_KEY must be 32 bytes, got {len(raw)}")
    return resolved_id, raw


def _load_audit_hmac_key() -> bytes:
    """Return the raw bytes for ``BC_AUDIT_HMAC_KEY``.

    Returns:
        bytes: 32+ byte HMAC key.

    Raises:
        InfraError: ``SYS_002`` if the key is missing or not valid hex.
    """
    settings = get_settings()
    try:
        raw = bytes.fromhex(settings.audit_hmac_key)
    except ValueError as exc:
        raise InfraError("SYS_002", "BC_AUDIT_HMAC_KEY is not hex") from exc
    if len(raw) < 32:
        raise InfraError("SYS_002", "BC_AUDIT_HMAC_KEY must be at least 32 bytes")
    return raw


def _load_lookup_hmac_key() -> bytes:
    """Return the raw bytes for the user-lookup HMAC key.

    Falls back to :attr:`Settings.crypto_key` when the dedicated lookup key is
    not configured — Batch 0 scope permits this since downstream consumers
    are exercised only through tests.

    Returns:
        bytes: 32+ byte HMAC key.

    Raises:
        InfraError: ``SYS_002`` if no usable key material is available.
    """
    settings = get_settings()
    value = settings.user_lookup_hmac_key or settings.crypto_key
    try:
        raw = bytes.fromhex(value)
    except ValueError as exc:
        raise InfraError("SYS_002", "BC_USER_LOOKUP_HMAC_KEY is not hex") from exc
    if len(raw) < 32:
        raise InfraError("SYS_002", "BC_USER_LOOKUP_HMAC_KEY must be at least 32 bytes")
    return raw


def encrypt_field(plaintext: bytes, *, key_id: str | None = None) -> bytes:
    """Encrypt ``plaintext`` with AES-256-GCM.

    Each call generates a fresh 12-byte random nonce and produces a
    self-describing envelope so that future rotation can decrypt old
    ciphertexts written under a previous key id.

    Args:
        plaintext: Data to encrypt.
        key_id: Optional key identifier; defaults to the active one.

    Returns:
        bytes: ``[key_id_len:2][key_id][nonce:12][ciphertext+tag]``.

    Raises:
        InfraError: ``SYS_002`` on any cryptographic failure.
    """
    if not isinstance(plaintext, (bytes, bytearray)):
        raise InfraError("SYS_002", "encrypt_field requires bytes plaintext")
    resolved_id, raw_key = _load_aes_key(key_id)
    try:
        aesgcm = AESGCM(raw_key)
        nonce = os.urandom(_NONCE_LEN)
        ct_and_tag = aesgcm.encrypt(nonce, bytes(plaintext), None)
    except (ValueError, TypeError) as exc:  # pragma: no cover — defensive
        raise InfraError("SYS_002", f"AES-GCM encrypt failed: {exc}") from exc
    key_id_bytes = resolved_id.encode("ascii")
    return struct.pack(">H", len(key_id_bytes)) + key_id_bytes + nonce + ct_and_tag


def decrypt_field(ciphertext: bytes) -> bytes:
    """Decrypt an envelope produced by :func:`encrypt_field`.

    Args:
        ciphertext: Envelope bytes.

    Returns:
        bytes: Original plaintext.

    Raises:
        InfraError: ``SYS_002`` if the envelope is malformed, the key id is
            unknown, or the GCM tag fails verification (tampered data).
    """
    if not isinstance(ciphertext, (bytes, bytearray)) or len(ciphertext) < 2:
        raise InfraError("SYS_002", "decrypt_field: envelope too short")
    buf = bytes(ciphertext)
    (key_id_len,) = struct.unpack(">H", buf[:2])
    if len(buf) < 2 + key_id_len + _NONCE_LEN + 16:
        raise InfraError("SYS_002", "decrypt_field: envelope truncated")
    try:
        key_id = buf[2 : 2 + key_id_len].decode("ascii")
    except UnicodeDecodeError as exc:
        raise InfraError("SYS_002", "decrypt_field: invalid key id") from exc
    _, raw_key = _load_aes_key(key_id)
    nonce_start = 2 + key_id_len
    nonce_end = nonce_start + _NONCE_LEN
    nonce = buf[nonce_start:nonce_end]
    ct_and_tag = buf[nonce_end:]
    try:
        aesgcm = AESGCM(raw_key)
        return aesgcm.decrypt(nonce, ct_and_tag, None)
    except InvalidTag as exc:
        raise InfraError("SYS_002", "decrypt_field: authentication tag mismatch") from exc
    except (ValueError, TypeError) as exc:  # pragma: no cover — defensive
        raise InfraError("SYS_002", f"AES-GCM decrypt failed: {exc}") from exc


def hmac_lookup_hash(value: bytes) -> bytes:
    """Compute a deterministic HMAC-SHA256 digest for lookup columns.

    Used for ``users.email_hash`` and ``users.sso_id_hash`` — equality lookups
    against encrypted columns must hash the query value with the same key.

    Args:
        value: Raw bytes to hash.

    Returns:
        bytes: 32-byte HMAC-SHA256 digest.

    Raises:
        InfraError: ``SYS_002`` if the key is not configured.
    """
    if not isinstance(value, (bytes, bytearray)):
        raise InfraError("SYS_002", "hmac_lookup_hash requires bytes input")
    key = _load_lookup_hmac_key()
    return hmac.new(key, bytes(value), sha256).digest()


def chain_hash(prev_hash: bytes, payload: bytes) -> bytes:
    """Compute the next audit-log chain value.

    Defined as ``HMAC-SHA256(BC_AUDIT_HMAC_KEY, prev_hash || payload)``. The
    very first audit row passes ``b"\\x00" * 32`` as ``prev_hash``.

    Args:
        prev_hash: 32-byte hash of the previous audit row.
        payload: Serialized payload for the new audit row.

    Returns:
        bytes: 32-byte HMAC-SHA256 chain value.

    Raises:
        InfraError: ``SYS_002`` if the key is not configured.
    """
    if not isinstance(prev_hash, (bytes, bytearray)) or not isinstance(payload, (bytes, bytearray)):
        raise InfraError("SYS_002", "chain_hash requires bytes arguments")
    key = _load_audit_hmac_key()
    return hmac.new(key, bytes(prev_hash) + bytes(payload), sha256).digest()
