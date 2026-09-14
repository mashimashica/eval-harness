# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Office preview lifecycle and cross-judge equality, without real model calls."""

from dataclasses import replace
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest
from PIL import Image
from test_evaluation_panel import _ApplicationExecutor, _experiment_config, _PanelExecutor, _task_source

from eval_harness import office_rendering as rendering
from eval_harness.artifacts import file_manifest, read_json, sha256_file
from eval_harness.config import EvaluationConfig, JudgeConfig, RuntimeConfig, load_evaluation_config, load_experiment
from eval_harness.errors import ArtifactError, ConfigError
from eval_harness.evaluate_pipeline import evaluate_run, resume_evaluation
from eval_harness.executor import ExecutionRequest, ExecutionResult
from eval_harness.run_pipeline import run_experiment


def office(path: Path, *, member: str = "word/document.xml", content: str = "<document/>") -> Path:
    with ZipFile(path, "w") as package:
        package.writestr(member, content)
    return path


@pytest.fixture
def fake_renderer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[Path]:
    """Only the native converter is mocked; cache, copying, and pipeline are real."""
    calls: list[Path] = []
    monkeypatch.setattr(rendering, "_tool_roots", lambda config: (tmp_path, tmp_path))
    monkeypatch.setattr(rendering, "_runtime_manifest", lambda root: [])

    def render(source: Path, target: Path, config: rendering.OfficeRenderingConfig, roots: Any) -> None:
        calls.append(source)
        color = "#" + sha256_file(source)[:6]
        Image.new("RGB", (40, 30), color).save(target / "page-001.png")
        (target / "document.pdf").write_bytes(b"test converter PDF")

    monkeypatch.setattr(rendering, "_render", render)
    return calls


def test_config_opt_in_roundtrip_and_reject_mechanical(tmp_path: Path) -> None:
    yaml = tmp_path / "visual.yaml"
    yaml.write_text(
        "evaluation:\n  method: pairwise\n  executor: codex\n  model: gpt-5.6-sol\n"
        "  office_rendering:\n    soffice: tools/Office.app/Contents/MacOS/soffice\n    pdftoppm: tools/poppler/bin/pdftoppm\n"
    )
    config = load_evaluation_config(yaml)
    assert config.office_rendering is not None
    assert config.office_rendering.soffice == tmp_path / "tools/Office.app/Contents/MacOS/soffice"
    from eval_harness.config import evaluation_snapshot, validate_evaluation_config
    from eval_harness.evaluate_pipeline import _evaluation_config_from_snapshot

    assert _evaluation_config_from_snapshot(evaluation_snapshot(config)) == config
    assert validate_evaluation_config(replace(config, method="mechanical"))
    yaml.write_text(yaml.read_text().replace("pdftoppm:", "unknown:"))
    with pytest.raises(ConfigError, match="exactly"):
        load_evaluation_config(yaml)


@pytest.mark.parametrize(
    "member,content",
    [
        ("word/vbaProject.bin", "macro"),
        ("xl/externalLinks/externalLink1.xml", "<link/>"),
        ("word/embeddings/object.bin", "embedded"),
        (
            "word/_rels/document.xml.rels",
            '<Relationships><Relationship TargetMode="External" Type="image" '
            'Target="file:///outside.png"/></Relationships>',
        ),
        ("word/_rels/document.xml.rels", '<!DOCTYPE a [<!ENTITY x "test">]><Relationships/>'),
    ],
)
def test_reject_active_or_external_inputs(tmp_path: Path, member: str, content: str) -> None:
    with pytest.raises(ArtifactError):
        rendering._check_office(office(tmp_path / "unsafe.docx", member=member, content=content))


def test_cache_preserves_source_and_never_rerenders_changed_preview(
    tmp_path: Path,
    fake_renderer: list[Path],
) -> None:
    source = office(tmp_path / "report.docx")
    before = sha256_file(source)
    cache = tmp_path / "cache"
    config = rendering.OfficeRenderingConfig(Path("unused"), Path("unused"))
    rendering.prepare_render_cache([source, source], cache, config)
    rendering.prepare_render_cache([source], cache, config)
    assert len(fake_renderer) == 1
    assert sha256_file(source) == before
    saved = rendering.cached_render(source, cache)
    assert saved["source_unchanged"] is True
    (cache / rendering.render_key(source) / "page-001.png").write_bytes(b"changed")
    with pytest.raises(ArtifactError, match="changed"):
        rendering.prepare_render_cache([source], cache, config)
    assert len(fake_renderer) == 1


