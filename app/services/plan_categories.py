"""Categories are labels on plans, scoped by the existing shop catalog queries."""

from __future__ import annotations


def normalize_plan_category(value: object | None) -> str | None:
    return str(value or "").strip()[:128] or None


def plan_category(plan: object) -> str | None:
    return normalize_plan_category(getattr(plan, "category", None))


def category_groups(plans: list) -> list[tuple[str | None, list]]:
    """Keep catalog order, including uncategorized plans, without new sorting."""
    groups: dict[str | None, list] = {}
    for plan in plans:
        groups.setdefault(plan_category(plan), []).append(plan)
    return list(groups.items())


def category_names(plans: list) -> list[str]:
    return [name for name, _ in category_groups(plans) if name is not None]
