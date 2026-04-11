"""Domain package for notifications and resubmit requests (M8).

Re-exports the public surface: :class:`NotificationTemplate` (CR-003
owner), :class:`NotificationService`, :class:`ResubmitRequestService`,
and the ORM models. Callers import from ``app.domain.notifications``
rather than the individual submodules.
"""

from __future__ import annotations

from app.domain.notifications.models import Notification, ResubmitRequest
from app.domain.notifications.repo import NotificationRepo
from app.domain.notifications.resubmit import ResubmitRequestService
from app.domain.notifications.service import EmailSender, NotificationService
from app.domain.notifications.templates import TEMPLATES_DIR, NotificationTemplate

__all__ = [
    "TEMPLATES_DIR",
    "EmailSender",
    "Notification",
    "NotificationRepo",
    "NotificationService",
    "NotificationTemplate",
    "ResubmitRequest",
    "ResubmitRequestService",
]
