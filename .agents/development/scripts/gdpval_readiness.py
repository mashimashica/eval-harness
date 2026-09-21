# SPDX-FileCopyrightText: 2026 NVIDIA Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regenerate the tracked GDPval readiness ledger from frozen data and history."""

import argparse
import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn, cast

from gdpval_current import EVIDENCE_PATH, REVIEW_PATH, apply_review

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_PATH = ROOT / ".agents/development/gdpval-task-readiness.json"
RECEIPT_PATH = ROOT / ".audit/2026-09-21-all-tasks/readiness-generator.json"
HISTORY_PATH = ROOT / ".agents/development/evidence/gdpval-content-triage-2026-09-16.json"
HISTORY_RELATIVE_PATH = ".agents/development/evidence/gdpval-content-triage-2026-09-16.json"
TASK_VERIFICATION_PATH = ROOT / ".agents/development/evidence/gdpval-capabilities-01.json"
TASK_VERIFICATION_RELATIVE_PATH = ".agents/development/evidence/gdpval-capabilities-01.json"
GENERATED_DATE = "2026-09-21"
CURRENT_SECTION_KEYS = {
    "identity",
    "primary_route",
    "required_capabilities",
    "task_specific_checks",
    "environment_support",
    "assessment",
    "evidence_version",
    "acceptance_scope",
}

FIXED_CRITERION_PATHS = {
    88: ".agents/development/evidence/gdpval-acceptance-criteria.json",
    129: ".agents/development/evidence/gdpval-acceptance-criteria.json",
}

COMMON_ENVIRONMENT = {
    "profile": "gdpval-v1",
    "shared_profile_status": "verified",
    "definition_refs": [
        "harness/src/eval_harness/capability_environment.py",
        "harness/src/eval_harness/capability_service.py",
        "harness/src/eval_harness/capability_network.py",
        "harness/src/eval_harness/capability_sandbox.py",
        "harness/src/eval_harness/capability_inspection.py",
    ],
    "tools": [
        "shell",
        "fetch",
        "search",
        "view_image",
        "install_wheel",
        "inspect_document",
        "render_pages",
    ],
    "status_vocabulary": ["verified", "unverified", "known_unsupported"],
    "role_evidence": {
        "creation": ".audit/native-probe-03-skill_creation/.harness_evidence/runtime.json",
        "application": ".audit/native-probe-03-application/.harness_evidence/runtime.json",
        "evaluation": ".audit/native-probe-03-evaluation/.harness_evidence/runtime.json",
    },
    "client_role_support": {
        "codex": {
            "status": "verified",
            "roles": ["creation", "application", "evaluation"],
        },
        "claude": {
            "status": "verified",
            "roles": ["creation", "application", "evaluation"],
        },
    },
    "evidence_refs": [
        ".audit/acceptance/capability-service-no-model.json",
        ".audit/capability-security-review.json",
        ".audit/acceptance/codex-app-server-capability-probe-rerun-20260915T154445Z/receipt.json",
        ".agents/development/evidence/gdpval-acceptance-criteria.json",
    ],
    "task_acceptance_evidence": {
        "criteria_matrix": ".agents/development/evidence/gdpval-acceptance-criteria.json",
        "dynamic_record": ".agents/development/evidence/gdpval-capabilities-01.json",
        "status": "see_referenced_versioned_acceptance_record",
        "results_copied": False,
    },
    "interpretation": "Verified status describes the shared service and role probes. It does not establish task-specific generation, evaluation, or participant success.",
}

LEDGER_DEFINITIONS = {
    "requirement_inference": "Prompt, rubric, metadata, or a named review record can establish a requirement inference; it cannot establish task acceptance.",
    "task_specific_unverified": "No task-specific generation, evaluation, or participant-success result is copied into this ledger.",
    "metadata_only_unconfirmed": "File, URL, date, and format metadata are recorded without asserting availability, readability, or correctness.",
    "planned_unconfirmed": "The method is a possible future check and was not executed for this ledger.",
    "unknown_scoring": "Unknown is not zero, pass, or failure; retain criteria and withhold a score.",
}

# These line numbers are 1-based so that they can be checked directly against
# the frozen JSONL reviewed by the content triage.  The prefix checks prevent a
# silently shifted source file from receiving another task's classification.
INDIVIDUAL_PREFIXES = {
    1: "83d10b06",
    13: "38889c3b",
    14: "ff85ee58",
    15: "4b894ae3",
    24: "85d95ce5",
    57: "e222075d",
    58: "c94452e4",
    59: "75401f7c",
    60: "a941b6d8",
    61: "8079e27d",
    64: "c7d83f01",
    69: "b78fd844",
    88: "9e39df84",
    105: "be830ca0",
    111: "5e2b6aab",
    113: "3940b7e7",
    115: "5a2d70da",
    121: "f1be6436",
    129: "5d0feb24",
    136: "b5d2e6f1",
    145: "c657103b",
    169: "0818571f",
    170: "6074bba3",
    172: "11593a50",
    173: "94925f49",
    174: "90f37ff3",
    200: "105f8ad0",
    207: "1d4672c8",
    208: "4de6a529",
    212: "a4a9195c",
    216: "0e386e32",
}

PUBLIC_REFERENCE_LINES = {
    4,
    6,
    8,
    11,
    21,
    22,
    23,
    26,
    27,
    28,
    30,
    32,
    35,
    36,
    37,
    38,
    39,
    40,
    46,
    47,
    50,
    51,
    52,
    53,
    54,
    55,
    62,
    63,
    65,
    66,
    76,
    78,
    81,
    82,
    83,
    85,
    91,
    102,
    103,
    106,
    107,
    108,
    109,
    110,
    116,
    117,
    118,
    119,
    124,
    126,
    127,
    128,
    130,
    131,
    132,
    135,
    141,
    142,
    143,
    144,
    152,
    153,
    154,
    156,
    160,
    166,
    171,
    177,
    179,
    181,
    183,
    186,
    187,
    188,
    189,
    193,
    201,
    203,
    206,
    210,
    211,
}

CODE_CALCULATION_SPECIFICATION_LINES = {112, 217, 218, 219, 220}
FIXED_ACCEPTANCE_LINES = {88, 129}

INDIVIDUAL_REASONS = {
    1: ("specification_conflict", "Frozen specification constraints need prospective adjudication."),
    13: ("audio", "Audio authoring and listening-grade evaluation are not established in this increment."),
    14: ("audio", "Audio authoring and listening-grade evaluation are not established in this increment."),
    15: ("audio", "Audio authoring and listening-grade evaluation are not established in this increment."),
    24: ("specification_conflict", "Frozen prompt/rubric conflicts need prospective adjudication."),
    57: ("video", "Video authoring and full temporal review are not established in this increment."),
    58: ("video", "Video authoring and full temporal review are not established in this increment."),
    59: ("video", "Video authoring and full temporal review are not established in this increment."),
    60: ("video", "Video/VFX authoring and full temporal review are not established in this increment."),
    61: ("source_or_data_access", "Task-specific source or data access remains unverified."),
    64: ("interactive_ui", "The interactive notebook/UI runtime is a scoring item and remains unverified."),
    69: ("specification_conflict", "Frozen specification constraints need prospective adjudication."),
    88: ("native_pivots", "Native PivotTable authoring and functional evaluation require the fixed acceptance path."),
    105: ("specification_conflict", "Frozen date-range constraints need prospective adjudication."),
    111: ("native_3d", "Native 3D/CAD authoring and evaluation are outside this increment."),
    113: ("step_input", "STEP input reading is distinct from new CFD/CAD delivery and remains unverified."),
    115: ("step_input", "STEP input reading is distinct from new CFD/CAD delivery and remains unverified."),
    121: ("source_or_data_access", "Task-specific source or data access remains unverified."),
    129: ("native_word", "Native Word revision/comment authoring and evaluation require the fixed acceptance path."),
    136: ("native_pivots", "Native PivotTable authoring and functional evaluation remain unverified."),
    145: ("template_or_calculation", "The task's template/calculation premise remains unverified."),
    169: ("source_or_data_access", "Task-specific source or data access remains unverified."),
    170: ("supplied_file_checks", "Checks against supplied files remain unverified."),
    172: ("specification_conflict", "Frozen specification constraints need prospective adjudication."),
    173: ("source_or_data_access", "Task-specific source or data access remains unverified."),
    174: ("source_or_data_access", "Task-specific source or data access remains unverified."),
    200: ("source_or_data_access", "Task-specific source or data access remains unverified."),
    207: ("source_or_data_access", "Task-specific source or data access remains unverified."),
    208: ("supplied_file_checks", "Checks against supplied files remain unverified."),
    212: ("source_or_data_access", "Task-specific source or data access remains unverified."),
    216: ("multi_chain_scope", "Multi-chain integration and its separate live evaluation path remain unverified."),
}


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def fail(message: str) -> NoReturn:
    raise SystemExit(f"readiness ledger validation failed: {message}")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str | None:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError:
        return None


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot load {label} {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} {path} must contain a JSON object")
    return value


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def short_excerpt(value: object, limit: int = 240) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    clipped = text[: limit - 1].rsplit(" ", 1)[0].rstrip()
    return f"{clipped}…"


def first_prompt_sentence(prompt: str) -> str:
    cleaned = re.sub(r"\s+", " ", prompt).strip()
    if not cleaned:
        return "Prompt text is empty in the frozen row."
    match = re.search(r"(?<=[.!?])\s+", cleaned)
    return short_excerpt(cleaned[: match.end() - 1] if match else cleaned)


