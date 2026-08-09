from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_worker_and_scheduler_refresh_health_in_their_main_loops() -> None:
    worker = read("apps/worker/airank_worker/main.py")
    scheduler = read("apps/scheduler/airank_scheduler/main.py")

    assert 'write_process_heartbeat("worker.json"' in worker
    assert 'write_process_heartbeat("scheduler.json"' in scheduler


def test_production_compose_checks_background_loop_freshness() -> None:
    compose = read("ops/deployment/compose.production.yml")

    assert "apps.runtime_health" in compose
    assert "worker.json" in compose
    assert "scheduler.json" in compose
    assert "--maximum-age-seconds=600" in compose
    assert "--maximum-age-seconds=120" in compose
