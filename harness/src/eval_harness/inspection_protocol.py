# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Versioned inspection procedures and conservative evidence provenance checks.

A verified reference establishes an actual file and recorded tool activity. It
never establishes the truth of the model's interpretation of that evidence.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .artifacts import file_manifest, manifest_hash, read_json, read_jsonl, sha256_file
from .errors import ArtifactError, ConfigError
from .grading_criteria import criteria_hash
from .inspection_lineage import find_derived_scopes, validate_derivations

METHOD_TOOLS = {
    "content": {"shell"},
    "structure": {"inspect_document", "shell"},
    "visual": {"render_pages", "view_image"},
    "functional": {"shell"},
    "research": {"fetch", "search", "shell"},
    "human": set(),
}
_RULE_KEYS = {"required_methods", "acceptable_inference", "unconfirmed_conditions", "human_review"}
_REF_KEYS = {"path", "sha256", "location", "call_id", "method"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _observation(value: Any) -> bool:
    """Allow finite recorded results, including an explicitly observed empty collection.

    The surrounding check still requires an action and a captured successful
    tool call. Empty collections can mean that a query returned no matches;
    neither they nor nonempty results establish the interpretation's truth.
    """
    if isinstance(value, str):
        return _text(value)
    if not isinstance(value, (list, dict, bool, int, float)):
        return False
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return False
    return True


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _methods(value: Any, *, human: bool = True) -> bool:
    allowed = set(METHOD_TOOLS) if human else set(METHOD_TOOLS) - {"human"}
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item in allowed for item in value)
        and len(value) == len(set(value))
    )


def protocol_hash(value: Mapping[str, Any] | None) -> str | None:
    return criteria_hash(value)


