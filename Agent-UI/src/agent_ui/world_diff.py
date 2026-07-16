from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel, ValidationError

from automationbench.schema.world import WorldState


_MISSING = object()
_IDENTITY_FIELDS = (
    ("spreadsheet_id", "worksheet_id", "row_id"),
    ("id",),
    ("uuid",),
    ("ts",),
)


def world_changes(
    initial_world: Any,
    final_world: Any,
) -> list[dict[str, Any]] | None:
    """Return semantic changes while preserving the stored world snapshots."""
    if initial_world is None or final_world is None:
        return None

    before, after = _canonical_worlds(initial_world, final_world)
    changes: list[dict[str, Any]] = []
    _collect_changes(before, after, "world", changes)
    return changes


def _canonical_worlds(initial_world: Any, final_world: Any) -> tuple[Any, Any]:
    if not isinstance(initial_world, dict) or not isinstance(final_world, dict):
        return initial_world, final_world
    try:
        before = WorldState.model_validate(copy.deepcopy(initial_world))
        after = WorldState.model_validate(copy.deepcopy(final_world))
    except ValidationError:
        return initial_world, final_world

    _align_generated_defaults(before, after)
    return before.model_dump(mode="json"), after.model_dump(mode="json")


def _align_generated_defaults(before: Any, after: Any) -> None:
    if isinstance(before, BaseModel) and isinstance(after, type(before)):
        for name, field in type(before).model_fields.items():
            before_value = getattr(before, name)
            after_value = getattr(after, name)
            if (
                name not in before.model_fields_set
                and field.default_factory is not None
                and not isinstance(before_value, (BaseModel, list, dict))
            ):
                setattr(before, name, copy.deepcopy(after_value))
                continue
            _align_generated_defaults(before_value, after_value)
        return
    if isinstance(before, list) and isinstance(after, list):
        matched = _matched_items(before, after)
        pairs = matched if matched is not None else zip(before, after, strict=False)
        for before_item, after_item in pairs:
            _align_generated_defaults(before_item, after_item)
        return
    if isinstance(before, dict) and isinstance(after, dict):
        for key in before.keys() & after.keys():
            _align_generated_defaults(before[key], after[key])


def _collect_changes(
    before: Any,
    after: Any,
    path: str,
    changes: list[dict[str, Any]],
    application: str | None = None,
    record: dict[str, Any] | None = None,
) -> None:
    if before == after:
        return
    if (
        before is _MISSING
        or after is _MISSING
        or before is None
        or after is None
        or not isinstance(before, (dict, list))
        or not isinstance(after, (dict, list))
    ):
        change: dict[str, Any] = {
            "action": (
                "Added"
                if before is _MISSING
                else "Removed"
                if after is _MISSING
                else "Changed"
            ),
            "path": path,
        }
        if before is not _MISSING:
            change["before"] = before
        if after is not _MISSING:
            change["after"] = after
        if application is not None:
            change["application"] = application
        if record is not None:
            change["record"] = record
        changes.append(change)
        return
    if isinstance(before, list) or isinstance(after, list):
        before_items = before if isinstance(before, list) else []
        after_items = after if isinstance(after, list) else []
        before_by_id = _identity_index(before_items)
        after_by_id = _identity_index(after_items)
        if before_by_id is not None and after_by_id is not None:
            identities = list(before_by_id)
            identities.extend(identity for identity in after_by_id if identity not in before_by_id)
            for index, identity in enumerate(identities):
                item_record = record or {
                    "path": f"{path}[{index}]",
                    "collection": path.rsplit(".", 1)[-1],
                    "identity": list(identity[1]),
                }
                _collect_changes(
                    before_by_id.get(identity, _MISSING),
                    after_by_id.get(identity, _MISSING),
                    f"{path}[{index}]",
                    changes,
                    application,
                    item_record,
                )
            return
        for index in range(max(len(before_items), len(after_items))):
            before_item = before_items[index] if index < len(before_items) else _MISSING
            after_item = after_items[index] if index < len(after_items) else _MISSING
            item_record = record
            if item_record is None and (
                isinstance(before_item, dict) or isinstance(after_item, dict)
            ):
                item_record = {
                    "path": f"{path}[{index}]",
                    "collection": path.rsplit(".", 1)[-1],
                    "identity": [index],
                }
            _collect_changes(
                before_item,
                after_item,
                f"{path}[{index}]",
                changes,
                application,
                item_record,
            )
        return
    for key in sorted(before.keys() | after.keys()):
        child_application = key if path == "world" else application
        _collect_changes(
            before.get(key, _MISSING),
            after.get(key, _MISSING),
            f"{path}.{key}",
            changes,
            child_application,
            record,
        )


def _matched_items(before: list[Any], after: list[Any]) -> list[tuple[Any, Any]] | None:
    before_by_id = _identity_index(before)
    after_by_id = _identity_index(after)
    if before_by_id is None or after_by_id is None:
        return None
    return [
        (before_by_id[identity], after_by_id[identity])
        for identity in before_by_id.keys() & after_by_id.keys()
    ]


def _identity_index(items: list[Any]) -> dict[tuple[str, Any], Any] | None:
    if not items:
        return {}
    indexed: dict[tuple[str, Any], Any] = {}
    for item in items:
        identity = _record_identity(item)
        if identity is None or identity in indexed:
            return None
        indexed[identity] = item
    return indexed


def _record_identity(item: Any) -> tuple[str, Any] | None:
    for fields in _IDENTITY_FIELDS:
        if isinstance(item, BaseModel):
            values = tuple(getattr(item, field, None) for field in fields)
        elif isinstance(item, dict):
            values = tuple(item.get(field) for field in fields)
        else:
            return None
        if all(value is not None for value in values):
            return "+".join(fields), values
    return None
