<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR04 public-boundary draft review

Reviewer: Sol, read-only fixed source. Head `fe23c09bedf07d51ec320373fd89f502428dff16`,
base `7ebef3f004fad1a8df88792dfac6f0db7b1dd3c7`. This is the first review of the new
public seam, not a failed corrective round. No public-draft unit/type/Linux result has
been claimed. Formal Draft PR #43 remains on reviewed preceding source `0c919a5c`.

## Required corrections

1. **P1 identity before execution** — grader_sandbox.py:1065–1188,1364–1409,1457–1472:
   runtime manifest absence succeeds, inventory hashes are optional and bwrap path is
   not compared. Runtime bwrap/Python/build-package/installed-bootstrap/source provenance
   is incompletely compared. Runtime-selected bwrap is host-executed before identity
   checks; Python expected hash is not compared before probe. Run recalculation is not
   compared with cached preflight identities. Require all manifest fields and compare
   every expected identity before executing anything; missing, tampered and stale
   binary/bootstrap/runtime fixtures must fail without process creation.
2. **P1 incomplete and unbounded probe** — grader_sandbox.py:1244–1312: only namespace
   inodes, capability fields, root/tmp write behavior and downloader config are proved.
   Ubuntu 24.04, private proc, mountinfo/all readonly mounts, nested userns, actual rlimits,
   dummy secret, external sentinels, sys.path, IPv4/IPv6/Unix listeners, all seven package
   statuses and lookup are absent. CLI limits after `python -c` do not install rlimits.
   Output size is checked after buffering; timeout does not prove descendant cleanup.
   Do not return ok until all required real facts hold. Reuse bounded lifecycle/limit
   enforcement rather than introducing a second unbounded launch path.
3. **P1 startup failure scored** — app.py:69–75,98–119: failed preflight is cached while
   startup succeeds; empty/no-code can return zero before checking it. Fail startup and
   all requests closed on unavailable infrastructure, with no result row or zero metric.
4. **P1 prepared-root connection** — app.py:70, evaluator registry.py:120 and
   grader_sandbox.py:1065–1075: callers pass repository resources but installer creates
   a separate RUNNER_TEMP prepared resource/runtime pair. No trusted connection exists,
   including for a future accepted manifest. Remove the uncontracted resource-local
   runtime shadow preference. Provide one explicit trusted, validated readonly locator;
   candidate path/role must remain impossible to select by request/YAML/environment.
5. **P1 planned forbidden roots** — evaluator.py:130–175 and grader_sandbox.py:423–435,1211:
   production forbidden_roots remain empty, so future run/workspace roots can appear
   below recursively mounted venv/base/data. Strict-existing resolution also rejects
   an as-yet-uncreated planned run root. Bind canonical planned roots to spec digest,
   reject intersections with every selected mount and validate again before launch.
6. **P1 locked launch order** — grader_sandbox.py:1409,1449–1482: probe launch is outside
   UID flock and grading rehash/key/input happen before lock acquisition. Serialize all
   launches; under lock rehash, compare attestation, encode, build, supervise and confirm
   cleanup. Test identity drift while lock acquisition waits.
7. **P2 common outcomes and provenance** — app.py:136–170, evaluator.py:85–107,180–227:
   caller status names differ and evaluator uses details.status instead of native_status.
   Persist independent manifest, attestation, lock, sandbox and policy provenance through
   one shared mapping, alongside separate dataset revision. Do not change central runner.
8. **P2 exact public inputs** — evaluator.py:69–82, app.py:124–133: str coercion accepts
   non-string fields, while oversize/invalid request construction leaks ProtocolError.
   Check exact types/task identity and wrap protocol rejection as GraderInfrastructureError;
   add non-string, oversized, NUL and task-ID consistency regressions.
9. **P2 accepted limits bypass** — grader_sandbox.py:1028–1051,1473: non-None accepted
   path bypasses production-limit guard. None is exclusively accepted; explicit path is
   exclusively exact candidate. Reject accepted nonproduction limits during preflight.
10. **P2 async cancellation** — app.py:127–134: cancellation releases semaphore while
    the to_thread supervisor remains running, allowing accumulation of waiting threads.
    Hold semaphore ownership until that worker finishes, including cancellation paths.
11. **P2 legacy residue** — setup_bcb_venv.py:29–95, evaluator registry.py:66 and resource
    config/README retain mutable download, .installed, Python3.10 and .bcb_venv/direct-route
    assumptions. Remove or replace with validated readonly setup semantics. No ignored
    legacy argument or compatibility wrapper is allowed.

## Existing positive source facts

Production constructors do not automatically select a candidate. Explicit candidate
path/role/blocked state, false/spec/policy digest rejection, single command builder,
legacy runner deletion and ordinary to_thread/semaphore are present. These do not close
the defects above or provide real isolation, native parity, coverage or CVE acceptance.

## Next bounded work

Keep the frozen contract and saved amendments. Luna receives this one consolidated
review at the current coherent checkpoint boundary. Required negative regressions must
prove no execution on invalid identity, no false attestation, no score on infrastructure
failure, stable public mapping and cancellation cleanup. Save source before grouped
unit/strict-mypy/Ruff validation, then Sol reviews the fixed correction. Do not promote
the defective draft to an actual sandbox job. Keep all failed/unrun gates and the prior
uv/Ninja histories explicit; do not reset counts by changing interval or owner.