def load_inspection_protocol(value: Any, base: Path, criteria: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Load a detached JSON/YAML protocol bound to the unchanged original rubric."""
    if value is None:
        return None
    if isinstance(value, str):
        path = Path(value).expanduser()
        path = path if path.is_absolute() else base / path
        try:
            value = yaml.safe_load(path.read_bytes())
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"cannot read inspection protocol: {path}: {exc}") from exc
    if not isinstance(value, Mapping) or set(value) != {"schema_version", "version", "criteria_sha256", "tasks"}:
        raise ConfigError("inspection_protocol requires schema_version, version, criteria_sha256 and tasks")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or not _text(value["version"]):
        raise ConfigError("inspection_protocol requires schema_version: 1 and a nonempty version")
    if criteria is None or value["criteria_sha256"] != criteria_hash(criteria):
        raise ConfigError("inspection protocol does not match the unchanged original criteria hash")
    tasks = value["tasks"]
    if not isinstance(tasks, Mapping) or not tasks:
        raise ConfigError("inspection protocol tasks must map task IDs to original criterion IDs")
    for task_id, rules in tasks.items():
        if not _text(task_id) or task_id == "*" or not isinstance(rules, Mapping):
            raise ConfigError("inspection protocol needs explicit task IDs and criterion mappings")
        for criterion_id, rule in rules.items():
            if (
                not _text(criterion_id)
                or not isinstance(rule, Mapping)
                or not _RULE_KEYS.issubset(rule)
                or set(rule) - _RULE_KEYS - {"pending_reason", "machine_alternative"}
            ):
                raise ConfigError(
                    "inspection protocol items accept procedure fields only; original descriptions cannot change"
                )
            if "pending_reason" in rule and not _text(rule["pending_reason"]):
                raise ConfigError(
                    "inspection protocol pending_reason must explain the unresolved route or prerequisite"
                )
            if not _methods(rule["required_methods"]):
                raise ConfigError("inspection protocol required_methods contains an unsupported or repeated method")
            conditions = rule["unconfirmed_conditions"]
            if not isinstance(conditions, list) or not conditions or not all(_text(item) for item in conditions):
                raise ConfigError("inspection protocol unconfirmed_conditions must be a nonempty list of descriptions")
            inference = rule["acceptable_inference"]
            if inference is not None and (
                not isinstance(inference, Mapping)
                or set(inference) != {"required_methods", "description"}
                or not _methods(inference["required_methods"], human=False)
                or not _text(inference["description"])
            ):
                raise ConfigError("acceptable_inference must be null or declare required_methods and description")
            alternative = rule.get("machine_alternative")
            if "machine_alternative" in rule and (
                not isinstance(alternative, Mapping)
                or set(alternative) != {"condition", "required_methods"}
                or not _text(alternative["condition"])
                or not _methods(alternative["required_methods"], human=False)
            ):
                raise ConfigError("machine_alternative requires an original sufficient condition and nonhuman methods")
            human = rule["human_review"]
            if "human" in rule["required_methods"]:
                if (
                    rule["required_methods"] != ["human"]
                    or inference is not None
                    or not isinstance(human, Mapping)
                    or set(human)
                    not in (
                        {"reviewer", "procedure"},
                        {"reviewer", "procedure", "coordination_owner"},
                    )
                    or not _text(human.get("procedure"))
                    or ("coordination_owner" in human and not _text(human["coordination_owner"]))
                    or not (
                        _text(human.get("reviewer"))
                        or (human.get("reviewer") is None and _text(human.get("coordination_owner")))
                    )
                ):
                    raise ConfigError(
                        "human-only criteria require a procedure and named reviewer, or an explicit coordination "
                        "owner with reviewer:null pending assignment, without AI inference"
                    )
            elif human is not None:
                raise ConfigError("human_review is only valid for a human-only criterion")
    try:
        detached: dict[str, Any] = json.loads(json.dumps(value, allow_nan=False))
        return detached
    except (ValueError, TypeError) as exc:
        raise ConfigError("inspection protocol must contain finite JSON-compatible values") from exc


def protocol_for_task(
    protocol: Mapping[str, Any] | None,
    task_id: str,
    task_criteria: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if protocol is None:
        return None
    rules = protocol["tasks"].get(task_id)
    expected = {item["id"] for item in (task_criteria or {}).get("ai", [])}
    if not isinstance(rules, Mapping) or set(rules) != expected:
        raise ConfigError(f"inspection protocol must cover exactly the original AI criteria for task {task_id}")
    return dict(rules)


def protocol_prompt(protocol: Mapping[str, Any], rules: Mapping[str, Any]) -> str:
    return (
        "\nFrozen inspection protocol (the original criterion descriptions remain unchanged):\n"
        + json.dumps(
            {"version": protocol["version"], "protocol_sha256": protocol_hash(protocol), "criteria": rules},
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\nFor every criterion add observation_kind: direct, inference, or unconfirmed, and evidence_refs. "
        "Each reference has exactly path (workspace-relative), sha256 (file bytes), location (specific page, cells, "
        "lines or other locator), call_id (completed capability call), and method. Use actual tool receipts; "
        "do not invent IDs or hashes. Read call_id from the returned tool metadata (render_pages includes a "
        "metadata text block). For inspect_document references, use its original workspace-relative artifact "
        "path and returned sha256. For render_pages on an original, use that original path and source_sha256. "
        "For all shell references, including structure checks, use captured_stdout_path or "
        "captured_stderr_path with stdout_sha256/stderr_sha256; these .harness_evidence/outputs paths are "
        "materialized by the controller after the session. Never quote an ephemeral absolute private-state path. "
        "For newly fetched research bytes use .harness_evidence/research/<sha256>.bin. The tool's visible "
        "scratch/research path is for reading during the session, not a persistent evidence reference. "
        "Use the canonical captured path in shell source_artifacts too. Participant research already staged "
        "under research/ and supplied reference_files/ keep their workspace-relative paths. "
        "Content uses shell; structure uses inspect_document or shell; visual uses render_pages/view_image; "
        "functional uses shell; research uses fetched response bytes or shell comparisons with supplied sources. "
        "A shell record of your visual observations is a procedure log, not a visual-method evidence reference. "
        "For visual evidence_refs cite the actual render_pages or view_image call, not the shell self-report. "
        "For every shell-based method, write one JSON object to the captured stream with schema_version:1, "
        "source_artifacts:[{path,sha256}], and checks:[{action,observation}]. For a derived scratch image or PDF, "
        "also declare derived_artifacts:[{path,sha256,source_paths,location}], using its canonical captured "
        ".harness_evidence/scratch/... path, actual derivative hash, the exact original source_artifacts paths "
        "used for that derivative, and location as a nonempty string describing the timestamp/page/region "
        "(not an object or list). Compute hashes from the visible scratch files, "
        "but record .harness_evidence/scratch/... paths; scratch/... is a session reading path, not a persistent "
        "evidence reference. Record the actual transformation and its observations. Call the inspection tool "
        "with the visible scratch/... path during the session. In the final derivative evidence reference, "
        "for view_image use its captured_path and rendered_sha256; for render_pages use the derivative's "
        "canonical captured scratch path and returned source_sha256. The recorded derivation binds viewed bytes "
        "to originals, without proving transformation truth. A modified copy shows its modified state, not the "
        "original's unchanged layout or values. Source entries may also include "
        "size or bytes as nonnegative integers matching the original file size; no other keys. Each check has "
        "exactly action (nonempty string) and observation (nonempty string, list/object, finite number, or boolean). "
        "A list/object may be empty when the described query actually returned no entries. Missing/null observations, "
        "blank strings and nonfinite numbers are invalid; nested null/empty values may describe cells. Record a "
        "checked absence as, for example, observation:{matches:[],count:0} or observation:[] with the query in action. "
        "An empty result does not establish that the query or interpretation was correct. Record actual commands/checks and "
        "observed results; include each inspected original's workspace-relative path and hash. Empty records "
        "or shell activity alone are insufficient. For research using shell, bind both the inspected submission "
        "and supplied source files under reference_files/ or research/ in source_artifacts. "
        "For pairwise judgments, inspect both anonymous submissions. "
        "A method reference records activity; it does not prove that a criterion is true. Follow the specified "
        "procedure and unconfirmed conditions. Inference is allowed only under its declared procedure. "
        "Before finalizing, match each original criterion ID to its own description and observations; do not "
        "assign evidence by list position. For each item, include evidence_refs covering every required method "
        "for each submission, or every method of its explicitly permitted inference. One reference declares "
        "one method. The same captured shell record may be referenced separately for structure, content or "
        "functional checks only when its actual checks and observations support each method. An inspect_document "
        "call is not a content-method reference; use a captured shell reading record for content. A reference on "
        "another criterion does not supply this item's missing methods. Keep evidence and reason concise, and "
        "return the complete structured judgment; a narrative announcement is not a judgment. "
        "A criterion with pending_reason is unconfirmed until that prerequisite is resolved in a new protocol. "
        "Only an explicitly declared machine_alternative may independently satisfy an original OR branch: "
        "a direct pass with nonempty evidence_refs on that item claims its stated sufficient condition and must "
        "cover its required_methods. State the observed branch in the reason. A failed or unobserved machine "
        "alternative is unconfirmed, not a failure of the unobserved other branch. A separately supplied human "
        "receipt, when present, judges the full original criterion and takes priority. "
        "Human-only criteria require a separately supplied completed human receipt; an AI must leave them "
        "unconfirmed. Insufficient evidence is unconfirmed, not a claim of hallucination. "
        "Keep reported status and rationale faithful to the observations. Use score:null or winner:unjudgeable "
        "when any original criterion is unconfirmed.\n"
    )


def evidence_ref_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "location": {"type": "string", "minLength": 1},
                "call_id": {"type": "string", "minLength": 1},
                "method": {"type": "string", "enum": sorted(set(METHOD_TOOLS) - {"human"})},
            },
            "required": sorted(_REF_KEYS),
            "additionalProperties": False,
        },
    }


def _workspace_file(workspace: Path, raw: Any) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise ArtifactError("evidence path must be workspace-relative")
    relative = Path(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ArtifactError("evidence path must stay inside the workspace")
    current = workspace
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ArtifactError("evidence path contains a symbolic link")
    if not current.is_file() or not current.resolve().is_relative_to(workspace.resolve()):
        raise ArtifactError("evidence file is missing or outside the workspace")
    return current


def _verified_calls(workspace: Path, expected_hash: str | None) -> dict[str, dict[str, Any]]:
    if not _digest(expected_hash):
        raise ArtifactError("controller capability evidence hash is missing")
    root = workspace / ".harness_evidence"
    manifest = read_json(_workspace_file(workspace, ".harness_evidence/manifest.json"))
    entries = [entry for entry in file_manifest(root) if entry["path"] != "manifest.json"]
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("files") != entries
        or manifest_hash(entries) != expected_hash
    ):
        raise ArtifactError("captured capability evidence changed")
    calls: dict[str, dict[str, Any]] = {}
    started: dict[str, Mapping[str, Any]] = {}
    terminal: set[str] = set()
    for event in read_jsonl(root / "events.jsonl"):
        identifier = event.get("call_id")
        if not isinstance(identifier, str) or not identifier or Path(identifier).name != identifier:
            raise ArtifactError("capability journal has an invalid call ID")
        if event.get("event") == "started":
            if identifier in started or identifier in terminal:
                raise ArtifactError("capability journal repeats a call ID")
            started[identifier] = event
        elif event.get("event") == "finished":
            if identifier in terminal:
                raise ArtifactError("capability journal repeats a terminal call")
            terminal.add(identifier)
            begin = started.get(identifier)
            if event.get("status") != "completed" or event.get("failure") is not None:
                continue
            receipt_path = _workspace_file(workspace, f".harness_evidence/receipts/{identifier}.json")
            if sha256_file(receipt_path) != event.get("output_sha256"):
                raise ArtifactError("capability receipt hash does not match its journal")
            receipt = read_json(receipt_path)
            if (
                begin is None
                or not isinstance(receipt, dict)
                or receipt.get("call_id") != identifier
                or receipt.get("failure") is not None
                or receipt.get("tool") != event.get("tool")
                or receipt.get("arguments") != event.get("arguments")
                or begin.get("tool") != event.get("tool")
                or begin.get("arguments") != event.get("arguments")
            ):
                raise ArtifactError("capability receipt does not match its recorded call")
            calls[identifier] = receipt
    return calls


def verify_captured_evidence(workspace: Path, expected_hash: str) -> None:
    """Recheck frozen controller evidence before reusing a completed judgment."""
    _verified_calls(workspace, expected_hash)


def _result_objects(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    result: list[Mapping[str, Any]] = []
    if isinstance(value, list):
        for block in value:
            if isinstance(block, Mapping) and block.get("type") == "text" and isinstance(block.get("text"), str):
                try:
                    parsed = json.loads(block["text"])
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, Mapping):
                    result.append(parsed)
    return result


def _bound_hashes(receipt: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    tool = receipt.get("tool")
    keys = {
        "inspect_document": ("sha256",),
        "render_pages": ("source_sha256", "image_sha256"),
        "view_image": ("source_sha256", "rendered_sha256"),
        "shell": ("stdout_sha256", "stderr_sha256"),
        "fetch": ("sha256",),
        "search": ("sha256",),
    }.get(str(tool), ())
    for item in _result_objects(receipt.get("result")):
        if tool in {"fetch", "search"}:
            status = item.get("status")
            if not isinstance(status, int) or not 200 <= status < 300 or item.get("http_error"):
                continue
        if tool == "shell" and (item.get("status") != "completed" or item.get("returncode") != 0):
            continue
        for key in keys:
            digest = item.get(key)
            if _digest(digest):
                result.add(str(digest))
        if tool in {"fetch", "search"}:
            groups = [item, *(attempt for attempt in item.get("attempts", []) if isinstance(attempt, Mapping))]
            for group in groups:
                if group.get("error"):
                    continue
                for exchange in group.get("exchanges", []):
                    if (
                        isinstance(exchange, Mapping)
                        and exchange.get("body_complete") is True
                        and isinstance(exchange.get("status"), int)
                        and 200 <= exchange["status"] < 300
                        and not exchange.get("error")
                        and _digest(exchange.get("sha256"))
                    ):
                        result.add(exchange["sha256"])
    return result


def _source_scope(workspace: Path, path: Any, digest: Any) -> str | None:
    if not isinstance(path, str) or not _digest(digest):
        return None
    parts = Path(path).parts
    for label in ("submission", "submission_A", "submission_B"):
        if label not in parts:
            continue
        relative = Path(*parts[parts.index(label) :]).as_posix()
        try:
            source = _workspace_file(workspace, relative)
        except ArtifactError:
            return None
        if sha256_file(source) == digest:
            return label
    return None


def _shell_record_scopes(path: Path, workspace: Path, *, method: str) -> set[str]:
    # This validates a recorded procedure and observation structure, not whether
    # a reported perturbation was meaningful or the observation is true.
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ArtifactError("shell inspection record exceeds 2 MiB")
    value = read_json(path)
    if (
        not isinstance(value, Mapping)
        or set(value)
        not in (
            {"schema_version", "source_artifacts", "checks"},
            {"schema_version", "source_artifacts", "checks", "derived_artifacts"},
        )
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
    ):
        raise ArtifactError("shell inspection requires a versioned source/check/observation record")
    sources, checks = value["source_artifacts"], value["checks"]
    if not isinstance(sources, list) or not sources or not isinstance(checks, list) or not checks:
        raise ArtifactError("shell inspection record is missing sources or performed checks")
    scopes = set()
    supplied_source = False
    for source in sources:
        if (
            not isinstance(source, Mapping)
            or not {"path", "sha256"}.issubset(source)
            or set(source) - {"path", "sha256", "size", "bytes"}
        ):
            raise ArtifactError("shell inspection source is invalid")
        original = _workspace_file(workspace, source["path"])
        if not _digest(source["sha256"]) or sha256_file(original) != source["sha256"]:
            raise ArtifactError("shell inspection source hash is stale")
        for key in ("size", "bytes"):
            if key in source and (
                type(source[key]) is not int or source[key] < 0 or source[key] != original.stat().st_size
            ):
                raise ArtifactError("shell inspection source size is invalid or stale")
        source_parts = Path(source["path"]).parts
        supplied_source |= source_parts[0] in {"reference_files", "research"} or source_parts[:2] == (
            ".harness_evidence",
            "research",
        )
        scope = _source_scope(workspace, source["path"], source["sha256"])
        if scope:
            scopes.add(scope)
    if any(
        not isinstance(check, Mapping)
        or set(check) != {"action", "observation"}
        or not _text(check["action"])
        or not _observation(check["observation"])
        for check in checks
    ):
        raise ArtifactError("shell inspection must describe each performed check and its observation")
    validate_derivations(value, workspace)
    if method == "research" and (not supplied_source or not scopes):
        raise ArtifactError("shell research must bind supplied-source and submission hashes")
    return scopes


def _check_ref(reference: Any, workspace: Path, calls: Mapping[str, Mapping[str, Any]]) -> tuple[str, set[str]]:
    if not isinstance(reference, Mapping) or set(reference) != _REF_KEYS or not _text(reference["location"]):
        raise ArtifactError("evidence reference is missing its required fields or location")
    path = _workspace_file(workspace, reference["path"])
    if not _digest(reference["sha256"]) or sha256_file(path) != reference["sha256"]:
        raise ArtifactError("evidence reference file hash is missing or stale")
    method, call_id = reference["method"], reference["call_id"]
    if not isinstance(method, str) or method not in METHOD_TOOLS or not isinstance(call_id, str):
        raise ArtifactError("evidence reference method or call ID is invalid")
    receipt = calls.get(call_id)
    if receipt is None or receipt.get("tool") not in METHOD_TOOLS[method]:
        raise ArtifactError("evidence reference has no completed call of the required method")
    if receipt.get("tool") == "shell":
        captured_paths = {
            item.get(key)
            for item in _result_objects(receipt.get("result"))
            for key in ("captured_stdout_path", "captured_stderr_path")
            if isinstance(item.get(key), str)
        }
        if reference["path"] not in captured_paths:
            raise ArtifactError("shell evidence must reference a captured stream path returned by its call")
    if reference["sha256"] not in _bound_hashes(receipt):
        raise ArtifactError("evidence file hash is not bound to the recorded tool result")
    if receipt.get("tool") == "shell":
        scopes = _shell_record_scopes(path, workspace, method=method)
    else:
        scopes = set()
        direct_scope = _source_scope(workspace, reference["path"], reference["sha256"])
        if direct_scope:
            scopes.add(direct_scope)
        for item in _result_objects(receipt.get("result")):
            scope = _source_scope(
                workspace, item.get("source", item.get("path")), item.get("source_sha256", item.get("sha256"))
            )
            if scope:
                scopes.add(scope)
            elif receipt.get("tool") in {"view_image", "render_pages"} and _digest(item.get("source_sha256")):
                scopes.update(
                    find_derived_scopes(
                        item["source_sha256"],
                        workspace,
                        calls,
                        validate_record=lambda record_path, root: _shell_record_scopes(
                            record_path, root, method="content"
                        ),
                    )
                )
    return method, scopes


def human_handoff(
    protocol: Mapping[str, Any],
    task_id: str,
    criterion: Mapping[str, Any],
    artifact_sha256: str,
) -> dict[str, Any]:
    """Prepare an explicit pending handoff; this is never a completed rating."""
    rule = protocol["tasks"][task_id][criterion["id"]]
    if rule["required_methods"] != ["human"] or not _digest(artifact_sha256):
        raise ConfigError("human handoff requires a human-only criterion and an artifact SHA256")
    return {
        "schema_version": 1,
        "type": "inspection.human",
        "task_id": task_id,
        "criterion_id": criterion["id"],
        "criterion_sha256": criteria_hash(criterion),
        "protocol_sha256": protocol_hash(protocol),
        "artifact_sha256": artifact_sha256,
        **rule["human_review"],
        "status": "pending",
    }


def validate_human_receipt(receipt: Any, handoff: Mapping[str, Any]) -> list[str]:
    """Validate a separately supplied human receipt, without deciding its merits."""
    if not isinstance(receipt, Mapping):
        return ["completed human receipt is missing"]
    errors = []
    if not _text(handoff.get("reviewer")):
        errors.append("human reviewer is unassigned; assign a reviewer in a new frozen protocol before review")
    if type(receipt.get("schema_version")) is not int:
        errors.append("human receipt schema_version must be an integer")
    for key, value in handoff.items():
        if key != "status" and receipt.get(key) != value:
            errors.append(f"human receipt does not match {key}")
    if (
        receipt.get("status") != "completed"
        or not isinstance(receipt.get("decision"), str)
        or receipt.get("decision") not in {"pass", "fail", "unconfirmed"}
    ):
        errors.append("human review is not completed with an explicit decision")
    if receipt.get("handoff_sha256") != criteria_hash(handoff) or not _text(receipt.get("evidence")):
        errors.append("human receipt lacks its handoff hash or review evidence")
    try:
        completed_at = datetime.fromisoformat(receipt.get("completed_at", ""))
        if completed_at.utcoffset() is None:
            raise ValueError("timezone is missing")
    except (TypeError, ValueError):
        errors.append("human receipt requires a completion timestamp with timezone")
    return errors


def apply_inspection_protocol(
    reported: Sequence[Mapping[str, Any]],
    *,
    protocol: Mapping[str, Any],
    task_id: str,
    task_criteria: Mapping[str, Any],
    workspace: Path,
    evidence_sha256: str | None,
    artifact_hashes: Sequence[str],
    human_receipts: Sequence[Mapping[str, Any]] = (),
) -> tuple[dict[str, Any], ...]:
    """Return effective items; insufficient provenance always remains unconfirmed.

    human_receipts is a controller-only API input, never parsed from model output.
    Callers must authenticate the named human independently; hashes bind content,
    not the identity of the person who supplied it.
    """
    rules = protocol_for_task(protocol, task_id, task_criteria)
    assert rules is not None
    try:
        calls = _verified_calls(workspace, evidence_sha256)
        journal_error: str | None = None
    except (ArtifactError, OSError, TypeError, ValueError) as exc:
        calls, journal_error = {}, str(exc)
    by_id = {item.get("id"): item for item in reported}
    effective: list[dict[str, Any]] = []
    for criterion in task_criteria["ai"]:
        identifier = criterion["id"]
        rule = rules[identifier]
        item = dict(
            by_id.get(
                identifier,
                {"id": identifier, "status": "unconfirmed", "reason": "criterion not reported", "evidence": ""},
            )
        )
        issues: list[str] = []
        kind, status = item.get("observation_kind"), item.get("status")
        alternative = rule.get("machine_alternative")
        human_supplied = any(
            receipt.get("task_id") == task_id and receipt.get("criterion_id") == identifier
            for receipt in human_receipts
        )
        references = item.get("evidence_refs")
        if (
            alternative is not None
            and kind == "direct"
            and isinstance(references, list)
            and references
            and not human_supplied
        ):
            # The source-reviewed alternative must suffice for the unchanged
            # original OR predicate. A failed branch cannot refute another one.
            rule = {**rule, "required_methods": alternative["required_methods"], "acceptable_inference": None}
            rule.pop("pending_reason", None)
            item["inspection_branch"] = "machine_alternative"
            if status != "pass":
                issues.append(
                    "machine alternative has not established a positive result for the original OR criterion"
                )
        elif rule.get("pending_reason"):
            issues.append("inspection prerequisite remains pending: " + rule["pending_reason"])
        item["reported_status"] = status
        item["reported_observation_kind"] = kind
        if rule["required_methods"] == ["human"]:
            decisions = []
            for artifact_hash in artifact_hashes:
                handoff = human_handoff(protocol, task_id, criterion, artifact_hash)
                candidates = [
                    receipt
                    for receipt in human_receipts
                    if receipt.get("task_id") == task_id
                    and receipt.get("criterion_id") == identifier
                    and receipt.get("artifact_sha256") == artifact_hash
                ]
                if len(candidates) != 1:
                    issues.append("one separately supplied completed human receipt is required for each artifact")
                    continue
                issues.extend(validate_human_receipt(candidates[0], handoff))
                decisions.append(candidates[0].get("decision"))
            if not artifact_hashes or not decisions:
                issues.append("human review is not completed")
            if not issues:
                # An external human can establish a criterion decision, but not
                # an AI's aggregate quality score. The pipeline supplies no such
                # receipts automatically.
                item["status"] = (
                    "fail" if "fail" in decisions else "unconfirmed" if "unconfirmed" in decisions else "pass"
                )
                item["observation_kind"] = "direct"
                status = item["status"]
        else:
            if not _text(item.get("evidence")) or not _text(item.get("reason")):
                issues.append("the reported inspection lacks descriptive evidence or rationale")
            methods = rule["required_methods"]
            if kind == "inference":
                if rule["acceptable_inference"] is None:
                    issues.append("this criterion does not permit inference")
                else:
                    methods = rule["acceptable_inference"]["required_methods"]
            elif kind != "direct":
                issues.append("no direct observation or permitted inference was reported")
            if journal_error:
                issues.append(journal_error)
            references = item.get("evidence_refs")
            observed: set[str] = set()
            covered: dict[str, set[str]] = {}
            if not isinstance(references, list) or not references:
                issues.append("evidence references are missing")
            else:
                for reference in references:
                    try:
                        method, scopes = _check_ref(reference, workspace, calls)
                        observed.add(method)
                        for scope in scopes:
                            covered.setdefault(scope, set()).add(method)
                    except (ArtifactError, OSError, TypeError, ValueError) as exc:
                        issues.append(str(exc))
            if not set(methods).issubset(observed):
                issues.append("recorded evidence does not cover the required inspection methods")
            for scope in ("submission", "submission_A", "submission_B"):
                if (workspace / scope).is_dir() and (
                    not covered.get(scope) or not (set(methods) - {"research"}).issubset(covered.get(scope, set()))
                ):
                    issues.append(f"required artifact inspection is missing for {scope}")
        if not isinstance(status, str) or status not in {"pass", "fail"}:
            issues.append("reported criterion is unconfirmed or invalid")
        if issues:
            item.update(status="unconfirmed", observation_kind="unconfirmed")
        item["evidence_validation"] = {
            "status": "unconfirmed" if issues else "referenced",
            "issues": issues,
            "scope": "provenance and method coverage only; not semantic verification",
        }
        effective.append(item)
    return tuple(effective)
