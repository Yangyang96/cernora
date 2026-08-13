"""Explicit CLI wiring for wheel-bundled public Profiles."""

from cernora.profile import Profile

BUILTIN_PROFILE_SELECTORS = ("builtin:coding-task", "builtin:offline-workflow")


def load_builtin_profile(selector: str) -> Profile:
    """Instantiate one explicitly selected built-in Profile.

    This closed CLI switch is not an SDK registry or discovery mechanism.
    """

    if selector == "builtin:offline-workflow":
        from cernora.profiles.offline_workflow import OfflineWorkflowProfile

        return OfflineWorkflowProfile()
    if selector == "builtin:coding-task":
        from cernora.profiles.coding_task import CodingTaskProfile

        return CodingTaskProfile()
    raise ValueError(f"unknown built-in Profile selector: {selector}")


__all__ = ["BUILTIN_PROFILE_SELECTORS", "load_builtin_profile"]