def canonical_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def extension_format(path: str) -> str:
    suffix = Path(path).suffix.lower()
    formats = {
        ".pdf": "PDF",
        ".doc": "Office document",
        ".docx": "Office document",
        ".odt": "Office document",
        ".xls": "Office spreadsheet",
        ".xlsx": "Office spreadsheet",
        ".ods": "Office spreadsheet",
        ".ppt": "Office presentation",
        ".pptx": "Office presentation",
        ".odp": "Office presentation",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".webp": "image",
        ".gif": "image",
        ".psd": "layered image",
        ".wav": "audio",
        ".mp3": "audio",
        ".flac": "audio",
        ".mp4": "video",
        ".mov": "video",
        ".avi": "video",
        ".mkv": "video",
        ".step": "STEP/CAD",
        ".stp": "STEP/CAD",
        ".iges": "CAD",
        ".igs": "CAD",
        ".py": "code",
        ".ipynb": "notebook/code",
        ".js": "code",
        ".ts": "code",
        ".tsx": "code",
        ".yaml": "structured text",
        ".yml": "structured text",
        ".json": "structured text",
        ".md": "text",
        ".txt": "text",
        ".zip": "archive",
    }
    return formats.get(suffix, suffix.lstrip(".").upper() or "unknown")


def unique_formats(paths: list[Any]) -> list[str]:
    values: list[str] = []
    for path in paths:
        if not isinstance(path, str):
            continue
        value = extension_format(path)
        if value not in values:
            values.append(value)
    return sorted(values)


def extract_dates(*values: str) -> list[str]:
    pattern = re.compile(
        r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*|\s+)\d{4}|Q[1-4]|20\d{2})\b",
        re.IGNORECASE,
    )
    result: list[str] = []
    for value in values:
        for match in pattern.finditer(value or ""):
            found = match.group(0)
            if found not in result:
                result.append(found)
    return result


def digest_records(records: dict[str, dict[str, Any]]) -> str:
    return sha256_bytes(canonical_json(records))


def record_evidence_pointers(record: dict[str, Any]) -> list[str]:
    pointers: list[str] = []
    for key, value in record.items():
        key_lower = key.lower()
        if "evidence" not in key_lower or "meaning" in key_lower:
            continue
        if isinstance(value, str):
            pointers.append(value)
        elif isinstance(value, list):
            pointers.extend(str(item) for item in value if isinstance(item, str))
    return sorted(set(pointers))


parser = argparse.ArgumentParser(
    description="Regenerate the GDPval readiness ledger from frozen data and tracked history."
)
parser.add_argument("--source", required=True, type=Path, help="Path to the frozen GDPval JSONL source")
parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Current readiness ledger output path")
parser.add_argument("--history", type=Path, default=HISTORY_PATH, help="Tracked historical triage and record path")
parser.add_argument("--receipt", type=Path, default=RECEIPT_PATH, help="Verification receipt path")
arguments = parser.parse_args()
SOURCE_ARGUMENT_PATH = arguments.source.expanduser().resolve()
OUTPUT_PATH = arguments.output.expanduser().resolve()
HISTORY_PATH = arguments.history.expanduser().resolve()
RECEIPT_PATH = arguments.receipt.expanduser().resolve()

history_seed = load_json(HISTORY_PATH, "tracked content-triage history")
source_info_value = history_seed.get("source")
if not isinstance(source_info_value, dict) or not isinstance(source_info_value.get("path"), str):
    fail("tracked content-triage history has no frozen source descriptor")
source_info: dict[str, Any] = cast(dict[str, Any], source_info_value)
review = history_seed.get("review_snapshot", {})
if not isinstance(review, dict):
    fail("tracked content-triage history has no review snapshot")
history_seed_records = history_seed.get("legacy_records")
if not isinstance(history_seed_records, dict):
    fail("tracked content-triage history has no legacy records")
history_seed_hashes = history_seed.get("source_hashes", {})
if not isinstance(history_seed_hashes, dict):
    fail("tracked content-triage history has no source hash descriptor")
REVIEW_ARTIFACT_SHA256 = history_seed_hashes.get("review_artifact_sha256")
reviewed = {
    str(task_id): deepcopy(record)
    for task_id, record in cast(dict[object, object], history_seed_records).items()
    if isinstance(record, dict) and record.get("review_status") == "reviewed_against_original_prompt_and_rubric"
}
source_path = SOURCE_ARGUMENT_PATH
try:
    source_bytes = source_path.read_bytes()
except OSError as exc:
    fail(f"cannot read frozen source {source_path}: {exc}")
source_hash = hashlib.sha256(source_bytes).hexdigest()
if source_hash != source_info["sha256"]:
    fail(f"frozen source hash changed: expected {source_info['sha256']}, got {source_hash}")
try:
    rows = [json.loads(line) for line in source_bytes.decode("utf-8").splitlines()]
except (UnicodeError, json.JSONDecodeError) as exc:
    fail(f"frozen source is not valid JSONL: {exc}")
if len(rows) != source_info["row_count"]:
    fail(f"frozen source row count changed: expected {source_info['row_count']}, got {len(rows)}")

row_ids = [row.get("task_id") for row in rows]
if any(not isinstance(task_id, str) for task_id in row_ids) or len(set(row_ids)) != len(row_ids):
    fail("frozen source task IDs are missing or duplicated")

if TASK_VERIFICATION_PATH.exists():
    task_verification_document = load_json(TASK_VERIFICATION_PATH, "task verification record")
    task_verification_value = task_verification_document.get("task_verification", {})
    if not isinstance(task_verification_value, dict):
        fail("task verification record task_verification must be an object")
    TASK_VERIFICATION = {
        str(task_id): deepcopy(record)
        for task_id, record in cast(dict[object, object], task_verification_value).items()
        if isinstance(record, dict)
    }
else:
    TASK_VERIFICATION = {}
# Hash only the task-keyed map.  The surrounding acceptance record may later
# refer to this ledger, so hashing the whole document would create a cycle.
TASK_VERIFICATION_SHA256 = digest_records(TASK_VERIFICATION)


def check_prefixes(prefixes: dict[int, str], label: str) -> None:
    for line_number, prefix in prefixes.items():
        actual = row_ids[line_number - 1]
        if not actual.startswith(prefix):
            fail(f"{label} line {line_number} expected {prefix}, got {actual}")


check_prefixes(INDIVIDUAL_PREFIXES, "individual")

all_lines = set(range(1, len(rows) + 1))
individual_lines = set(INDIVIDUAL_PREFIXES)
ordinary_lines = all_lines - individual_lines
if len(individual_lines) != 31:
    fail(f"individual classification has {len(individual_lines)} rows, expected 31")
if FIXED_ACCEPTANCE_LINES - individual_lines:
    fail("fixed acceptance rows must be individual rows")
if PUBLIC_REFERENCE_LINES & individual_lines:
    fail("public-reference and individual classifications overlap")
if CODE_CALCULATION_SPECIFICATION_LINES & individual_lines:
    fail("code/calculation/specification and individual classifications overlap")
if PUBLIC_REFERENCE_LINES & CODE_CALCULATION_SPECIFICATION_LINES:
    fail("public-reference and code/calculation/specification classifications overlap")
if len(PUBLIC_REFERENCE_LINES) != 81 or len(CODE_CALCULATION_SPECIFICATION_LINES) != 5:
    fail("content classification counts changed")
supplied_information_lines = ordinary_lines - PUBLIC_REFERENCE_LINES - CODE_CALCULATION_SPECIFICATION_LINES
if len(supplied_information_lines) != 103:
    fail(f"supplied-information classification has {len(supplied_information_lines)} rows, expected 103")
if len(ordinary_lines) != 189:
    fail(f"ordinary-route classification has {len(ordinary_lines)} rows, expected 189")
if len(FIXED_ACCEPTANCE_LINES) != 2 or len(individual_lines - FIXED_ACCEPTANCE_LINES) != 29:
    fail("acceptance-scope classification counts changed")
if set(INDIVIDUAL_REASONS) != individual_lines:
    fail("each individual check must have exactly one content reason")

if len(reviewed) != 26:
    fail(f"tracked history contains {len(reviewed)} reviewed task records, expected 26")
for task_id, task in reviewed.items():
    index = task.get("dataset_index_zero_based")
    if not isinstance(index, int) or not 0 <= index < len(rows) or row_ids[index] != task_id:
        fail(f"review task index does not match frozen source for {task_id}")


def old_content_classification(line_number: int) -> tuple[str, str]:
    if line_number in PUBLIC_REFERENCE_LINES:
        return (
            "public_reference_candidate",
            "Task content calls for participant-selected public references or research; availability and participant retrieval remain unverified.",
        )
    if line_number in CODE_CALCULATION_SPECIFICATION_LINES:
        return (
            "code_calculation_specification_candidate",
            "Task content is primarily code, calculation, or specification work; semantic correctness remains unverified.",
        )
    if line_number in supplied_information_lines:
        return (
            "supplied_information_document_candidate",
            "Task content relies on supplied information or documents; input bytes and task-specific evaluation remain unverified.",
        )
    _, reason = INDIVIDUAL_REASONS[line_number]
    return "individual_check", reason


