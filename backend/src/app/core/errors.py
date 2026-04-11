"""Application error hierarchy and the single-source-of-truth error code registry.

This module owns **CR-001** (error code uniqueness). Every error code raised anywhere
in the backend MUST appear as a key in :data:`ERROR_REGISTRY`. Each entry maps the
code to ``(http_status, default_message_template)``.

Forward dependency note
-----------------------
:class:`BatchValidationError` is populated from ``RowError`` instances that live
in ``app.domain._shared.row_validation`` (introduced in Batch 3). To avoid a
circular import during Batch 0, this module does **not** import ``RowError``. The
subclass accepts ``errors: list[dict] | list`` and stores the pre-converted
dicts in :attr:`AppError.details`. Callers are responsible for producing the
list-of-dicts form via ``[e.to_dict() for e in result.errors]`` before
instantiation. A light duck-typed fallback (``getattr(e, "to_dict")``) is applied
at construction to ease the upgrade path once Batch 3 lands.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AppError",
    "BatchValidationError",
    "NotFoundError",
    "ConflictError",
    "ForbiddenError",
    "UnauthenticatedError",
    "InfraError",
    "ERROR_REGISTRY",
]


# ---------------------------------------------------------------------------
# Error code registry (CR-001 — single source of truth)
# ---------------------------------------------------------------------------
#
# Every code raised anywhere in the backend MUST appear here. The registry maps
# ``code -> (http_status, default_message_template)``. Architecture §3 defines
# the canonical table; two infra-owned codes (``CSV_001``, ``TABULAR_001``) are
# added here per Batch 0 task scope so that :mod:`app.infra.csv_io` and
# :mod:`app.infra.tabular` can surface decoder/dispatch failures without
# overloading ``SYS_002``.
ERROR_REGISTRY: dict[str, tuple[int, str]] = {
    # --- SSO / authentication (FR-021) ------------------------------------
    "AUTH_001": (503, "Identity provider unreachable"),
    "AUTH_002": (400, "SSO callback signature or state mismatch"),
    "AUTH_003": (403, "No role mapping found for this SSO account"),
    "AUTH_004": (401, "Session or refresh token expired"),
    # --- RBAC (FR-022) ----------------------------------------------------
    "RBAC_001": (403, "Insufficient role for this action"),
    "RBAC_002": (403, "Resource is outside your permitted scope"),
    # --- Cycles (FR-001..FR-006) -----------------------------------------
    "CYCLE_001": (409, "A non-closed cycle already exists for this fiscal year"),
    "CYCLE_002": (409, "One or more filing units are missing a manager"),
    "CYCLE_003": (409, "Cycle can only be opened from Draft state"),
    "CYCLE_004": (409, "Write operations are not permitted on a Closed cycle"),
    "CYCLE_005": (409, "Reopen window has expired"),
    # --- Accounts (FR-007, FR-008) ---------------------------------------
    "ACCOUNT_001": (404, "Account code not found"),
    "ACCOUNT_002": (400, "Actuals import failed: one or more rows are invalid"),
    # --- Templates (FR-009, FR-010) --------------------------------------
    "TPL_001": (500, "Template generation failed"),
    "TPL_002": (404, "Template has not been generated for this org unit"),
    # --- Budget uploads (FR-011, FR-012) ---------------------------------
    "UPLOAD_001": (413, "File size exceeds 10 MB limit"),
    "UPLOAD_002": (400, "Row count exceeds 5000 row limit"),
    "UPLOAD_003": (400, "Department code does not match the assigned org unit"),
    "UPLOAD_004": (400, "Required cell is empty"),
    "UPLOAD_005": (400, "Amount format is invalid"),
    "UPLOAD_006": (400, "Amount must be zero or positive"),
    "UPLOAD_007": (400, "Budget upload validation failed"),
    "UPLOAD_008": (404, "Upload record not found"),
    # --- Personnel (FR-024..FR-026) --------------------------------------
    "PERS_001": (400, "Department ID not found in org tree"),
    "PERS_002": (400, "Account code is not in the personnel category"),
    "PERS_003": (400, "Personnel budget amount must be positive"),
    "PERS_004": (400, "Personnel import validation failed"),
    # --- Shared cost (FR-027..FR-029) ------------------------------------
    "SHARED_001": (400, "Department ID not found in org tree"),
    "SHARED_002": (400, "Account code is not in the shared_cost category"),
    "SHARED_003": (400, "Shared cost amount must be positive"),
    "SHARED_004": (400, "Shared cost import validation failed"),
    # --- Reports (FR-014..FR-017) ----------------------------------------
    "REPORT_001": (404, "No data found for cycle and scope"),
    "REPORT_002": (410, "Export job failed"),
    # --- Notifications (FR-013, FR-018, FR-020) --------------------------
    "NOTIFY_001": (502, "SMTP relay unreachable"),
    "NOTIFY_002": (500, "Failed to persist resubmit request record"),
    "NOTIFY_003": (404, "Notification record not found"),
    # --- Audit (FR-023) --------------------------------------------------
    "AUDIT_001": (500, "Audit hash chain verification failed"),
    "AUDIT_002": (400, "Audit filter parameters are invalid"),
    # --- System / infra --------------------------------------------------
    "SYS_001": (500, "Database connection failed"),
    "SYS_002": (500, "Storage system unavailable"),
    "SYS_003": (500, "Unhandled internal error"),
    # --- Batch 0 additions (infra tabular adapters) -----------------------
    "CSV_001": (400, "CSV content could not be decoded as UTF-8"),
    "TABULAR_001": (400, "Unsupported tabular file format"),
}


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class AppError(Exception):
    """Base application exception carrying a registered error code.

    The HTTP status is always resolved from :data:`ERROR_REGISTRY` so that every
    code has exactly one canonical status. Subclasses are informational groupings
    — they do not override the status, they only document the expected category
    of code a caller should instantiate them with.

    Args:
        code: A key of :data:`ERROR_REGISTRY` (e.g. ``"UPLOAD_007"``).
        message: Human-readable message (may include dynamic context). When
            omitted, the default template from the registry is used.
        http_status: Optional explicit override. Primarily exists for tests and
            the unit-test suite's legacy constructor shape; callers SHOULD NOT
            pass this in production code — the registry is authoritative.
        details: Row-level or field-level error details (serialized into the
            response envelope).

    Raises:
        KeyError: If ``code`` is not present in :data:`ERROR_REGISTRY`.
    """

    code: str
    message: str
    http_status: int
    details: list[dict[str, Any]] | None

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        http_status: int | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        if code not in ERROR_REGISTRY:
            raise KeyError(f"Unknown error code: {code!r}")
        registry_status, default_message = ERROR_REGISTRY[code]
        self.code = code
        self.message = message if message is not None else default_message
        self.http_status = http_status if http_status is not None else registry_status
        self.details = details
        super().__init__(self.message)

    def to_envelope(self) -> dict[str, Any]:
        """Return the JSON error-envelope body (without the outer ``request_id``).

        The global FastAPI exception handler merges ``request_id`` into the top
        level. This method produces only the ``{"error": {...}}`` portion so it
        can be unit-tested without a request context.

        Returns:
            dict[str, Any]: Envelope payload of shape
            ``{"error": {"code", "message", "details"}}``.
        """
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class BatchValidationError(AppError):
    """Raised after collect-then-report validation finds one or more row errors.

    Integrates with the collect-then-report importer pattern (FR-008, FR-011,
    FR-024, FR-027). The persisted transaction is aborted and zero rows are
    committed.

    Args:
        code: Batch-level code, e.g. ``"UPLOAD_007"``, ``"PERS_004"``,
            ``"SHARED_004"``, ``"ACCOUNT_002"``.
        errors: Row-level errors collected during validation. Accepts a list of
            ``RowError``-like objects (anything exposing ``to_dict()``) or a
            plain ``list[dict]``. The constructor normalizes to ``list[dict]``.
        message: Optional override message; the registry default is used by
            default.
    """

    def __init__(
        self,
        code: str,
        *,
        errors: list[Any] | None = None,
        message: str | None = None,
    ) -> None:
        normalized: list[dict[str, Any]] = []
        if errors is not None:
            for item in errors:
                if isinstance(item, dict):
                    normalized.append(dict(item))  # type: ignore[arg-type]
                    continue
                to_dict = getattr(item, "to_dict", None)
                if callable(to_dict):
                    result = to_dict()
                    if not isinstance(result, dict):
                        raise TypeError("BatchValidationError: to_dict() must return a dict")
                    normalized.append(dict(result))  # type: ignore[arg-type]
                    continue
                raise TypeError(  # pragma: no cover — defensive
                    "BatchValidationError.errors entries must be dict or have to_dict()"
                )
        super().__init__(code, message=message, details=normalized)


class NotFoundError(AppError):
    """Resource not found — typically maps to HTTP 404 via the registry."""


class ConflictError(AppError):
    """Conflicting state / duplicate resource — typically HTTP 409."""


class ForbiddenError(AppError):
    """RBAC or role-mapping denial — typically HTTP 403."""


class UnauthenticatedError(AppError):
    """Session expired or invalid — typically HTTP 401."""


class InfraError(AppError):
    """Infrastructure / adapter failure — covers ``SYS_*``, ``AUTH_001``, ``NOTIFY_001``, etc."""