def test_failed_render_retains_failure_without_retry(tmp_path: Path, fake_renderer: list[Path]) -> None:
    source = office(tmp_path / "unsafe.docx", member="word/vbaProject.bin")
    cache = tmp_path / "cache"
    config = rendering.OfficeRenderingConfig(Path("unused"), Path("unused"))
    with pytest.raises(ArtifactError, match="active"):
        rendering.prepare_render_cache([source], cache, config)
    record = read_json(cache / rendering.render_key(source) / "manifest.json")
    assert record["status"] == "failed" and record["source_unchanged"] is True
    with pytest.raises(ArtifactError, match="retained failure"):
        rendering.prepare_render_cache([source], cache, config)
    assert fake_renderer == []


def test_immutable_images_shared_across_panel_and_reversed_orders(
    tmp_path: Path,
    fake_renderer: list[Path],
) -> None:
    class OfficeApplication(_ApplicationExecutor):
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            office(request.cwd / "report.docx", content=f"<document>{len(self.requests)}</document>")
            return super().execute(request)

    source = _task_source(tmp_path)
    experiment = load_experiment(_experiment_config(tmp_path, source))
    run = run_experiment(experiment, tmp_path / "run", OfficeApplication(), check_auth=False)
    before = file_manifest(run.run_dir)
    sol = RuntimeConfig("codex", "gpt-5.6-sol", {})
    opus = RuntimeConfig("claude-code", "claude-opus-5", {"tool_mode": "sandboxed_shell"})
    config = EvaluationConfig(
        "pairwise",
        sol,
        (JudgeConfig("sol", sol), JudgeConfig("opus", opus)),
        office_rendering=rendering.OfficeRenderingConfig(Path("unused"), Path("unused")),
    )
    executors = {
        "codex": _PanelExecutor(sol.model, pairwise=True),
        "claude-code": _PanelExecutor(opus.model, pairwise=True),
    }
    result = evaluate_run(
        run.run_dir, config, tmp_path / "eval", check_auth=False, executor_factory=executors.__getitem__
    )
    assert result.valid_count == 4
    assert len(fake_renderer) == 2  # one conversion per generation, never one per judge/order
    assert file_manifest(run.run_dir) == before
    orders: list[list[list[str]]] = []
    for executor in executors.values():
        assert len(executor.requests) == 2
        judge_orders = []
        for request in executor.requests:
            assert len(request.images) == 2
            mapping = read_json(request.cwd / "visuals_manifest.json")["mapping"]
            assert len({entry["image_sha256"] for entry in mapping}) == 2
            judge_orders.append([entry["source_sha256"] for entry in mapping])
            assert all(sha256_file(request.cwd / entry["image"]) == entry["image_sha256"] for entry in mapping)
            assert "LibreOffice" in request.prompt
            assert set(path.parts[1] for path in request.images) == {"submission_A", "submission_B"}
        orders.append(judge_orders)
    assert orders[0] == orders[1]
    assert orders[0][0] == list(reversed(orders[0][1]))
    image = next((tmp_path / "eval" / "office_renders").rglob("*.png"))
    image.unlink()
    with pytest.raises(ArtifactError, match="changed"):
        resume_evaluation(result.evaluation_dir, check_auth=False, executor_factory=executors.__getitem__)
    assert all(len(executor.requests) == 2 for executor in executors.values())


def test_real_runtime_paths_must_not_be_wrappers_or_broad_roots(tmp_path: Path) -> None:
    with pytest.raises(ArtifactError, match="requires"):
        rendering._tool_roots(rendering.OfficeRenderingConfig(Path("/bin/sh"), Path("/bin/sh")))


def test_policy_does_not_grant_original_write_or_system_data_alias(tmp_path: Path) -> None:
    work, inputs = tmp_path / "work", tmp_path / "inputs"
    policy = rendering.sandbox_policy(work, inputs, (tmp_path / "Office.app", tmp_path / "poppler"))
    assert f'(allow file-write* (subpath "{work}"))' in policy
    assert f'(allow file-write* (subpath "{inputs}"))' not in policy
    assert '(subpath "/System")' not in policy  # /System/Volumes/Data aliases user data
    assert "(deny network*)" in policy