def build_legacy_entry(row: dict[str, Any], review_task: dict[str, Any] | None, index: int) -> dict[str, Any]:
    line_number = index + 1
    row_hash = sha256_bytes(canonical_json(row))
    if review_task:
        entry = deepcopy(review_task)
        entry["row_sha256"] = row_hash
        entry["disposition"] = entry.pop("suggested_disposition")
        entry["review_status"] = "reviewed_against_original_prompt_and_rubric"
        entry["empirical_acceptance"] = "unconfirmed"
    else:
        entry = {
            "task_id": row["task_id"],
            "dataset_index_zero_based": index,
            "row_sha256": row_hash,
            "disposition": "out_of_scope",
            "review_status": "not_reviewed",
            "empirical_acceptance": "unconfirmed",
            "reason": "Not one of the 26 named cases or two fixed acceptance tasks in this bounded increment. This is not a benchmark exclusion or feasibility claim; task-specific input/execution/evaluation review is still required.",
        }
    if line_number in FIXED_ACCEPTANCE_LINES:
        entry["acceptance_evidence"] = ".agents/development/evidence/gdpval-capabilities-01.json"
        entry["acceptance_evidence_meaning"] = (
            "Per-role capability proof and participant outcomes are recorded separately; full task acceptance remains unconfirmed while required native or human checks are pending."
        )
    content_readiness, content_reason = old_content_classification(line_number)
    entry["content_readiness"] = content_readiness
    entry["content_readiness_reason"] = content_reason
    if line_number in ordinary_lines:
        entry["acceptance_scope"] = "ordinary_route_candidate"
    elif line_number in FIXED_ACCEPTANCE_LINES:
        entry["acceptance_scope"] = "fixed_acceptance"
    else:
        entry["acceptance_scope"] = "individual_check"
    return entry


