# bigcodebench

Verifies model-generated Python solutions against the
[BigCodeBench](https://github.com/bigcode-project/bigcodebench) unittest
suite. Each task ships its own `unittest.TestCase` class plus an
`entry_point` function name; the model's extracted code is calibrated
(`code_prompt + "\n    pass\n" + extracted`) and run through
`bigcodebench.eval.untrusted_check` in an isolated subprocess.

## Provisioned grader runtime

The fixed grader runtime is prepared by the reviewed CI provisioning job
under a fresh private root. It contains the locked CPython 3.11.16 venv,
vendored native metric, pinned offline NLTK data, and a read-only runtime
manifest. This server only resolves that manifest and calls the shared
attested host sandbox; it never creates a venv, resolves dependencies,
downloads data, or launches an interpreter directly.

## Example usage

```bash
# Running servers
gym env start \
    --model-type vllm_model \
    --resources-server bigcodebench

# Collecting rollouts (5-example smoke test)
gym eval run --no-serve \
    --agent bigcodebench_simple_agent \
    --input resources_servers/bigcodebench/data/example.jsonl \
    --output results/bigcodebench_rollouts.jsonl \
    --num-repeats 1
```

## Reasoning-parser note

When serving a reasoning model (Nemotron, Qwen3-Thinking, DeepSeek-R1,
GPT-OSS), start vLLM with `--reasoning-parser <name>` so `<think>...</think>`
is stripped at the model edge. Without it, the code-extractor's
`</think>`-stripping rule still fires on the resource-server side, but
post-hoc surgery diverges from Skills' parse-reasoning-True behaviour on
truncated rollouts. See the migration recipe's `run_*.py` for the
canonical setup.

## Calibration

`bigcodebench.evaluate.evaluate(..., calibrated=True)` prepends the
benchmark's `code_prompt` (function signature + docstring stub) plus
`"\n    pass\n"` to the model's solution before running the unittest.
This guarantees the entry_point is defined even when the model returned
only the function body. We replicate it verbatim in `verify()`.
