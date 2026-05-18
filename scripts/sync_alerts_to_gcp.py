#!/usr/bin/env python3
"""Validate Prometheus alert rules and render GCP Terraform alert policies.

This keeps infra/observability/alerts.rules.yml as the portable source of truth.
The generated Terraform uses Cloud Monitoring PromQL alert conditions so the same
queries can back the OSS Alertmanager path and the GCP path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised only on minimal systems
    raise SystemExit(
        "PyYAML is required to parse Prometheus rule YAML. Install it with "
        "`python3 -m pip install PyYAML` and retry."
    ) from exc


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = REPO_ROOT / "infra" / "observability" / "alerts.rules.yml"
DEFAULT_OUTPUT = REPO_ROOT / "infra" / "terraform" / "alerts_generated.tf"
EXPECTED_ALERTS = {
    "voice_round_trip_p95_slow",
    "chat_response_p95_slow",
    "stt_latency_degradation",
    "backend_error_burst",
    "agent_routing_skew",
    "frontend_audio_watchdog_spike",
    "cloud_run_traffic_zero",
}


class RuleValidationError(ValueError):
    """Raised when alerts.rules.yml cannot safely generate GCP policies."""


def _resource_name(alert_name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]", "_", alert_name).lower()
    if not re.match(r"^[a-z_]", name):
        name = f"alert_{name}"
    return name


def _hcl_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _duration(value: Any, *, default: str = "0s") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not re.match(r"^\d+[smhdwy]$", text):
        raise RuleValidationError(f"Unsupported Prometheus duration: {value!r}")
    return text


def _load_rule_groups(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)
    if not isinstance(parsed, dict):
        raise RuleValidationError("Rule file must be a YAML mapping.")
    groups = parsed.get("groups")
    if not isinstance(groups, list) or not groups:
        raise RuleValidationError("Rule file must define at least one group.")
    return groups


def _collect_alert_rules(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            raise RuleValidationError("Each rule group must be a mapping.")
        group_name = group.get("name")
        rules = group.get("rules")
        if not group_name or not isinstance(rules, list):
            raise RuleValidationError("Each rule group requires name and rules.")
        for rule in rules:
            if not isinstance(rule, dict):
                raise RuleValidationError(
                    f"Rules in group {group_name!r} must be mappings."
                )
            alert = rule.get("alert")
            if not alert:
                continue
            if alert in seen:
                raise RuleValidationError(f"Duplicate alert name: {alert}")
            seen.add(alert)
            rule["_group_name"] = group_name
            alerts.append(rule)
    return alerts


def validate_rules(
    alerts: list[dict[str, Any]], *, require_expected: bool = True
) -> None:
    names = {str(rule.get("alert")) for rule in alerts}
    if require_expected and names != EXPECTED_ALERTS:
        missing = sorted(EXPECTED_ALERTS - names)
        extra = sorted(names - EXPECTED_ALERTS)
        details = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"extra={extra}")
        raise RuleValidationError("Alert set mismatch: " + ", ".join(details))

    for rule in alerts:
        alert = str(rule.get("alert"))
        expr = rule.get("expr")
        labels = rule.get("labels")
        annotations = rule.get("annotations")
        if not isinstance(expr, str) or not expr.strip():
            raise RuleValidationError(f"{alert}: expr is required.")
        if not isinstance(labels, dict) or not labels.get("severity"):
            raise RuleValidationError(f"{alert}: labels.severity is required.")
        if not isinstance(annotations, dict) or not annotations.get("summary"):
            raise RuleValidationError(f"{alert}: annotations.summary is required.")
        _duration(rule.get("for"), default="0s")


def _render_map(values: dict[str, Any], indent: int = 6) -> str:
    prefix = " " * indent
    normalized_keys = {
        key: re.sub(r"[^a-zA-Z0-9_]", "_", str(key)) for key in sorted(values)
    }
    width = max((len(key) for key in normalized_keys.values()), default=0)
    lines = ["{"]
    for key in sorted(values):
        normalized = normalized_keys[key]
        lines.append(
            f"{prefix}{normalized.ljust(width)} = {_hcl_string(str(values[key]))}"
        )
    lines.append(" " * (indent - 2) + "}")
    return "\n".join(lines)


def render_terraform(
    alerts: list[dict[str, Any]], notification_channel_ids: list[str]
) -> str:
    channel_expr = (
        "["
        + ", ".join(_hcl_string(channel_id) for channel_id in notification_channel_ids)
        + "]"
        if notification_channel_ids
        else "var.notification_channel_ids"
    )
    blocks = [
        "# Generated by scripts/sync_alerts_to_gcp.py from infra/observability/alerts.rules.yml.",
        "# Do not edit by hand; edit the Prometheus rule source instead.",
        "",
    ]
    for rule in alerts:
        alert_name = str(rule["alert"])
        resource_name = _resource_name(alert_name)
        labels = {str(k): str(v) for k, v in dict(rule.get("labels", {})).items()}
        annotations = {
            str(k): str(v) for k, v in dict(rule.get("annotations", {})).items()
        }
        documentation = annotations.get("description") or annotations.get(
            "summary", alert_name
        )
        group_name = str(rule.get("_group_name", "engineer-cafe-navigator-wave3"))
        severity = labels.get("severity", "P3")

        blocks.append(f'resource "google_monitoring_alert_policy" "{resource_name}" {{')
        blocks.append(f"  display_name = {_hcl_string('Engineer Cafe ' + alert_name)}")
        blocks.append('  combiner     = "OR"')
        blocks.append("  enabled      = var.alert_enabled")
        blocks.append("")
        blocks.append(f"  notification_channels = {channel_expr}")
        blocks.append("")
        blocks.append("  documentation {")
        blocks.append(f"    content   = {_hcl_string(documentation)}")
        blocks.append('    mime_type = "text/markdown"')
        blocks.append("  }")
        blocks.append("")
        blocks.append("  conditions {")
        blocks.append(f"    display_name = {_hcl_string(alert_name)}")
        blocks.append("")
        blocks.append("    condition_prometheus_query_language {")
        blocks.append(f"      query               = {_hcl_string(str(rule['expr']))}")
        blocks.append(
            f"      duration            = {_hcl_string(_duration(rule.get('for'), default='0s'))}"
        )
        blocks.append('      evaluation_interval = "30s"')
        blocks.append(f"      rule_group          = {_hcl_string(group_name)}")
        blocks.append(f"      alert_rule          = {_hcl_string(alert_name)}")
        blocks.append(f"      labels = {_render_map(labels, indent=8)}")
        blocks.append("    }")
        blocks.append("  }")
        blocks.append("")
        blocks.append("  user_labels = {")
        blocks.append('    managed_by = "terraform"')
        blocks.append('    source     = "prometheus_rules"')
        blocks.append(f"    severity   = {_hcl_string(severity)}")
        blocks.append("  }")
        blocks.append("}")
        blocks.append("")
    return "\n".join(blocks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rules", type=Path, default=DEFAULT_RULES, help="Prometheus rule YAML."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Terraform output path. Use '-' to write to stdout.",
    )
    parser.add_argument(
        "--notification-channel-id",
        action="append",
        default=[],
        help="GCP Monitoring notification channel ID. Repeat for multiple channels.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate rules without writing Terraform.",
    )
    parser.add_argument(
        "--allow-extra-alerts",
        action="store_true",
        help="Skip the Wave 3 exact seven-alert set check.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        groups = _load_rule_groups(args.rules)
        alerts = _collect_alert_rules(groups)
        validate_rules(alerts, require_expected=not args.allow_extra_alerts)
        rendered = render_terraform(alerts, args.notification_channel_id)
    except (OSError, RuleValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.validate_only:
        print(f"Validated {len(alerts)} alert rules from {args.rules}")
        return 0

    if str(args.output) == "-":
        print(rendered)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
