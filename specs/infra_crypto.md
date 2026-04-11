# Spec: infra/crypto

Module: `backend/src/app/infra/crypto/__init__.py` (and internal `_aes.py`, `_hmac.py` if needed for ≤500 lines)
Tests: `backend/tests/unit/infra/test_crypto.py`

## FRs

- FR-021 (HMAC lookup for `users.email_hash`, `users.sso_id_hash`)
- FR-023 (hash chain for audit log integrity — `chain_hash`)
- PRD §7 資料保護 (AES-256-GCM column encryption)

## Exports

```python
def encrypt_field(plaintext: bytes, *, key_id: str | None = None) -> bytes:
    """Encrypt a byte payload using AES-256-GCM and return ciphertext with embedded nonce and tag.

    The output format is: key_id_prefix (4 bytes, big-endian length-prefixed ASCII) ||
    nonce (12 bytes) || ciphertext || tag (16 bytes).
    Actual format: [2-byte key_id length][key_id bytes][12-byte nonce][ciphertext+tag].

    Args:
        plaintext (bytes): Data to encrypt.
        key_id (str | None): Key identifier. If None, uses the active key from settings
            (BC_CRYPTO_KEY_ID). Stored in ciphertext envelope for future rotation.

    Returns:
        bytes: Ciphertext envelope (key_id prefix + nonce + ciphertext + GCM tag).

    Raises:
        InfraError: code='SYS_002' if the key cannot be loaded.
    """

def decrypt_field(ciphertext: bytes) -> bytes:
    """Decrypt a byte payload previously encrypted by encrypt_field.

    Reads key_id from envelope, loads corresponding key, decrypts.

    Args:
        ciphertext (bytes): Envelope produced by encrypt_field.

    Returns:
        bytes: Original plaintext bytes.

    Raises:
        InfraError: code='SYS_002' on decryption failure (wrong key, tampered data).
    """

def hmac_lookup_hash(value: bytes) -> bytes:
    """Compute a deterministic HMAC-SHA256 digest for lookup (email_hash / sso_id_hash).

    Uses BC_USER_LOOKUP_HMAC_KEY. Output is 32 bytes.

    Args:
        value (bytes): Input to hash.

    Returns:
        bytes: 32-byte HMAC-SHA256 digest.

    Raises:
        InfraError: code='SYS_002' if the key is not configured.
    """

def chain_hash(prev_hash: bytes, payload: bytes) -> bytes:
    """Compute the next audit log hash chain value using HMAC-SHA256.

    Uses BC_AUDIT_HMAC_KEY. hash = HMAC-SHA256(key=BC_AUDIT_HMAC_KEY, msg=prev_hash || payload).

    Args:
        prev_hash (bytes): Hash value of the previous audit log row (32 bytes).
            For the first row, pass b'\\x00' * 32.
        payload (bytes): Serialized row payload bytes (produced by AuditService._serialize_for_chain).

    Returns:
        bytes: 32-byte HMAC-SHA256 chain value.

    Raises:
        InfraError: code='SYS_002' if the key is not configured.
    """
```

## Imports

| Module | Symbols |
|---|---|
| `cryptography.hazmat.primitives.ciphers.aead` | `AESGCM` |
| `cryptography.hazmat.primitives.hmac` | `HMAC` |
| `cryptography.hazmat.primitives.hashes` | `SHA256` |
| `cryptography.hazmat.backends` | `default_backend` |
| `os` | `urandom` |
| `struct` | `pack`, `unpack` |
| `app.config` | `get_settings` |
| `app.core.errors` | `InfraError` |

## Side Effects

- Reads `BC_CRYPTO_KEY`, `BC_CRYPTO_KEY_ID`, `BC_AUDIT_HMAC_KEY`, `BC_USER_LOOKUP_HMAC_KEY` from `Settings` on first call.
- No persistent state; keys are read from settings each call (or cached module-level after first decode).

## Key Loading Convention

- `BC_CRYPTO_KEY` is a hex-encoded 32-byte string. Decode via `bytes.fromhex(settings.crypto_key)`.
- `BC_AUDIT_HMAC_KEY` and `BC_USER_LOOKUP_HMAC_KEY` are also hex-encoded. Minimum 32 bytes each.
- Key rotation: `decrypt_field` must support decrypting with an older key if `key_id` in the envelope maps to a previously active key. A `_KEY_STORE: dict[str, bytes]` (keyed by key_id) loaded from settings handles this. For Batch 0, only one active key is supported; rotation is a future concern but the envelope format must be designed for it.

## Ciphertext Envelope Format

```
[2 bytes: big-endian uint16 key_id_len]
[key_id_len bytes: ASCII key_id string]
[12 bytes: random nonce]
[N bytes: AES-GCM ciphertext + 16-byte tag]
```

Total overhead per encrypted field: `2 + len(key_id) + 12 + 16` bytes.

## Gotchas

- **NEVER use `pgcrypto` for symmetric encryption** — keys would leak into `pg_stat_statements`. All AES is done here.
- `AESGCM` from `cryptography` combines ciphertext and tag; the last 16 bytes of `aesgcm.encrypt(nonce, plaintext, None)` are the GCM tag.
- `hmac_lookup_hash` is deterministic (same key + value → same output), which is required for lookup. `encrypt_field` is probabilistic (fresh nonce each call), which is correct for at-rest encryption.
- `chain_hash` uses `prev_hash + payload` as the HMAC message (concatenate the two byte strings before passing to HMAC). This is simpler and safe because the audit service owns the separation of prev_hash and payload.
- The very first audit log row uses `prev_hash = b'\x00' * 32` as the genesis sentinel.

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - All failures raise `InfraError("SYS_002", ...)` which is in the registry.

## Tests

### `encrypt_field` / `decrypt_field`
1. `test_round_trip` — encrypt then decrypt returns original plaintext.
2. `test_different_nonces` — two calls with identical plaintext produce different ciphertext (probabilistic nonce).
3. `test_tampered_ciphertext_raises_infra_error` — flip a byte in the ciphertext; `decrypt_field` raises `InfraError` with code `SYS_002`.
4. `test_key_id_embedded_in_ciphertext` — decoded envelope prefix matches `settings.crypto_key_id`.

### `hmac_lookup_hash`
5. `test_deterministic` — two calls with same input return identical bytes.
6. `test_different_inputs_differ` — different inputs produce different outputs.
7. `test_output_is_32_bytes` — result length is 32.

### `chain_hash`
8. `test_chain_hash_output_32_bytes` — result is 32 bytes.
9. `test_chain_advances` — `chain_hash(prev, p1) != chain_hash(prev, p2)` when `p1 != p2`.
10. `test_genesis_hash` — `chain_hash(b'\\x00' * 32, payload)` returns a stable bytes value (not exception).
