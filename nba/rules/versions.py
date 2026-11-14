"""Saved rule versions from the rule studio.

The catalogue (spec/rules/rules_catalogue.yaml) is version 1 of every rule. When the brand team changes a
parameter in the rule studio and saves it, a new version is recorded in data/rule_versions.json with who-why
notes, and every later run uses the latest version. Nothing in the catalogue file is overwritten.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from nba import spec
from nba.rules.catalogue import by_id


def _path(data_dir: Path | None = None) -> Path:
    return (Path(data_dir) if data_dir else spec.data_dir()) / "rule_versions.json"


def history(data_dir: Path | None = None) -> dict[str, list[dict]]:
    p = _path(data_dir)
    return json.loads(p.read_text()) if p.exists() else {}


def current_overrides(data_dir: Path | None = None) -> dict[str, dict]:
    """{rule_id: parameters} of the latest saved version of each changed rule."""
    return {rid: versions[-1]["parameters"] for rid, versions in history(data_dir).items() if versions}


def paused(data_dir: Path | None = None) -> set[str]:
    """Rules whose latest version is paused."""
    return {rid for rid, v in history(data_dir).items() if v and v[-1].get("paused")}


def save(rule_id: str, parameters: dict, note: str = "", data_dir: Path | None = None, pause: bool = False) -> dict:
    rule = by_id()[rule_id]
    h = history(data_dir)
    versions = h.setdefault(rule_id, [])
    previous = versions[-1]["parameters"] if versions else {}
    parameters = {**rule.parameters, **previous, **parameters}
    rule.with_parameters(**parameters).condition()          # refuses unknown parameters or a broken condition
    record = {"version": len(versions) + 2, "parameters": parameters, "paused": pause, "note": note,
              "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    versions.append(record)
    _path(data_dir).write_text(json.dumps(h, indent=1))
    return record


def reset(data_dir: Path | None = None) -> None:
    _path(data_dir).unlink(missing_ok=True)
