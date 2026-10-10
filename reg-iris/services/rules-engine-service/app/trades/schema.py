"""Trade reporting schema (JSON Schema draft-07). Default = dataset's reporting_schema.json, normalised."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).parent / "reporting_schema.json"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    types: tuple[str, ...]
    required: bool
    enum: tuple[Any, ...] | None = None
    pattern: str | None = None
    fmt: str | None = None
    minimum: float | None = None
    description: str | None = None

    @property
    def nullable(self) -> bool:
        return "null" in self.types

    @property
    def base_type(self) -> str:
        return next((t for t in self.types if t != "null"), "string")


@dataclass(frozen=True)
class ReportingSchema:
    raw: dict[str, Any]
    fields: tuple[FieldSpec, ...]

    @property
    def names(self) -> set[str]:
        return {f.name for f in self.fields}

    @property
    def required(self) -> list[str]:
        return [f.name for f in self.fields if f.required]


def normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """The hackathon file escapes '$' as '$$' ("$$schema", "…$$" in patterns). Undo that."""
    text = json.dumps(raw).replace('"$$schema"', '"$schema"').replace('$$"', '$"')
    return json.loads(text)


def parse_schema(raw: dict[str, Any]) -> ReportingSchema:
    raw = normalise(raw)
    required = set(raw.get("required", []))
    fields = []
    for name, spec in raw.get("properties", {}).items():
        types = spec.get("type", "string")
        fields.append(
            FieldSpec(
                name=name,
                types=tuple(types if isinstance(types, list) else [types]),
                required=name in required,
                enum=tuple(spec["enum"]) if "enum" in spec else None,
                pattern=spec.get("pattern"),
                fmt=spec.get("format"),
                minimum=spec.get("minimum"),
                description=spec.get("description"),
            )
        )
    return ReportingSchema(raw, tuple(fields))


@lru_cache
def load_schema(path: str | None = None) -> ReportingSchema:
    return parse_schema(json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8")))
