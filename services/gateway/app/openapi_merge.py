"""Merge the services' OpenAPI documents into one public specification."""

from __future__ import annotations

import copy
import json
from typing import Any

PUBLIC_PREFIX = "/api/"


def _rename_refs(spec: dict[str, Any], renames: dict[str, str]) -> dict[str, Any]:
    if not renames:
        return spec
    text = json.dumps(spec)
    for old, new in renames.items():
        text = text.replace(f'"#/components/schemas/{old}"', f'"#/components/schemas/{new}"')
    return json.loads(text)


def merge_specs(base: dict[str, Any], services: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Merge public (/api/*) paths and schemas; same-named but different schemas are prefixed."""
    merged = copy.deepcopy(base)
    merged.setdefault("paths", {})
    schemas: dict[str, Any] = merged.setdefault("components", {}).setdefault("schemas", {})
    tags: list[dict[str, Any]] = list(merged.get("tags", []))
    seen_tags = {t["name"] for t in tags}

    for service, spec in services.items():
        service_schemas = (spec.get("components") or {}).get("schemas") or {}
        renames: dict[str, str] = {}
        for name, schema in service_schemas.items():
            if name in schemas and schemas[name] != schema:
                renames[name] = f"{service.capitalize()}{name}"
        spec = _rename_refs(spec, renames)
        for name, schema in ((spec.get("components") or {}).get("schemas") or {}).items():
            schemas.setdefault(name, schema)
        for path, item in (spec.get("paths") or {}).items():
            if not path.startswith(PUBLIC_PREFIX):
                continue
            merged["paths"][path] = item
            for op in item.values():
                if isinstance(op, dict):
                    op.setdefault("x-service", service)
                    for tag in op.get("tags", []):
                        if tag not in seen_tags:
                            tags.append({"name": tag, "description": f"Served by the {service} service"})
                            seen_tags.add(tag)
    merged["tags"] = tags
    merged["paths"] = dict(sorted(merged["paths"].items()))
    return merged
