from __future__ import annotations

import copy
import json
from datetime import datetime
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
_WRITE_ACTIONS = {
    "add",
    "append",
    "apply",
    "archive",
    "cancel",
    "copy",
    "create",
    "delete",
    "invite",
    "move",
    "pause",
    "post",
    "publish",
    "remove",
    "rename",
    "replace",
    "reply",
    "restore",
    "schedule",
    "send",
    "set",
    "share",
    "sign",
    "update",
    "upload",
}


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


def world_change_evidence(session: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Annotate semantic changes only when execution evidence matches exactly."""
    changes = world_changes(
        session.get("initial_world"),
        session.get("final_world"),
    )
    if changes is None:
        return None

    grouped: dict[str, list[dict[str, Any]]] = {}
    for change in changes:
        record_path = change.get("record", {}).get("path", change["path"])
        grouped.setdefault(record_path, []).append(change)

    for record_changes in grouped.values():
        origin = _originating_write(record_changes, session.get("events") or [])
        for change in record_changes:
            change["origin"] = origin
            change["assertions"] = _matching_assertions(
                change,
                session.get("evaluation", {}).get("assertions")
                if isinstance(session.get("evaluation"), dict)
                else None,
                session.get("final_world"),
            )
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
                    "identity_fields": identity[0].split("+"),
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
                    "identity_fields": ["index"],
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


def _originating_write(
    changes: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    record = changes[0].get("record") or {}
    identities = record.get("identity") or []
    application = changes[0].get("application")
    if not identities or not application:
        return None

    results = {
        event.get("correlation_id"): event
        for event in events
        if event.get("kind") == "tool_result"
    }
    candidates: list[dict[str, Any]] = []
    for event in events:
        name = event.get("name") or ""
        if (
            event.get("kind") != "tool_call"
            or not _is_write_tool(name)
            or not name.startswith(f"{application}_")
        ):
            continue
        result = results.get(event.get("correlation_id"))
        if result is None:
            continue
        payloads = [
            _decode_json(event.get("arguments")),
            _decode_json(result.get("result")),
        ]
        if not _result_succeeded(payloads[1]):
            continue
        if not all(_contains_value(payloads, identity) for identity in identities):
            continue
        if not _changed_values_match(changes, payloads, identities, name):
            continue
        candidates.append(
            {
                "correlation_id": event.get("correlation_id"),
                "tool_name": name,
                "sequence": event.get("sequence"),
            }
        )

    return candidates[0] if len(candidates) == 1 else None


def _is_write_tool(name: str) -> bool:
    return bool(set(name.split("_")) & _WRITE_ACTIONS)


def _decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return _decode_json(json.loads(value))
    except (TypeError, ValueError):
        return value


def _result_succeeded(value: Any) -> bool:
    return not (isinstance(value, dict) and value.get("success") is False)


def _contains_value(value: Any, target: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_value(item, target) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_value(item, target) for item in value)
    return _values_equal(value, target)


def _values_equal(value: Any, target: Any) -> bool:
    if value == target:
        return True
    if value is None or target is None:
        return False
    if str(value) == str(target):
        return True
    if isinstance(value, str) and isinstance(target, str):
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ) == datetime.fromisoformat(target.replace("Z", "+00:00"))
        except ValueError:
            pass
    return False


def _meaningful_scalars(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [
            scalar
            for item in value.values()
            for scalar in _meaningful_scalars(item)
        ]
    if isinstance(value, list):
        return [scalar for item in value for scalar in _meaningful_scalars(item)]
    return [] if value in (None, "", [], {}) else [value]


def _changed_values_match(
    changes: list[dict[str, Any]],
    payloads: list[Any],
    identities: list[Any],
    tool_name: str,
) -> bool:
    values: list[Any] = []
    whole_record_change = len(changes) == 1 and (
        changes[0]["path"] == changes[0].get("record", {}).get("path")
    )
    key = "before" if changes[0]["action"] == "Removed" else "after"
    if (
        whole_record_change
        and changes[0]["action"] == "Removed"
        and set(tool_name.split("_")) & {"delete", "remove"}
    ):
        return True
    for change in changes:
        values.extend(_meaningful_scalars(change.get(key)))
    values = [
        value
        for value in values
        if not any(str(value) == str(identity) for identity in identities)
    ]
    if not values:
        return True
    matches = sum(_contains_value(payloads, value) for value in values)
    return matches >= 1 if whole_record_change else matches == len(values)


def _matching_assertions(
    change: dict[str, Any],
    assertions: Any,
    final_world: Any,
) -> list[dict[str, Any]]:
    if not isinstance(assertions, list):
        return []
    matches: list[dict[str, Any]] = []
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict) or not _assertion_matches(
            change, assertion, final_world
        ):
            continue
        params = assertion.get("params") or {}
        explicitly_excluded = (
            params.get("excluded") is True or params.get("scored") is False
        )
        status = (
            "excluded"
            if assertion.get("excluded")
            else "passed"
            if assertion.get("passed")
            else "failed"
        )
        label = (
            "Excluded"
            if status == "excluded" and explicitly_excluded
            else "Pre-satisfied · excluded"
            if status == "excluded"
            else status.title()
        )
        matches.append(
            {
                "index": index,
                "type": assertion.get("type", "Assertion"),
                "status": status,
                "status_label": label,
            }
        )
    return matches


def _assertion_matches(
    change: dict[str, Any],
    assertion: dict[str, Any],
    final_world: Any,
) -> bool:
    assertion_type = assertion.get("type") or ""
    application = change.get("application") or ""
    if not assertion_type.startswith(f"{application}_"):
        return False

    params = assertion.get("params") or {}
    record = change.get("record") or {}
    identities = record.get("identity") or []
    identity_params = [
        value
        for key, value in params.items()
        if key == "id" or key.endswith("_id")
    ]
    if identity_params and not all(
        any(str(value) == str(identity) for identity in identities)
        for value in identity_params
    ):
        return False

    collection = params.get("collection")
    if collection and str(collection).rstrip("s") != str(
        record.get("collection", "")
    ).rstrip("s"):
        return False

    channel_name = params.get("channel_name")
    if channel_name and not _channel_matches(change, channel_name, final_world):
        return False

    if "_not_exists" in assertion_type and change.get("action") != "Removed":
        return False
    if (
        "_exists" in assertion_type
        and "_not_exists" not in assertion_type
        and change.get("action") == "Removed"
    ):
        return False

    changed_field = change["path"].split(".")[-1]
    target_field = params.get("field")
    if target_field:
        if change["path"] != record.get("path") and target_field != changed_field:
            return False
        target_value = (
            change.get("after", {}).get(target_field)
            if isinstance(change.get("after"), dict)
            else change.get("after")
        )
        expected = params.get("value")
        if assertion_type.endswith("_equals"):
            return _values_equal(target_value, expected)
        if assertion_type.endswith("_not_contains"):
            return isinstance(target_value, str) and str(expected) not in target_value
        if assertion_type.endswith("_contains"):
            return isinstance(target_value, str) and str(expected) in target_value
        return False

    text_contains = params.get("text_contains")
    if text_contains is not None:
        record_value = (
            change.get("before")
            if change.get("action") == "Removed"
            else change.get("after")
        )
        return any(
            isinstance(value, str) and str(text_contains) in value
            for value in _meaningful_scalars(record_value)
        )

    if "_not_exists" in assertion_type:
        return change.get("action") == "Removed" and bool(identity_params)
    if "_exists" in assertion_type:
        if change.get("action") == "Removed":
            return False
        if text_contains is not None:
            return True
        return bool(identity_params)
    return False


def _channel_matches(change: dict[str, Any], channel_name: Any, final_world: Any) -> bool:
    record_value = (
        change.get("before")
        if change.get("action") == "Removed"
        else change.get("after")
    )
    if not isinstance(record_value, dict):
        return False
    channel_id = record_value.get("channel_id", record_value.get("channel"))
    if channel_id is None:
        return False
    if str(channel_id) == str(channel_name):
        return True
    if not isinstance(final_world, dict):
        return False
    channels = final_world.get("slack", {}).get("channels", [])
    return any(
        isinstance(channel, dict)
        and str(channel.get("name")) == str(channel_name)
        and str(channel.get("id")) == str(channel_id)
        for channel in channels
    )
