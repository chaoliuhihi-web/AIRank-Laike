from datetime import datetime, timedelta, timezone
import json

import pytest

from apps.runtime_health import (
    ProcessHealthError,
    check_process_heartbeat,
    write_process_heartbeat,
)


NOW = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)


def test_process_heartbeat_is_atomic_and_component_scoped(tmp_path) -> None:
    path = write_process_heartbeat(
        "worker.json",
        component="worker",
        identity="worker-a",
        now=NOW,
        root=tmp_path,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "component": "worker",
        "identity": "worker-a",
        "timestamp": "2026-08-09T08:00:00+00:00",
    }
    assert check_process_heartbeat(
        "worker.json",
        component="worker",
        maximum_age_seconds=60,
        now=NOW + timedelta(seconds=59),
        root=tmp_path,
    ) == payload


def test_process_heartbeat_fails_closed_for_stale_or_wrong_component(tmp_path) -> None:
    write_process_heartbeat(
        "scheduler.json",
        component="scheduler",
        identity="scheduler-a",
        now=NOW,
        root=tmp_path,
    )

    with pytest.raises(ProcessHealthError, match="component"):
        check_process_heartbeat(
            "scheduler.json",
            component="worker",
            maximum_age_seconds=60,
            now=NOW,
            root=tmp_path,
        )
    with pytest.raises(ProcessHealthError, match="stale"):
        check_process_heartbeat(
            "scheduler.json",
            component="scheduler",
            maximum_age_seconds=60,
            now=NOW + timedelta(seconds=61),
            root=tmp_path,
        )


@pytest.mark.parametrize("filename", ["../escape.json", "/tmp/escape.json", "nested/escape.json"])
def test_process_heartbeat_rejects_path_escape(tmp_path, filename: str) -> None:
    with pytest.raises(ProcessHealthError, match="filename"):
        write_process_heartbeat(
            filename,
            component="worker",
            identity="worker-a",
            now=NOW,
            root=tmp_path,
        )