def task_map(value: object, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        fail(f"{label} must be a task list")
    result: dict[str, dict[str, Any]] = {}
    for task in value:
        if not isinstance(task, dict) or not isinstance(task.get("task_id"), str):
            fail(f"{label} contains an invalid task record")
        task_id = task["task_id"]
        if task_id in result:
            fail(f"{label} contains duplicate task ID {task_id}")
        result[task_id] = deepcopy(task)
    return result


def load_legacy_snapshot() -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if HISTORY_PATH.exists():
        history = load_json(HISTORY_PATH, "content-triage history")
        history_source = history.get("source")
        if not isinstance(history_source, dict) or history_source.get("sha256") != source_info["sha256"]:
            fail("content-triage history is for a different frozen source")
        records = history.get("legacy_records")
        if not isinstance(records, dict):
            fail("content-triage history has no legacy record map")
        records = {
            str(task_id): deepcopy(record)
            for task_id, record in cast(dict[object, object], records).items()
            if isinstance(record, dict)
        }
        legacy_top_level = history.get("legacy_top_level", {})
        if not isinstance(legacy_top_level, dict):
            fail("content-triage history legacy_top_level is not an object")
        snapshot = history.get("legacy_snapshot", {})
        if not isinstance(snapshot, dict):
            fail("content-triage history legacy_snapshot is not an object")
        return records, deepcopy(legacy_top_level), deepcopy(snapshot)

    if OUTPUT_PATH.exists():
        prior = load_json(OUTPUT_PATH, "prior readiness ledger")
        if prior.get("schema_version") != 1:
            fail("a migrated readiness ledger requires its content-triage history file")
        records = task_map(prior.get("tasks"), "prior readiness ledger tasks")
        metadata = {key: deepcopy(value) for key, value in prior.items() if key != "tasks"}
        snapshot = {
            "path": ".agents/development/gdpval-task-readiness.json",
            "sha256": sha256_path(OUTPUT_PATH),
            "schema_version": prior.get("schema_version"),
        }
        return records, metadata, snapshot

    records = {
        row["task_id"]: build_legacy_entry(row, reviewed.get(row["task_id"]), index) for index, row in enumerate(rows)
    }
    return (
        records,
        {},
        {
            "path": ".agents/development/gdpval-task-readiness.json",
            "sha256": None,
            "schema_version": 1,
            "origin": "reconstructed from the frozen review artifact",
        },
    )


legacy_records, legacy_top_level, legacy_snapshot = load_legacy_snapshot()
if set(legacy_records) != set(row_ids):
    fail("legacy record map does not cover the frozen source exactly")
legacy_records = {task_id: legacy_records[task_id] for task_id in row_ids}
legacy_digest = digest_records(legacy_records)

legacy_scope_membership: dict[str, list[str]] = {
    "ordinary_route_candidate": [],
    "fixed_acceptance": [],
    "individual_check": [],
}
legacy_content_membership: dict[str, list[str]] = {
    "public_reference_candidate": [],
    "supplied_information_document_candidate": [],
    "code_calculation_specification_candidate": [],
    "individual_check": [],
}
legacy_membership: dict[str, dict[str, Any]] = {}
for index, row in enumerate(rows):
    task_id = row["task_id"]
    record = legacy_records[task_id]
    old_scope = record.get("acceptance_scope")
    old_content = record.get("content_readiness")
    if not isinstance(old_scope, str) or old_scope not in legacy_scope_membership:
        fail(f"legacy record {task_id} has unknown acceptance scope {old_scope!r}")
    if not isinstance(old_content, str) or old_content not in legacy_content_membership:
        fail(f"legacy record {task_id} has unknown content readiness {old_content!r}")
    legacy_scope_membership[old_scope].append(task_id)
    legacy_content_membership[old_content].append(task_id)
    legacy_membership[task_id] = {
        "line_number": index + 1,
        "dataset_index_zero_based": index,
        "task_id": task_id,
        "prior_content_readiness": old_content,
        "prior_content_readiness_reason": record.get("content_readiness_reason"),
        "prior_acceptance_scope": old_scope,
        "rationale": record.get("reason") or record.get("content_readiness_reason"),
        "limitations": record.get("acceptance_evidence_meaning"),
        "disposition": record.get("disposition"),
        "review_status": record.get("review_status"),
        "empirical_acceptance": record.get("empirical_acceptance"),
        "row_sha256": record.get("row_sha256"),
        "legacy_record_sha256": sha256_bytes(canonical_json(record)),
        "evidence_pointers": record_evidence_pointers(record),
    }

if {key: len(value) for key, value in legacy_scope_membership.items()} != {
    "ordinary_route_candidate": 189,
    "fixed_acceptance": 2,
    "individual_check": 29,
}:
    fail("legacy acceptance membership counts changed")
if {key: len(value) for key, value in legacy_content_membership.items()} != {
    "public_reference_candidate": 81,
    "supplied_information_document_candidate": 103,
    "code_calculation_specification_candidate": 5,
    "individual_check": 31,
}:
    fail("legacy content membership counts changed")

history_document = {
    "schema_version": 1,
    "history_kind": "legacy-readiness-ledger-and-content-triage",
    "generated_date": "2026-09-16",
    "source": deepcopy(source_info),
    "source_hashes": {
        "frozen_jsonl_sha256": source_info["sha256"],
        "review_artifact_sha256": REVIEW_ARTIFACT_SHA256,
        "prior_ledger_snapshot_sha256": legacy_snapshot.get("sha256"),
    },
    "review_snapshot": {key: deepcopy(value) for key, value in review.items() if key != "tasks"},
    "legacy_snapshot": legacy_snapshot,
    "legacy_partition": {
        "acceptance_scope": {
            "counts": {key: len(value) for key, value in legacy_scope_membership.items()},
            "membership": legacy_scope_membership,
            "definitions": {
                "ordinary_route_candidate": "Historical content-triage label for 189 rows; not a current scope status.",
                "fixed_acceptance": "Historical label for the two ordered fixed tasks; current inclusion is represented only by included/excluded.",
                "individual_check": "Historical label for 29 named checks; not a permanent exclusion.",
            },
        },
        "content_readiness": {
            "counts": {key: len(value) for key, value in legacy_content_membership.items()},
            "membership": legacy_content_membership,
            "definitions": {
                "public_reference_candidate": "Historical inference that participant-selected public references or research may be needed.",
                "supplied_information_document_candidate": "Historical inference that supplied information or documents may be needed.",
                "code_calculation_specification_candidate": "Historical inference that code, calculation, or specification work may be central.",
                "individual_check": "Historical named check retained for later task-specific review.",
            },
        },
        "historical_counts_are_not_current_acceptance": True,
        "candidate_is_not_empirical_acceptance": True,
        "limitations": [
            "The historical labels were content triage and did not establish participant success or task feasibility.",
            "The 29 other individual checks remain available for later review and were not made permanent exclusions.",
            "Public-reference availability and participant retrieval were not asserted by the triage.",
            "No bulk promotion of the 189 historical candidates to empirical acceptance is permitted.",
        ],
    },
    "correction_history": {
        "bb499d9c": "The prompt allows <=25 pages and the rubric requires <=15; this is a prospective policy issue, not inherent impossibility.",
        "1137e2bb": "A summary table or PivotTable is allowed while PO-number preservation and operable drill-down remain required.",
        "ee09d943": "The task permits explicitly reporting missing inputs.",
    },
    "membership": legacy_membership,
    "legacy_top_level": legacy_top_level,
    "legacy_records": legacy_records,
    "preservation": {
        "legacy_record_count": len(legacy_records),
        "legacy_record_digest": legacy_digest,
        "all_source_ids_present_once": True,
        "all_empirical_acceptance_values_preserved": all(
            record.get("empirical_acceptance") == "unconfirmed" for record in legacy_records.values()
        ),
        "all_dispositions_preserved": all("disposition" in record for record in legacy_records.values()),
        "all_row_hashes_preserved": all(
            isinstance(record.get("row_sha256"), str) for record in legacy_records.values()
        ),
        "evidence_pointers_preserved": True,
        "field_names_by_task": {task_id: sorted(record) for task_id, record in legacy_records.items()},
        "empirical_acceptance_by_task": {
            task_id: record.get("empirical_acceptance") for task_id, record in legacy_records.items()
        },
        "disposition_by_task": {task_id: record.get("disposition") for task_id, record in legacy_records.items()},
        "row_hash_by_task": {task_id: record.get("row_sha256") for task_id, record in legacy_records.items()},
        "evidence_pointers_by_task": {
            task_id: record_evidence_pointers(record) for task_id, record in legacy_records.items()
        },
    },
}
HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
if not HISTORY_PATH.exists():
    HISTORY_PATH.write_text(json.dumps(history_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
history_sha256 = sha256_path(HISTORY_PATH)
if history_sha256 is None:
    fail("content-triage history could not be hashed after writing")


def declared_paths(row: dict[str, Any], field: str) -> list[str]:
    return [value for value in as_list(row.get(field)) if isinstance(value, str)]


def retrieval_signal(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:online|publicly available|online resources?|research|retrieve|retrieval|search(?:ing)?|"
            r"source provenance|participant[- ](?:selected|retrieval)|public references?|web sources?)\b",
            text,
            re.IGNORECASE,
        )
    )


def task_route(line_number: int, row: dict[str, Any]) -> tuple[str, str]:
    prompt = str(row.get("prompt") or "")
    occupation = str(row.get("occupation") or "")
    paths = declared_paths(row, "deliverable_files") + declared_paths(row, "reference_files")
    formats = unique_formats(paths)
    text = f"{prompt} {occupation}".lower()
    media = bool({"audio", "video", "image", "layered image"} & set(formats)) or bool(
        re.search(r"\b(audio|video|music|film|vfx|soundtrack|show reel|footage)\b", text)
    )
    cad = bool({"STEP/CAD", "CAD"} & set(formats)) or bool(
        re.search(r"\b(cad|3d model|step file|step model|step format)\b", text)
    )
    code = line_number in CODE_CALCULATION_SPECIFICATION_LINES or bool(
        re.search(r"\b(python|react|typescript|javascript|software developer|backend|api|code|notebook|query)\b", text)
    )
    if media or cad:
        return "artifact_creation", "Prompt or declared formats indicate an authored media or CAD artifact."
    if code:
        return "code", "Prompt, occupation, or deliverable indicates code or technical specification work."
    if line_number in PUBLIC_REFERENCE_LINES or retrieval_signal(text):
        return "research", "Prompt or historical content basis indicates research, retrieval, or source selection."
    if declared_paths(row, "deliverable_files"):
        return (
            "artifact_creation",
            "A deliverable artifact is declared; task-specific artifact semantics remain unconfirmed.",
        )
    return (
        "research",
        "No authoritative route title is supplied; this is a preliminary research/output route inference.",
    )


def content_category(line_number: int, row: dict[str, Any], route: str) -> tuple[str, list[str]]:
    prompt = str(row.get("prompt") or "")
    refs = declared_paths(row, "reference_files")
    urls = declared_paths(row, "reference_file_urls") + declared_paths(row, "reference_file_hf_uris")
    text = prompt.lower()
    retrieval = line_number in PUBLIC_REFERENCE_LINES or retrieval_signal(text)
    supplied = bool(refs or urls)
    if route == "code":
        category = "technical_code_or_specification"
    elif supplied and retrieval:
        category = "mixed_supplied_and_retrieved_content"
    elif supplied:
        category = "supplied_content_processing"
    elif retrieval:
        category = "participant_retrieved_content"
    elif route == "artifact_creation":
        category = "participant_authored_artifact"
    else:
        category = "prompt_defined_output"
    signals = []
    if refs:
        signals.append("declared reference files")
    if urls:
        signals.append("declared reference URLs or repository URIs")
    if retrieval:
        signals.append("prompt or historical basis mentions retrieval or source selection")
    if not signals:
        signals.append("prompt and deliverable metadata only")
    return category, signals


def requirement_status(review_task: dict[str, Any] | None) -> str:
    return "reviewed_inference_unconfirmed" if review_task else "preliminary_unconfirmed"


def build_required_capabilities(
    line_number: int,
    row: dict[str, Any],
    review_task: dict[str, Any] | None,
    route: str,
    formats: list[str],
) -> dict[str, Any]:
    prompt = str(row.get("prompt") or "")
    rubric = canonical_text(row.get("rubric_json") or "")
    refs = declared_paths(row, "reference_files")
    outputs = declared_paths(row, "deliverable_files")
    requirements: list[dict[str, Any]] = []

    def add(
        name: str, stage: str, basis: str, observed_status: str | None = None, observed_evidence: str | None = None
    ) -> None:
        item: dict[str, Any] = {
            "name": name,
            "stage": stage,
            "status": "inferred_unconfirmed",
            "basis_ref": "definitions.requirement_inference",
        }
        if observed_status is not None:
            item["review_observation_status"] = observed_status
        if observed_evidence is not None:
            item["review_observation"] = observed_evidence
        requirements.append(item)

    if review_task:
        for stage, stage_info in review_task.get("capabilities", {}).items():
            if not isinstance(stage_info, dict):
                continue
            for required in as_list(stage_info.get("required")):
                add(
                    str(required),
                    str(stage),
                    "Exact requirement recorded in the tracked historical review snapshot; the review observation is not task acceptance.",
                    str(stage_info.get("status")) if stage_info.get("status") is not None else None,
                    str(stage_info.get("evidence")) if stage_info.get("evidence") is not None else None,
                )
    else:
        if refs:
            add(
                "read declared supplied reference files",
                "input",
                "Frozen row reference_files metadata; bytes and readability are unconfirmed.",
            )
        if outputs:
            add(
                "produce the declared deliverable files",
                "execution",
                "Frozen row deliverable_files metadata; task-specific content is unconfirmed.",
            )
        add(
            "execute the task-specific workflow",
            "execution",
            "Preliminary inference from the frozen prompt; the row has no named prompt/rubric review record.",
        )
        add(
            "evaluate the requested result against the rubric",
            "evaluation",
            "Preliminary inference from the frozen rubric; no criterion-level execution was performed.",
        )

    if formats:
        for value in formats:
            add(
                f"read or produce the declared {value} material as applicable",
                "input" if value in unique_formats(refs) else "execution",
                "Frozen file extension metadata; exact task use and successful handling remain unconfirmed.",
            )
    if route == "research":
        add(
            "retrieve, select, and record provenance for participant-chosen sources",
            "input",
            "Prompt or content basis indicates research/retrieval; participant selection and source availability are unconfirmed.",
        )
    elif route == "code":
        add(
            "author and run the requested code or technical specification",
            "execution",
            "Prompt and route inference; semantic correctness and task execution are unconfirmed.",
        )
        add(
            "select or provide task dependencies within the isolated environment",
            "execution",
            "Preliminary capability inference; no task-specific dependency result is copied.",
        )
    else:
        add(
            "author the requested artifact and conform to its output format",
            "execution",
            "Prompt and deliverable metadata; task-specific authoring and evaluation are unconfirmed.",
        )

    text = f"{prompt} {rubric}".lower()
    hint_patterns = {
        "calculation_formula_recalc": r"\b(calculate|calculation|formula|recalculat|statistical|analysis|spreadsheet|chart)\b",
        "pivots": r"\bpivot(?:table)?s?\b",
        "revisions_updates": r"\b(track changes|revision|revising|update|updated|comment|edit)\b",
        "media_editing": r"\b(audio|video|music|mix|edit|timeline|composit|footage)\b",
        "dependencies": r"\b(dependenc|package|install|npm|pip|library|module)\b",
        "interactive_ui_or_actions": r"\b(interactive|interface|notebook|ui|user interface|click|drill[- ]down)\b",
        "native_document_inspection": r"\b(docx|word|pdf|office|render|page|presentation|powerpoint)\b",
        "output_format_compliance": r"\b(format|file|deliverable|export|submit|workbook|document)\b",
    }
    category_hints: dict[str, dict[str, Any]] = {}
    for name, pattern in hint_patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            category_hints[name] = {
                "status": "preliminary_unconfirmed",
                "basis_ref": "definitions.requirement_inference",
            }
    retrieval_applicable = route == "research" or retrieval_signal(text)
    category_hints["research_retrieval_selection"] = {
        "applicable": retrieval_applicable,
        "status": "preliminary_unconfirmed",
        "basis": "Applicability is inferred from prompt/metadata; participant retrieval and provenance remain unconfirmed.",
    }
    return {
        "requirements_inferred": {
            "status": requirement_status(review_task),
            "basis": {
                "source": f"{HISTORY_RELATIVE_PATH}#/review_snapshot"
                if review_task
                else "frozen prompt/rubric and file metadata",
                "prompt_excerpt": short_excerpt(review_task.get("prompt_excerpt") if review_task else prompt),
                "rubric_excerpt": short_excerpt(review_task.get("rubric_excerpt") if review_task else rubric),
            },
            "required": requirements,
            "category_hints": category_hints,
            "interpretation_ref": "definitions.requirement_inference",
        },
        "supplied_formats": unique_formats(refs),
        "output_formats": unique_formats(outputs),
        "research_retrieval_selection_ref": "requirements_inferred.category_hints.research_retrieval_selection",
        "capability_category_hints_ref": "requirements_inferred.category_hints",
        "verified_capability": {
            "status": "unverified",
            "task_specific": [],
            "common_profile_status_ref": "common_environment.shared_profile_status",
            "basis_ref": "definitions.task_specific_unverified",
        },
        "unconfirmed_ref": "definitions.task_specific_unverified",
    }


def conflict_items(line_number: int, review_task: dict[str, Any] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if line_number == 24:
        items.append(
            {
                "kind": "prompt_rubric_identity_and_template_conflict",
                "prompt_basis": "Prompt leaves the first-page social worker name and address blank.",
                "rubric_basis": "Rubric specifies a named social worker and a different filename/person identity.",
                "status": "identified_unconfirmed",
            }
        )
    elif line_number == 105:
        items.append(
            {
                "kind": "date_range_conflict",
                "prompt_basis": "01/04/25-02/21/25",
                "rubric_basis": "2025-01-04 to 2025-03-01",
                "status": "identified_unconfirmed",
            }
        )
    elif line_number == 210:
        items.append(
            {
                "kind": "page_limit_conflict",
                "prompt_basis": "Word document no longer than 25 pages.",
                "rubric_basis": "Document 15 pages or fewer.",
                "status": "identified_unconfirmed",
                "interpretation": "A document of 15 pages or fewer satisfies both limits; this is a prospective policy issue, not inherent impossibility.",
            }
        )
    if review_task:
        for conflict in as_list(review_task.get("additional_conflicts")):
            if isinstance(conflict, str) and not any(item.get("detail") == conflict for item in items):
                items.append(
                    {
                        "kind": "review_recorded_additional_conflict",
                        "detail": conflict,
                        "status": "identified_unconfirmed",
                    }
                )
    if (
        line_number in INDIVIDUAL_REASONS
        and INDIVIDUAL_REASONS[line_number][0] == "specification_conflict"
        and not items
    ):
        items.append(
            {
                "kind": "specification_conflict",
                "detail": INDIVIDUAL_REASONS[line_number][1],
                "status": "identified_unconfirmed",
            }
        )
    return items


def build_task_specific_checks(
    line_number: int,
    row: dict[str, Any],
    review_task: dict[str, Any] | None,
    formats: list[str],
) -> dict[str, Any]:
    prompt = str(row.get("prompt") or "")
    rubric = canonical_text(row.get("rubric_json") or "")
    refs = declared_paths(row, "reference_files")
    ref_urls = declared_paths(row, "reference_file_urls")
    ref_hf = declared_paths(row, "reference_file_hf_uris")
    outputs = declared_paths(row, "deliverable_files")
    stage_statuses = {
        stage: str(info.get("status"))
        for stage, info in (review_task.get("capabilities", {}) if review_task else {}).items()
        if isinstance(info, dict) and info.get("status") is not None
    }
    missing: list[str] = []
    unread: list[str] = []
    if review_task is None:
        missing.append("task-specific prompt/rubric review and criterion mapping")
    if refs or ref_urls or ref_hf:
        unread.append("declared reference material availability and readability are unconfirmed")
    if outputs:
        unread.append("declared deliverable artifact availability and actual viewing are unconfirmed")
    for stage, status in stage_statuses.items():
        if not any(token in status.lower() for token in ("confirmed", "complete", "partial")):
            unread.append(f"{stage} requirement evidence is unconfirmed ({status})")
    unread.append("task-specific generation and evaluation have not been executed in this ledger")
    conflicts = conflict_items(line_number, review_task)
    if conflicts:
        conflict_status = "identified_unconfirmed"
    elif review_task:
        conflict_status = "none_recorded_in_review"
    else:
        conflict_status = "not_reviewed"
    dates = extract_dates(prompt, rubric)
    return {
        "status": "reviewed" if review_task else "unreviewed",
        "missing": missing,
        "unread_or_unconfirmed": unread,
        "dates": {
            "values": dates,
            "status": "metadata_only_unconfirmed" if dates else "none_declared",
        },
        "standards_or_data_access": {
            "status": "metadata_declared_availability_unconfirmed" if (refs or ref_urls or ref_hf) else "not_declared",
            "declared_reference_files": len(refs),
            "declared_reference_urls": len(ref_urls),
            "declared_reference_hf_uris": len(ref_hf),
            "declared_formats": formats,
            "basis_ref": "definitions.metadata_only_unconfirmed",
        },
        "source_or_rubric_conflicts": {
            "status": conflict_status,
            "items": conflicts,
            "basis_ref": "evidence_version.requirements and historical review snapshot",
        },
        "concrete_basis": {
            "source_line": line_number,
            "task_id": row["task_id"],
            "prompt_excerpt": short_excerpt(review_task.get("prompt_excerpt") if review_task else prompt),
            "rubric_excerpt": short_excerpt(review_task.get("rubric_excerpt") if review_task else rubric),
            "review_record": review_task is not None,
            "stage_statuses": stage_statuses,
            "row_hash": sha256_bytes(canonical_json(row)),
        },
    }


def environment_support(line_number: int, row: dict[str, Any], route: str, formats: list[str]) -> dict[str, Any]:
    task_capabilities = [
        {
            "capability": f"task-specific {route} generation",
            "status": "unverified",
            "common_profile_ref": COMMON_ENVIRONMENT["profile"],
            "permanent_exclusion": False,
        },
        {
            "capability": "task-specific evaluation",
            "status": "unverified",
            "common_profile_ref": COMMON_ENVIRONMENT["profile"],
            "permanent_exclusion": False,
        },
    ]
    return {
        "common_profile_ref": COMMON_ENVIRONMENT["profile"],
        "common_profile_status_ref": "common_environment.shared_profile_status",
        "applicable_roles": ["creation", "application", "evaluation"],
        "client_role_support_ref": "common_environment.client_role_support",
        "task_specific_capabilities": task_capabilities,
        "known_unsupported": [],
        "generation_vs_evaluation": {
            "generation": {"status": "unverified", "proof_is_task_specific": True},
            "evaluation": {"status": "unverified", "proof_is_task_specific": True},
            "proofs_are_separate": True,
        },
        "task_level_acceptance": "unverified",
        "permanent_exclusion_claim": False,
        "interpretation": "Common role probes do not establish this task's functional generation or evaluation.",
    }


def criterion_mapping(line_number: int, task_id: str) -> dict[str, Any]:
    path_text = FIXED_CRITERION_PATHS.get(line_number)
    if path_text is None:
        return {
            "status": "unconfirmed",
            "mapping_scope": "not_mapped_in_this_bounded_ledger",
            "criterion_ids": [],
            "criterion_count": None,
            "result_status": "unconfirmed",
            "score": None,
        }
    path = ROOT / path_text
    document = load_json(path, "fixed-task criterion map")
    matrix_task: dict[str, Any] = document
    if isinstance(document.get("tasks"), list):
        matches = [value for value in document["tasks"] if isinstance(value, dict) and value.get("task_id") == task_id]
        if len(matches) != 1:
            fail(f"criterion matrix {path_text} has {len(matches)} entries for {task_id}")
        matrix_task = matches[0]
    if matrix_task.get("task_id") != task_id:
        fail(f"criterion map {path_text} belongs to another task")
    criteria = matrix_task.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        fail(f"criterion map {path_text} has no criteria")
    ids: list[str] = []
    author_types: Counter[str] = Counter()
    for criterion in criteria:
        if not isinstance(criterion, dict) or not isinstance(criterion.get("rubric_item_id"), str):
            fail(f"criterion map {path_text} has an invalid criterion")
        ids.append(criterion["rubric_item_id"])
        author_types[str(criterion.get("author_type", "human"))] += 1
    if len(set(ids)) != len(ids) or set(author_types) != {"human"}:
        fail(f"criterion map {path_text} is not a unique all-human map")
    return {
        "status": "available_unexecuted",
        "mapping_scope": "fixed_acceptance_task_only",
        "criterion_source": path_text,
        "source_row_sha256": matrix_task.get("source_row_sha256"),
        "criterion_ids": ids,
        "human_criterion_ids": ids,
        "criterion_count": len(ids),
        "author_type_counts": dict(author_types),
        "result_status": "unconfirmed",
        "results": [],
        "score": None,
        "unconfirmed_policy": "Retain criteria and withhold score; unknown is not zero, pass, or failure.",
    }


TRIAL_METADATA_FIELDS = (
    "status",
    "task_success",
    "receipt_path",
    "receipt_sha256",
    "environment_fingerprint",
    "elapsed_seconds",
    "model",
    "error",
)
NON_DISPATCHED_TRIAL_STATUSES = {"pending", "not_started", "planned", "unconfirmed", "unknown"}


def compact_trial_phase(value: object) -> dict[str, dict[str, Any]]:
    """Keep execution metadata while excluding judge reports and quality scores."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for client, trial in value.items():
        if not isinstance(trial, dict):
            continue
        result[str(client)] = {field: deepcopy(trial[field]) for field in TRIAL_METADATA_FIELDS if field in trial}
    return result


def trial_was_dispatched(trial: dict[str, Any]) -> bool:
    explicit = trial.get("execution_occurred")
    if isinstance(explicit, bool):
        return explicit
    status = trial.get("status")
    return isinstance(status, str) and status.lower() not in NON_DISPATCHED_TRIAL_STATUSES


def trial_phase_summary(phase: dict[str, dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(trial.get("status", "unconfirmed")) for trial in phase.values())
    task_success_statuses = Counter(str(trial.get("task_success", "unconfirmed")) for trial in phase.values())
    dispatched = sum(trial_was_dispatched(trial) for trial in phase.values())
    return {
        "client_trial_count": len(phase),
        "status_counts": dict(sorted(statuses.items())),
        "task_success_status_counts": dict(sorted(task_success_statuses.items())),
        "dispatch_recorded_count": dispatched,
        "dispatch_not_recorded_count": len(phase) - dispatched,
    }


def task_verification(task_id: str, line_number: int) -> dict[str, Any]:
    """Project the parent-owned trial map into the task ledger without scores."""
    if line_number not in FIXED_ACCEPTANCE_LINES:
        return {
            "recorded": False,
            "source_ref": TASK_VERIFICATION_RELATIVE_PATH,
            "source_sha256": TASK_VERIFICATION_SHA256,
            "source_hash_kind": "canonical_task_verification_map",
            "full_task_acceptance": "unconfirmed",
            "generation": {},
            "evaluation": {},
            "criterion_evidence_ref": None,
            "interpretation": "No fixed-task trial map applies to this row.",
        }
    record = TASK_VERIFICATION.get(task_id)
    if record is None:
        return {
            "recorded": False,
            "source_ref": TASK_VERIFICATION_RELATIVE_PATH,
            "source_sha256": TASK_VERIFICATION_SHA256,
            "source_hash_kind": "canonical_task_verification_map",
            "full_task_acceptance": "unconfirmed",
            "generation": {},
            "evaluation": {},
            "criterion_evidence_ref": None,
            "interpretation": "The fixed-task trial map has no record for this task yet.",
        }
    generation = compact_trial_phase(record.get("generation"))
    evaluation = compact_trial_phase(record.get("evaluation"))
    return {
        "recorded": True,
        "source_ref": TASK_VERIFICATION_RELATIVE_PATH,
        "source_sha256": TASK_VERIFICATION_SHA256,
        "source_hash_kind": "canonical_task_verification_map",
        "full_task_acceptance": str(record.get("full_task_acceptance", "unconfirmed")),
        "generation": generation,
        "evaluation": evaluation,
        "generation_coverage": trial_phase_summary(generation),
        "evaluation_coverage": trial_phase_summary(evaluation),
        "criterion_evidence_ref": record.get("criterion_evidence_path"),
        "interpretation": record.get(
            "interpretation",
            "Execution evidence is separate from participant task success and full task acceptance.",
        ),
    }


def trial_method_status(phase: dict[str, dict[str, Any]], recorded: bool) -> str:
    if not recorded:
        return "planned_unconfirmed"
    if not phase:
        return "pending_recorded"
    if any(trial_was_dispatched(trial) for trial in phase.values()):
        return "executed_recorded"
    return "pending_recorded"


def trial_coverage(items: list[dict[str, Any]], phase_name: str) -> dict[str, Any]:
    by_task: dict[str, dict[str, Any]] = {}
    combined: dict[str, dict[str, Any]] = {}
    recorded_tasks = 0
    for item in items:
        verification = item["assessment"]["task_verification"]
        phase = verification.get(phase_name, {})
        if not isinstance(phase, dict):
            phase = {}
        if verification.get("recorded") and phase:
            recorded_tasks += 1
        task_id = item["identity"]["task_id"]
        if verification.get("recorded") and phase:
            by_task[task_id] = trial_phase_summary(phase)
        for client, trial in phase.items():
            if isinstance(trial, dict):
                combined[f"{task_id}:{client}"] = trial
    summary = trial_phase_summary(combined)
    summary["task_count_with_recorded_trials"] = recorded_tasks
    summary["by_task"] = by_task
    return summary


def full_task_acceptance_coverage(items: list[dict[str, Any]]) -> dict[str, int]:
    statuses = Counter(
        str(item["assessment"]["task_verification"].get("full_task_acceptance", "unconfirmed"))
        for item in items
        if item["assessment"]["task_verification"].get("recorded")
    )
    return dict(sorted(statuses.items()))


def assessment(
    line_number: int, row: dict[str, Any], review_task: dict[str, Any] | None, formats: list[str]
) -> dict[str, Any]:
    refs = declared_paths(row, "reference_files")
    outputs = declared_paths(row, "deliverable_files")
    criteria = criterion_mapping(line_number, row["task_id"])
    verification = task_verification(row["task_id"], line_number)
    generation_phase = verification["generation"]
    evaluation_phase = verification["evaluation"]
    generation_status = trial_method_status(generation_phase, bool(verification["recorded"]))
    evaluation_status = trial_method_status(evaluation_phase, bool(verification["recorded"]))
    generation_coverage = verification.get("generation_coverage", trial_phase_summary(generation_phase))
    evaluation_coverage = verification.get("evaluation_coverage", trial_phase_summary(evaluation_phase))
    generation_coverage_status = (
        "executed_unconfirmed"
        if generation_coverage["dispatch_recorded_count"] > 0
        else "pending_recorded"
        if generation_phase
        else "unconfirmed"
    )
    evaluation_coverage_status = (
        "executed_unconfirmed"
        if evaluation_coverage["dispatch_recorded_count"] > 0
        else "pending_recorded"
        if evaluation_phase
        else "unconfirmed"
    )
    prompt_review_status = "performed" if review_task else "unperformed_unconfirmed"
    methods = {
        "content_route_inference": {
            "status": "performed",
            "basis_ref": "evidence_version.evidence_layers.content_inference",
        },
        "prompt_rubric_review": {
            "status": prompt_review_status,
            "basis_ref": "evidence_version.evidence_layers.static",
        },
        "input_file_availability": {
            "status": "planned_unconfirmed",
            "basis_ref": "definitions.planned_unconfirmed",
        },
        "participant_generation": {
            "status": generation_status,
            "basis_ref": "definitions.planned_unconfirmed",
        },
        "task_evaluation": {
            "status": evaluation_status,
            "basis_ref": "definitions.planned_unconfirmed",
        },
    }
    if verification["recorded"]:
        methods["participant_generation"]["execution_evidence_ref"] = verification["source_ref"]
        methods["participant_generation"]["status_counts"] = generation_coverage["status_counts"]
        methods["task_evaluation"]["execution_evidence_ref"] = verification["source_ref"]
        methods["task_evaluation"]["status_counts"] = evaluation_coverage["status_counts"]
    unconfirmed_range = [
        "task-specific input availability and actual file reading",
        "participant generation and output correctness",
        "task-specific evaluator execution",
        "criterion-level results and score",
        "available pages/actions versus pages/actions actually viewed or performed",
        "cross-file reconciliation where multiple files are declared",
    ]
    if verification["recorded"]:
        unconfirmed_range.append(
            "recorded trial execution does not establish participant task success or full task acceptance"
        )
    if not review_task:
        unconfirmed_range.append("prompt/rubric interpretation and criterion mapping")
    return {
        "methods": methods,
        "performed_coverage": {
            "content_inference": "performed",
            "prompt_rubric": "reviewed" if review_task else "unreviewed",
            "input_metadata": {
                "declared_reference_file_count": len(refs),
                "declared_formats": formats,
                "available": "unverified",
                "actually_read": "not_recorded",
            },
            "artifact_files": {
                "declared_deliverable_file_count": len(outputs),
                "available": "unverified",
                "actually_viewed": "not_recorded",
            },
            "pages_or_actions": {
                "available": "unverified",
                "viewed_or_performed": "not_recorded",
                "count": None,
            },
            "cross_file_checks": {
                "declared_file_count": len(refs) + len(outputs),
                "checked": "unconfirmed",
            },
            "generation": generation_coverage_status,
            "evaluation": evaluation_coverage_status,
            "criterion_map": "available_unexecuted" if line_number in FIXED_ACCEPTANCE_LINES else "not_mapped",
            "generation_execution_status": generation_status,
            "evaluation_execution_status": evaluation_status,
        },
        "planned_vs_executed": {
            "prompt_rubric_review": {"planned": True, "executed": bool(review_task)},
            "input_file_read": {"planned": True, "executed": False},
            "participant_generation": {
                "planned": True,
                "executed": generation_coverage["dispatch_recorded_count"] > 0,
                "status": generation_status,
                "client_statuses": {
                    client: str(trial.get("status", "unconfirmed")) for client, trial in generation_phase.items()
                },
            },
            "task_evaluation": {
                "planned": True,
                "executed": evaluation_coverage["dispatch_recorded_count"] > 0,
                "status": evaluation_status,
                "client_statuses": {
                    client: str(trial.get("status", "unconfirmed")) for client, trial in evaluation_phase.items()
                },
            },
        },
        "available_vs_viewed": {
            "declared_files": {"available": "unverified", "viewed": "not_recorded"},
            "pages_or_actions": {"available": "unverified", "viewed_or_performed": "not_recorded"},
        },
        "unconfirmed_range": unconfirmed_range,
        "scoring": criteria,
        "task_verification": verification,
        "unknown_is_not_zero_pass_or_failure": True,
        "exhaustive_audit": {
            "status": "not_requested",
            "meaning": "The ledger maps the two available fixed criterion sources and leaves other rows unconfirmed; it is not an all-220 rubric audit.",
        },
    }


def build_task_record(index: int, row: dict[str, Any], review_task: dict[str, Any] | None) -> dict[str, Any]:
    line_number = index + 1
    task_id = row["task_id"]
    prompt = str(row.get("prompt") or "")
    rubric = canonical_text(row.get("rubric_json") or "")
    refs = declared_paths(row, "reference_files")
    outputs = declared_paths(row, "deliverable_files")
    route, route_basis = task_route(line_number, row)
    content_category_value, content_signals = content_category(line_number, row, route)
    all_formats = unique_formats(refs + outputs)
    ref_formats = unique_formats(refs)
    output_formats = unique_formats(outputs)
    verification = task_verification(task_id, line_number)
    trial_receipts = sorted(
        {
            str(trial["receipt_path"])
            for phase_name in ("generation", "evaluation")
            for trial in verification.get(phase_name, {}).values()
            if isinstance(trial, dict) and isinstance(trial.get("receipt_path"), str)
        }
    )
    trial_dispatch_recorded = any(
        trial_was_dispatched(trial)
        for phase_name in ("generation", "evaluation")
        for trial in verification.get(phase_name, {}).values()
        if isinstance(trial, dict)
    )
    summary = short_excerpt(review_task.get("prompt_excerpt") if review_task else first_prompt_sentence(prompt))
    occupation = row.get("occupation") if isinstance(row.get("occupation"), str) else None
    sector = row.get("sector") if isinstance(row.get("sector"), str) else None
    content_readiness = {
        "category": content_category_value,
        "status": "reviewed_inference_unconfirmed" if review_task else "preliminary_unconfirmed",
        "basis": {
            "prompt_excerpt": summary,
            "signals": content_signals,
            "source": "frozen prompt/rubric and file metadata",
        },
        "historical_membership_ref": f"{HISTORY_RELATIVE_PATH}#/membership/{task_id}",
    }
    identity = {
        "task_id": task_id,
        "name": f"Frozen row {line_number}: {occupation or 'unlabeled task'}",
        "name_is_derived_label": True,
        "name_basis": "Synthetic row/occupation label; it is not an authoritative task title.",
        "label": {"name": occupation, "sector": sector, "occupation": occupation},
        "summary": summary,
        "summary_basis": "Exact review excerpt where available, otherwise a concise frozen prompt excerpt.",
        "dataset_line": line_number,
        "dataset_index_zero_based": index,
    }
    primary_route = {
        "route": route,
        "basis": route_basis,
        "artifact_modalities": sorted(
            set(all_formats)
            | ({"audio/video"} if any(value in {"audio", "video"} for value in all_formats) else set())
            | ({"CAD/STEP"} if any(value in {"CAD", "STEP/CAD"} for value in all_formats) else set())
        ),
        "reference_formats": ref_formats,
        "output_formats": output_formats,
        "content_readiness": content_readiness,
        "deployment_claim": {
            "status": "not_inferred",
            "basis": "A prompt, code, or specification does not establish a deployed system.",
        },
    }
    required = build_required_capabilities(line_number, row, review_task, route, all_formats)
    checks = build_task_specific_checks(line_number, row, review_task, all_formats)
    environment = environment_support(line_number, row, route, all_formats)
    task_evidence_pointers = record_evidence_pointers(legacy_records[task_id])
    evidence_version = {
        "frozen_source": {
            "path": source_info["path"],
            "dataset_repository_revision": source_info.get("dataset_repository_revision"),
            "dataset_version_record_sha256": source_info.get("dataset_version_record_sha256"),
            "line_number": line_number,
            "row_sha256": sha256_bytes(canonical_json(row)),
            "source_sha256": source_info["sha256"],
        },
        "requirements": {
            "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
            "rubric_sha256": sha256_bytes(canonical_text(row.get("rubric_json") or "").encode("utf-8")),
            "prompt_excerpt": summary,
            "rubric_excerpt": short_excerpt(review_task.get("rubric_excerpt") if review_task else rubric),
            "basis_ref": "definitions.requirement_inference",
        },
        "declared_files": {
            "reference_files": refs,
            "reference_file_urls": declared_paths(row, "reference_file_urls"),
            "reference_file_hf_uris": declared_paths(row, "reference_file_hf_uris"),
            "deliverable_files": outputs,
            "deliverable_file_urls": declared_paths(row, "deliverable_file_urls"),
            "deliverable_file_hf_uris": declared_paths(row, "deliverable_file_hf_uris"),
            "status": "metadata_only_unconfirmed",
        },
        "environment": {
            "profile_ref": COMMON_ENVIRONMENT["profile"],
            "definition_refs": "common_environment.definition_refs",
            "tools_and_versions": "Referenced by the common profile; task-specific invocation and versions are unconfirmed.",
        },
        "evidence_layers": {
            "static": {
                "status": "preserved",
                "refs": ["frozen JSONL row", f"{HISTORY_RELATIVE_PATH}#/review_snapshot"],
            },
            "content_inference": {
                "status": "performed_unconfirmed",
                "basis_ref": "definitions.requirement_inference",
            },
            "real_task": {
                "status": (
                    "executed_unconfirmed"
                    if trial_dispatch_recorded
                    else "pending_recorded"
                    if verification["recorded"]
                    else "unconfirmed"
                ),
                "paths": trial_receipts,
                "verification_ref": (
                    f"{TASK_VERIFICATION_RELATIVE_PATH}#/task_verification/{task_id}"
                    if verification["recorded"]
                    else None
                ),
                "full_task_acceptance": verification["full_task_acceptance"],
            },
        },
        "empirical_acceptance": "unconfirmed",
        "historical": {
            "history_file": HISTORY_RELATIVE_PATH,
            "legacy_record_json_pointer": f"/legacy_records/{task_id}",
            "legacy_record_sha256": sha256_bytes(canonical_json(legacy_records[task_id])),
            "historical_evidence_pointers": task_evidence_pointers,
            "acceptance_evidence_pointer": legacy_records[task_id].get("acceptance_evidence"),
            "current_criteria_matrix_ref": ".agents/development/evidence/gdpval-acceptance-criteria.json",
            "task_verification_ref": (
                f"{TASK_VERIFICATION_RELATIVE_PATH}#/task_verification/{task_id}" if verification["recorded"] else None
            ),
            "task_verification_sha256": verification["source_sha256"],
            "results_copied": False,
        },
    }
    if line_number in FIXED_ACCEPTANCE_LINES:
        scope: dict[str, Any] = {
            "status": "included",
            "reason": "One of the two ordered current acceptance tasks; task-level empirical acceptance remains unconfirmed.",
            "fixed_acceptance_order": 1 if line_number == 88 else 2,
        }
    else:
        scope = {
            "status": "excluded",
            "reason": "Outside the current two-task acceptance execution; retained for future task-specific review and not a permanent feasibility claim.",
            "fixed_acceptance_order": None,
        }
    result = {
        "identity": identity,
        "primary_route": primary_route,
        "required_capabilities": required,
        "task_specific_checks": checks,
        "environment_support": environment,
        "assessment": assessment(line_number, row, review_task, all_formats),
        "evidence_version": evidence_version,
        "acceptance_scope": scope,
    }
    if set(result) != CURRENT_SECTION_KEYS:
        fail(f"task {task_id} does not have exactly the eight current sections")
    return result


requirements_review = load_json(ROOT / REVIEW_PATH, "all-task requirements review")
current_review = task_map(requirements_review["tasks"], "all-task requirements")
if requirements_review["source"]["sha256"] != source_hash or set(current_review) != set(row_ids):
    fail("current requirements review must cover the exact frozen 220-task source")
current_evidence = (
    load_json(ROOT / EVIDENCE_PATH, "all-task capability evidence") if (ROOT / EVIDENCE_PATH).exists() else {}
)
route_reference = current_evidence.get("route_applicability_record")
if route_reference is not None:
    route_path = ROOT / ".agents/development/evidence/gdpval-220-route-applicability.json"
    if route_reference.get("path") != route_path.relative_to(ROOT).as_posix():
        fail("unexpected current route mapping path")
    if hashlib.sha256(route_path.read_bytes()).hexdigest() != route_reference.get("sha256"):
        fail("current route mapping differs from its evidence hash")
    current_routes = load_json(route_path, "source-bound common routes")
    current_evidence["route_applicability"] = current_routes["tasks"]
historical_environment = deepcopy(COMMON_ENVIRONMENT)
COMMON_ENVIRONMENT.update(
    profile="gdpval-v2",
    shared_profile_status=current_evidence.get("common_environment_acceptance", {}).get("status", "unverified"),
    role_evidence=current_evidence.get("role_evidence", {}),
    evidence_refs=[EVIDENCE_PATH],
    client_role_support=current_evidence.get(
        "client_role_support",
        {
            client: {"status": "unverified", "roles": ["creation", "application", "evaluation"]}
            for client in ("codex", "claude")
        },
    ),
    interpretation="Common native checks, real CLI dispatch and task-level acceptance are separate. Historical gdpval-v1 evidence is retained with explicit applicability.",
)
items = [
    apply_review(
        build_task_record(index, row, reviewed.get(row["task_id"])),
        row,
        current_review[row["task_id"]],
        current_evidence,
    )
    for index, row in enumerate(rows)
]
if len(items) != len(rows):
    fail(f"output coverage changed: expected {len(rows)}, got {len(items)}")
if {item["identity"]["task_id"] for item in items} != set(row_ids):
    fail("output task IDs do not cover the frozen source exactly")
if len({item["identity"]["task_id"] for item in items}) != len(items):
    fail("output task IDs are duplicated")

content_counts = Counter(item["primary_route"]["content_readiness"]["status"] for item in items)
environment_task_counts = Counter(item["environment_support"]["task_level_acceptance"] for item in items)
generation_counts = Counter(
    item["environment_support"]["generation_vs_evaluation"]["generation"]["status"] for item in items
)
evaluation_counts = Counter(
    item["environment_support"]["generation_vs_evaluation"]["evaluation"]["status"] for item in items
)
scope_counts = Counter(item["acceptance_scope"]["status"] for item in items)
included = [
    {
        "order": item["acceptance_scope"]["fixed_acceptance_order"],
        "task_id": item["identity"]["task_id"],
        "line_number": item["identity"]["dataset_line"],
    }
    for item in items
    if item["acceptance_scope"]["fixed_acceptance_order"] is not None
]
included.sort(key=lambda value: value["order"])
if dict(scope_counts) != {"included": 220}:
    fail(f"current acceptance inclusion counts changed: {dict(scope_counts)}")
if [value["line_number"] for value in included] != [88, 129] or [value["order"] for value in included] != [1, 2]:
    fail("current fixed acceptance order changed")
if set(environment_task_counts) - {"unverified", "common_routes_applicable_with_limits", "route_gaps_remain"}:
    fail("unknown route acceptance state")
if any(item["assessment"]["scoring"]["result_status"] != "unconfirmed" for item in items):
    fail("route adoption must not invent artifact scores")
if sum(content_counts.values()) != len(items):
    fail("content readiness counts do not cover all tasks")

axes = {
    "content_readiness": {
        "dimension": "content-based readiness",
        "counts": dict(sorted(content_counts.items())),
        "status_counts": dict(sorted(content_counts.items())),
        "basis": "Per-task prompt, rubric, occupation, and declared file metadata; no category is empirical acceptance.",
        "candidate_is_not_empirical_acceptance": True,
        "historical_triage_ref": HISTORY_RELATIVE_PATH,
    },
    "target_environment_acceptance": {
        "dimension": "target-environment support and task acceptance",
        "task_level_status_counts": dict(sorted(environment_task_counts.items())),
        "common_profile": {
            "ref": "gdpval-v2",
            "status": current_evidence.get("common_environment_acceptance", {}).get("status", "unverified"),
            "defined_once_in_common_environment": True,
            "not_task_acceptance_count": True,
        },
        "generation_status_counts": dict(sorted(generation_counts.items())),
        "evaluation_status_counts": dict(sorted(evaluation_counts.items())),
        "task_trial_coverage": {
            "scope": "Historical eleven-session record; current trials are separate below.",
            "source_ref": TASK_VERIFICATION_RELATIVE_PATH,
            "source_sha256": TASK_VERIFICATION_SHA256,
            "source_hash_kind": "canonical_task_verification_map",
            "generation": trial_coverage(items, "generation"),
            "evaluation": trial_coverage(items, "evaluation"),
            "full_task_acceptance_status_counts": full_task_acceptance_coverage(items),
            "interpretation": "Counts recorded client trials and dispatch evidence; they are not task success or full environment acceptance.",
        },
        "current_trial_coverage": {
            "source_ref": EVIDENCE_PATH,
            "application_status_counts": dict(
                Counter(
                    result.get("execution_status", "unconfirmed")
                    for session in current_evidence.get("model_sessions", [])
                    if session["mode"] == "application"
                    for result in session.get("results", [])
                )
            ),
            "evaluation_status_counts": dict(
                Counter(
                    result.get("judge_execution_status", "unconfirmed")
                    for session in current_evidence.get("model_sessions", [])
                    if session["mode"] == "evaluation"
                    for result in session.get("results", [])
                )
            ),
            "task_success_inferred": False,
        },
        "status_vocabulary": ["unverified", "common_routes_applicable_with_limits", "route_gaps_remain"],
        "interpretation": "Shared profile verification and task-level functional acceptance are separate; one failure does not establish permanent unsupported status.",
    },
    "current_acceptance_scope": {
        "dimension": "current inclusion or exclusion scope",
        "counts": dict(sorted(scope_counts.items())),
        "first_real_cli_task_order": included,
        "status_vocabulary": ["included", "excluded"],
        "interpretation": "Only inclusion/exclusion is represented here. Historical triage membership is in the separate history file.",
    },
}

output = {
    "schema_version": 3,
    "historical_environment": historical_environment,
    "date": GENERATED_DATE,
    "ledger_kind": "GDPval task readiness ledger with independent axes",
    "source": {
        **deepcopy(source_info),
        "row_hash_format": "UTF-8 json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=False); no newline",
    },
    "definitions": deepcopy(LEDGER_DEFINITIONS),
    "review_context": {
        "path": HISTORY_RELATIVE_PATH,
        "sha256": REVIEW_ARTIFACT_SHA256,
        "named_reviewed_task_count": len(reviewed),
        "unreviewed_rows_are_explicit": True,
    },
    "common_environment": deepcopy(COMMON_ENVIRONMENT),
    "axes": axes,
    "policy": {
        "empirical_acceptance": "Common capability evidence may support multiple tasks when applicability is established; participant task success is not an infrastructure acceptance condition. Unverified requirements remain unconfirmed.",
        "unknown": "Unknown is not zero, pass, or failure.",
        "inference": "Content and capability requirements are labelled inferred/preliminary when they are not backed by task evidence.",
        "scope": "Current acceptance scope is independent from content readiness and environment support.",
        "exhaustive_audit": "All 220 tasks and 10453 original rubric items have a source-grounded requirements mapping and draft inspection procedures. Registration alone is not empirical capability acceptance.",
    },
    "history": {
        "path": HISTORY_RELATIVE_PATH,
        "sha256": history_sha256,
        "legacy_record_digest": legacy_digest,
        "legacy_record_count": len(legacy_records),
        "meaning": "Historical labels, full prior records, review findings, source hashes, correction history, and evidence pointers are retained in this file and are not current axes.",
    },
    "preservation": {
        "prior_ledger_snapshot": legacy_snapshot,
        "legacy_record_digest": legacy_digest,
        "legacy_record_count": len(legacy_records),
        "exact_id_mapping": True,
        "empirical_acceptance_preserved": all(
            record.get("empirical_acceptance") == "unconfirmed" for record in legacy_records.values()
        ),
        "dispositions_preserved": all("disposition" in record for record in legacy_records.values()),
        "row_hashes_preserved": all(isinstance(record.get("row_sha256"), str) for record in legacy_records.values()),
        "evidence_pointers_preserved": True,
        "historical_full_records": True,
    },
    "task_count": len(items),
    "reviewed_named_count": len(reviewed),
    "unconfirmed_empirical_acceptance_count": sum(
        item["evidence_version"]["empirical_acceptance"] == "unconfirmed" for item in items
    ),
    "tasks": items,
    "verification": {
        "receipt_path": ".audit/2026-09-21-all-tasks/readiness-generator.json",
        "model_runs": 0,
        "model_runs_meaning": "Generator runs no models; task trials are referenced under axes.target_environment_acceptance.task_trial_coverage.",
        "remote_writes": 0,
    },
}

for item in items:
    if set(item) != CURRENT_SECTION_KEYS:
        fail(f"task {item['identity']['task_id']} has an unexpected current field")
for forbidden in ("ordinary_route_candidate", "fixed_acceptance", "individual_check"):
    if f'"{forbidden}":' in json.dumps(output, ensure_ascii=False):
        fail(f"legacy mixed taxonomy leaked into the current ledger: {forbidden}")

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
output_sha256 = sha256_path(OUTPUT_PATH)
if output_sha256 is None:
    fail("readiness ledger could not be hashed after writing")

receipt = {
    "schema_version": 1,
    "purpose": "Independent-axis GDPval readiness ledger restructure; generator made no model runs or remote writes and references separately recorded task trials",
    "generated_date": GENERATED_DATE,
    "generator": {
        "path": ".agents/development/scripts/gdpval_readiness.py",
        "sha256": sha256_path(Path(__file__).resolve()),
    },
    "output": {
        "path": ".agents/development/gdpval-task-readiness.json",
        "sha256": output_sha256,
        "schema_version": output["schema_version"],
    },
    "history": {
        "path": HISTORY_RELATIVE_PATH,
        "sha256": history_sha256,
        "legacy_record_digest": legacy_digest,
    },
    "source": deepcopy(source_info),
    "source_argument": str(SOURCE_ARGUMENT_PATH),
    "source_argument_sha256": source_hash,
    "derived_axes": deepcopy(axes),
    "checks": {
        "frozen_row_count": len(rows),
        "output_task_count": len(items),
        "unique_ids": len({item["identity"]["task_id"] for item in items}) == len(rows),
        "exact_source_id_coverage": {item["identity"]["task_id"] for item in items} == set(row_ids),
        "section_keys_exact": all(set(item) == CURRENT_SECTION_KEYS for item in items),
        "current_scope_has_only_included_excluded": all(
            set(item["acceptance_scope"]) == {"status", "reason", "fixed_acceptance_order"} for item in items
        ),
        "legacy_taxonomy_absent_from_current": all(
            f'"{value}":' not in json.dumps(output, ensure_ascii=False)
            for value in ("ordinary_route_candidate", "fixed_acceptance", "individual_check")
        ),
        "no_empirical_results_copied": all(
            item["evidence_version"]["empirical_acceptance"] == "unconfirmed"
            and item["assessment"]["scoring"].get("result_status") == "unconfirmed"
            for item in items
        ),
        "task_trial_map_hash_is_canonical_only": TASK_VERIFICATION_SHA256 == digest_records(TASK_VERIFICATION),
        "task_trial_execution_separate_from_acceptance": all(
            item["assessment"]["scoring"].get("result_status") == "unconfirmed" for item in items
        ),
        "legacy_empirical_evidence_disposition_preserved": output["preservation"]["empirical_acceptance_preserved"]
        and output["preservation"]["dispositions_preserved"]
        and output["preservation"]["row_hashes_preserved"]
        and output["preservation"]["evidence_pointers_preserved"],
    },
    "fixed_acceptance": [
        {
            "order": item["acceptance_scope"]["fixed_acceptance_order"],
            "task_id": item["identity"]["task_id"],
            "line_number": item["identity"]["dataset_line"],
            "criterion_source": item["assessment"]["scoring"].get("criterion_source"),
            "criterion_count": item["assessment"]["scoring"].get("criterion_count"),
            "result_status": "unconfirmed",
        }
        for item in items
        if item["acceptance_scope"]["fixed_acceptance_order"] is not None
    ],
    "preservation": deepcopy(output["preservation"]),
    "model_runs": 0,
    "model_runs_meaning": "Generator only; task trial execution counts are in derived_axes.target_environment_acceptance.task_trial_coverage.",
    "remote_writes": 0,
}
RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
RECEIPT_PATH.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
receipt_sha256 = sha256_path(RECEIPT_PATH)
print(
    json.dumps(
        {
            "output": ".agents/development/gdpval-task-readiness.json",
            "output_sha256": output_sha256,
            "history": HISTORY_RELATIVE_PATH,
            "history_sha256": history_sha256,
            "receipt": ".audit/2026-09-21-all-tasks/readiness-generator.json",
            "receipt_sha256": receipt_sha256,
            "task_count": len(items),
            "axes": axes,
        },
        ensure_ascii=False,
    )
)
