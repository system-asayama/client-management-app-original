from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


STAGE_THRESHOLDS = {
    "canary": {
        "max_http_5xx_rate": 0.5,
        "max_auth_error_rate": 2.0,
        "max_finalize_failure_rate": 1.0,
        "max_audit_verify_failure_count": 0,
    },
    "limited": {
        "max_http_5xx_rate": 0.3,
        "max_auth_error_rate": 1.0,
        "max_finalize_failure_rate": 0.5,
        "max_audit_verify_failure_count": 0,
    },
    "full": {
        "max_http_5xx_rate": 0.2,
        "max_auth_error_rate": 0.8,
        "max_finalize_failure_rate": 0.3,
        "max_audit_verify_failure_count": 0,
    },
}


def fetch_json(url: str, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def main() -> int:
    if "--self-check" in sys.argv:
        return _self_check()

    stage = _get_cli_arg("--stage", default=os.environ.get("ROLLOUT_STAGE", "canary")).lower()
    if stage not in STAGE_THRESHOLDS:
        print(f"[FAIL] unknown stage: {stage}. use canary|limited|full")
        return 2

    allow_missing_rates = "--allow-missing-rates" in sys.argv

    base = os.environ.get("E_CONTRACT_SERVICE_URL", "http://localhost:5001").rstrip("/")
    health_url = f"{base}/healthz"
    metrics_url = f"{base}/metrics"

    try:
        health = fetch_json(health_url)
        metrics = fetch_json(metrics_url)
    except urllib.error.URLError as exc:
        print(f"[FAIL] service unreachable: {exc}")
        return 2
    except Exception as exc:
        print(f"[FAIL] invalid response: {exc}")
        return 2

    if health.get("ok") is not True:
        print("[FAIL] healthz is not ok")
        return 1

    required = {
        "uptime_seconds",
        "contracts_total",
        "contracts_completed",
        "signers_total",
        "signers_signed",
        "audit_logs_total",
    }
    missing = sorted(required - set(metrics.keys()))
    if missing:
        print(f"[FAIL] metrics missing keys: {', '.join(missing)}")
        return 1

    external = _load_external_rates()
    threshold_errors = _check_stage_thresholds(stage, external, allow_missing_rates)
    if threshold_errors:
        print("[FAIL] stage threshold check failed")
        for e in threshold_errors:
            print(f"- {e}")
        print(json.dumps({"stage": stage, "health": health, "metrics": metrics, "external": external}, ensure_ascii=False))
        return 1

    print(f"[PASS] release gate check ({stage})")
    print(json.dumps({"stage": stage, "health": health, "metrics": metrics, "external": external}, ensure_ascii=False))
    return 0


def _self_check() -> int:
    # Local self-check without running HTTP server.
    os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    from e_contract_service import create_app

    app = create_app()
    with app.test_client() as client:
        health = client.get("/healthz").get_json()
        metrics = client.get("/metrics").get_json()

    required = {
        "uptime_seconds",
        "contracts_total",
        "contracts_completed",
        "signers_total",
        "signers_signed",
        "audit_logs_total",
    }
    missing = sorted(required - set(metrics.keys()))
    if health.get("ok") is not True or missing:
        print("[FAIL] self-check failed")
        if missing:
            print("missing metrics:", ", ".join(missing))
        return 1

    print("[PASS] self-check")
    print(json.dumps({"health": health, "metrics": metrics}, ensure_ascii=False))
    return 0


def _get_cli_arg(name: str, default: str = "") -> str:
    try:
        idx = sys.argv.index(name)
        return sys.argv[idx + 1]
    except (ValueError, IndexError):
        return default


def _load_external_rates() -> dict:
    # values should be provided by observability pipeline in production
    return {
        "http_5xx_rate": _float_or_none(os.environ.get("HTTP_5XX_RATE")),
        "auth_error_rate": _float_or_none(os.environ.get("AUTH_ERROR_RATE")),
        "finalize_failure_rate": _float_or_none(os.environ.get("FINALIZE_FAILURE_RATE")),
        "audit_verify_failure_count": _int_or_none(os.environ.get("AUDIT_VERIFY_FAILURE_COUNT")),
    }


def _float_or_none(value: str | None):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int_or_none(value: str | None):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _check_stage_thresholds(stage: str, external: dict, allow_missing_rates: bool) -> list[str]:
    t = STAGE_THRESHOLDS[stage]
    errors: list[str] = []

    checks = [
        ("http_5xx_rate", t["max_http_5xx_rate"]),
        ("auth_error_rate", t["max_auth_error_rate"]),
        ("finalize_failure_rate", t["max_finalize_failure_rate"]),
    ]
    for key, max_allowed in checks:
        v = external.get(key)
        if v is None:
            if not allow_missing_rates:
                errors.append(f"missing external metric: {key}")
            continue
        if v > max_allowed:
            errors.append(f"{key}={v} exceeds max {max_allowed}")

    av = external.get("audit_verify_failure_count")
    if av is None:
        if not allow_missing_rates:
            errors.append("missing external metric: audit_verify_failure_count")
    elif av > t["max_audit_verify_failure_count"]:
        errors.append(
            f"audit_verify_failure_count={av} exceeds max {t['max_audit_verify_failure_count']}"
        )

    return errors


if __name__ == "__main__":
    sys.exit(main())
