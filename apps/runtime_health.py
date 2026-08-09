from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


DEFAULT_HEALTH_ROOT = Path("/tmp/airank-health")
SAFE_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SAFE_COMPONENT_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ProcessHealthError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_filename(filename: str) -> str:
    if not SAFE_FILENAME_RE.fullmatch(filename):
        raise ProcessHealthError("health filename must be a safe basename")
    return filename


def _validate_component(component: str) -> str:
    if not SAFE_COMPONENT_RE.fullmatch(component):
        raise ProcessHealthError("health component is invalid")
    return component


def _health_path(filename: str, root: str | Path) -> Path:
    return Path(root).resolve() / _validate_filename(filename)


def write_process_heartbeat(
    filename: str,
    *,
    component: str,
    identity: str,
    now: datetime | None = None,
    root: str | Path = DEFAULT_HEALTH_ROOT,
) -> Path:
    timestamp = now or _utc_now()
    if timestamp.tzinfo is None:
        raise ProcessHealthError("health timestamp must be timezone-aware")
    normalized_component = _validate_component(component)
    normalized_identity = identity.strip()
    if not normalized_identity or len(normalized_identity) > 128:
        raise ProcessHealthError("health identity must contain 1 to 128 characters")

    path = _health_path(filename, root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "component": normalized_component,
        "identity": normalized_identity,
        "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
    }
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def check_process_heartbeat(
    filename: str,
    *,
    component: str,
    maximum_age_seconds: float,
    now: datetime | None = None,
    root: str | Path = DEFAULT_HEALTH_ROOT,
) -> dict[str, Any]:
    if maximum_age_seconds < 1 or maximum_age_seconds > 3600:
        raise ProcessHealthError("maximum heartbeat age must be between 1 and 3600 seconds")
    expected_component = _validate_component(component)
    path = _health_path(filename, root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProcessHealthError("process heartbeat is missing or invalid") from exc
    if not isinstance(payload, dict) or payload.get("component") != expected_component:
        raise ProcessHealthError("process heartbeat component does not match")
    try:
        timestamp = datetime.fromisoformat(str(payload["timestamp"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ProcessHealthError("process heartbeat timestamp is invalid") from exc
    if timestamp.tzinfo is None:
        raise ProcessHealthError("process heartbeat timestamp is not timezone-aware")
    age = ((now or _utc_now()).astimezone(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
    if age < -5 or age > maximum_age_seconds:
        raise ProcessHealthError("process heartbeat is stale")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="AIRank background process health probe")
    parser.add_argument("command", choices=("check",))
    parser.add_argument("--filename", required=True)
    parser.add_argument("--component", required=True)
    parser.add_argument("--maximum-age-seconds", required=True, type=float)
    args = parser.parse_args()
    try:
        check_process_heartbeat(
            args.filename,
            component=args.component,
            maximum_age_seconds=args.maximum_age_seconds,
        )
    except ProcessHealthError as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}, sort_keys=True))
        return 1
    print(json.dumps({"status": "pass", "component": args.component}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
