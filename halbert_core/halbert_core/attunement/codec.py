# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Engine dataclasses ↔ plain dicts.

``store.py`` speaks dicts so its mechanics are testable with the engine
absent. This is the binding, kept in its own module so the storage code never
imports ``haloysius`` and the conversion is exercised on its own.

Coercion is driven by the engine's own type hints rather than a hand-written
field table: a table would be one more copy of the contract to drift, and this
repo already carries a repo-wide guard test because copies drifted.
"""

from __future__ import annotations

import dataclasses
import enum
import typing
from typing import Any, Dict, Optional, Type, TypeVar

T = TypeVar("T")

_NONE_TYPE = type(None)


def to_dict(obj: Any) -> Any:
    """Recursively convert a frozen engine dataclass to JSON-safe data.

    Enum members are ``str``/``int`` subclasses in this contract, so they
    serialise as their values with no special handling.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_dict(getattr(obj, f.name))
                for f in dataclasses.fields(obj)}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


def _unwrap_optional(hint: Any) -> Any:
    """``Optional[X]`` → ``X``; anything else unchanged."""
    origin = typing.get_origin(hint)
    if origin is typing.Union:
        args = [a for a in typing.get_args(hint) if a is not _NONE_TYPE]
        if len(args) == 1:
            return args[0]
    return hint


def _coerce(value: Any, hint: Any) -> Any:
    if value is None:
        return None

    hint = _unwrap_optional(hint)
    origin = typing.get_origin(hint)

    if origin in (tuple, list):
        args = typing.get_args(hint)
        if not args:
            return tuple(value)
        # Tuple[X, ...] is homogeneous; Tuple[X, Y] is positional.
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_coerce(v, args[0]) for v in value)
        return tuple(_coerce(v, a) for v, a in zip(value, args))

    if isinstance(hint, type):
        if issubclass(hint, enum.Enum):
            return hint(value)
        if dataclasses.is_dataclass(hint):
            return from_dict(hint, value)

    return value


def from_dict(cls: Type[T], data: Optional[Dict[str, Any]]) -> T:
    """Rebuild an engine dataclass, coercing enums and nested records.

    Unknown keys are dropped and missing keys fall back to the dataclass
    default, so a record written by a newer or older build still loads. A
    standing request that fails to load is worse than one that loads
    partially: the failure mode is a withdrawal being forgotten.
    """
    if data is None:
        return cls()  # type: ignore[call-arg]
    hints = typing.get_type_hints(cls)
    kwargs: Dict[str, Any] = {}
    for field in dataclasses.fields(cls):
        if field.name not in data:
            continue
        kwargs[field.name] = _coerce(data[field.name], hints.get(field.name, Any))
    return cls(**kwargs)  # type: ignore[arg-type]
