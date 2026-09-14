"""S2.2 Permission Engine exports."""
from .engine import (
    DEFAULT_CLASSIFICATION_MATRIX,
    PermissionDecision,
    PermissionScope,
    check_permission,
)

__all__ = [
    "DEFAULT_CLASSIFICATION_MATRIX",
    "PermissionDecision",
    "PermissionScope",
    "check_permission",
]
