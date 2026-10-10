"""In-memory registry of the loaded reporting schema, overlay and rule sets (reloadable)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .engine import Overlay, Rule, RuleSet, load_rule_sets
from .engine.dataset import DatasetError, ReportingSchema, TradeDataset, load_trades

logger = logging.getLogger("rules.registry")


@dataclass
class Registry:
    rules_dir: Path
    trades_dir: Path
    schema_path: Path
    overlay_path: Path
    schema: ReportingSchema | None = None
    overlay: Overlay = field(default_factory=Overlay)
    rule_sets: list[RuleSet] = field(default_factory=list)
    loaded_at: datetime | None = None
    load_errors: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def reload(self) -> None:
        with self._lock:
            errors: list[str] = []
            try:
                self.schema = ReportingSchema.load(self.schema_path)
            except (OSError, ValueError) as exc:
                self.schema = None
                errors.append(f"reporting schema could not be loaded: {exc}")
            try:
                self.overlay = Overlay.load(self.overlay_path)
            except (OSError, ValueError) as exc:
                self.overlay = Overlay()
                errors.append(f"rules overlay could not be loaded: {exc}")
            known = self.schema.field_names if self.schema else set()
            if self.rules_dir.exists():
                self.rule_sets = load_rule_sets(self.rules_dir, known, self.overlay)
            else:
                self.rule_sets = []
                errors.append(f"rules directory {self.rules_dir} not found")
            self.load_errors = errors
            self.loaded_at = datetime.now(UTC)
            logger.info("rules loaded", extra={"rule_sets": len(self.rule_sets), "rules": len(self.all_rules)})

    @property
    def all_rules(self) -> list[Rule]:
        return [r for rs in self.rule_sets for r in rs.rules]

    def rule(self, rule_id: str) -> Rule | None:
        return next((r for r in self.all_rules if r.id.upper() == rule_id.upper()), None)

    @property
    def regulators(self) -> list[str]:
        return sorted({rs.regulator for rs in self.rule_sets})

    def datasets(self) -> list[Path]:
        if not self.trades_dir.exists():
            return []
        return sorted(p for p in self.trades_dir.glob("*.csv") if p.is_file())

    def dataset_path(self, name: str) -> Path:
        for p in self.datasets():
            if p.name == name:
                return p
        raise DatasetError(f"Unknown trade dataset {name!r}; available: {', '.join(p.name for p in self.datasets()) or 'none'}")

    def load_dataset(self, name: str) -> TradeDataset:
        return load_trades(self.dataset_path(name), self.schema)

    @property
    def default_dataset(self) -> str | None:
        names = [p.name for p in self.datasets()]
        if "sample_trades.csv" in names:
            return "sample_trades.csv"
        return names[0] if names else None
