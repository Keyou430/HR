"""FastAPI dependency classes for permission checks.

Provides ``PermissionChecker`` as a class-based alternative to the
``require_permission`` function factory in ``auth.dependencies``.
Both delegate to ``authorization.rbac.user_has_permission`` for the
actual permission decision.

Usage::

    from authorization.checks import PermissionChecker

    @router.get("/admin/users")
    def list_users(
        _user: dict = Depends(PermissionChecker("user:view")),
    ):
        ...

``require_permission`` is the current production pattern; ``PermissionChecker``
is available as a class-based option for codebases that prefer dependency
classes over function factories.  Both are functionally equivalent.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status

from auth.dependencies import get_current_user
from authorization.rbac import user_has_permission


class PermissionChecker:
    """FastAPI dependency that requires a specific permission.

    Instances are callable and meant to be used with ``Depends``::

        PermissionChecker("task:create")

    On success the current user dict is returned so endpoint handlers can
    access user identity without a second ``get_current_user`` call.
    """

    def __init__(self, permission_code: str) -> None:
        self._permission_code = permission_code

    def __call__(
        self,
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if not user_has_permission(current_user, self._permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {self._permission_code}",
            )
        return current_user

    def __repr__(self) -> str:
        return f"PermissionChecker({self._permission_code!r})"
