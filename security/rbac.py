from typing import List
from fastapi import Depends, HTTPException, status
from security.auth import get_current_user


class RoleChecker:
    """Enforces Role-Based Access Control (RBAC) on REST endpoints."""

    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role", "guest")
        if user_role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{user_role}' is not authorized to perform this operation. Required: {self.allowed_roles}"
            )
        return current_user


# Role Presets
require_admin_or_operator = RoleChecker(["admin", "operator"])
require_admin_only = RoleChecker(["admin"])

