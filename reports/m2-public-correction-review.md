<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# PR04 first public correction: not closed

Sol reviewed fixed `0d4a4b1ebf4e5b82152fc69fa35afd0c0f969d6f` against original
draft `fe23c09bedf07d51ec320373fd89f502428dff16`. The same public source remains
in `7282be1a149c7352b91fd3df1a3b9f712ef9d1b5`; subsequent changes are only the
installer capability correction, preparation fixtures, baseline and work records.
Astra rejects this first corrective public batch based on the following source findings
and failed related diagnostics. It is not promoted or executed as a real boundary.

## Consolidated source defects and required regressions

1. **Normal public Path rejected (P1).** evaluator:69 uses `type(resource_dir) is not
   Path`, rejecting ordinary PosixPath values on Linux/macOS. Reproduce a legitimate
   Path request reaching the shared sandbox exactly once, then correct the path test.
2. **Probe cleanup crashes (P1).** host:1817–1897 calls shutil.rmtree at 1831/1897
   without importing shutil. Cover successful setup, setup failure and cleanup failure
   with stable secret-free infrastructure results, not NameError.
3. **Real probe contradicts its builder (P1).** host:1686–1689 reads /etc/os-release
   which the frozen builder does not mount; 1679/1704 can count the enumeration FD
   itself as leaked; 1953–1959 rejects the expressly permitted writable /dev/pts.
   Do not expand the frozen host mounts to fix the first problem: verify the actual
   Ubuntu host identity in preflight, and keep child facts consistent with its synthetic
   filesystem. Check which enumerated FDs remain open; do not blindly ignore extra FDs.
4. **Probe lifecycle and facts incomplete (P1).** host:1724–1807 does not cap stderr,
   continuously sample process count/aggregate RSS, or clean up failures before its try
   block. Nonzero exit can skip descendant cleanup; errors restart the full probe timeout
   instead of preserving the teardown deadline. Reuse the already closed bounded host
   lifecycle semantics. Add negative regressions for pipe-held descendants, stderr
   pressure, selector/fileno failure, nonzero exit, observation failure, resource pressure
   and final cleanup. Full real facts still need private proc, exact/size mount set,
   non-loopback listener when available, required write targets and component-safe exact
   sys.path checks (1939–1943 currently uses unsafe string prefixes). Keep the existing
   namespace/rlimit/secret/sentinel/listener/offline-NLTK requirements; unit facts are
   never real sandbox acceptance.
5. **Preflight executes stale identities (P1).** hashes at 2101–2125 precede flock at
   2126; subsequent host metadata/version/probe executes without an under-lock rehash.
   Reproduce mutation while lock acquisition waits and prove no process starts. All
   executable identities must be checked under the lock before execution, not merely
   grade-time rechecked. Grade-time lock/rehash itself has improved.
6. **Prepared path/role connection broken (P1).** resolver:2054–2068 adopts runtime
   bwrap/venv values instead of comparing every field to the fixed derived layout.
   Runtime checks:1207–1215/1270–1272 hardcode candidate role/path and cannot validate
   a future accepted runtime. Explicit candidate CI lacks SETUP_ROOT_ENV yet loader
   requires it. Production None must mean accepted only; explicit trusted candidate
   resolves the fixed sibling prepared runtime with no source-local shadow or redirect.
   Cover every field redirect, missing runtime, production/candidate mismatch and both
   valid role paths without creating an actual accepted manifest while audit is blocked.
7. **Preparation metadata and dependency check missing (P1).** locator:251–290 lacks
   securely created install-root/child owner and mode checks, and runtime-manifest owner/
   0444 checks. Distinguish the trusted setup parent from installer-created children;
   match the frozen creation contract rather than inventing metadata for unrelated host
   ancestors. Cover writable/swapped/foreign-owner metadata. Frozen preflight item 1
   requires a fresh bounded, read-only uv pip check; installer-time success is not a
   substitute. A fixed verified tool location is being clarified separately; do not
   invoke arbitrary PATH/manifest-selected executables before identity validation.
8. **External getcap remains in host (P1).** host:2024–2036 uses unqualified getcap
   and buffered subprocess.run. Apply the separately reviewed strict ENODATA-only xattr
   rule here too, with every other result failing and no leaked exception/path text.
9. **Actual workspace can intersect trusted mounts (P1).** evaluator:170–172 binds
   only run_dir; 199–202 checks workspace only against resource_dir. Bind planned roots
   and verify actual executor workspace against all selected venv/base/runner/vendor/data
   mounts, including workspaces below a distinct runtime_root. Test planned missing root,
   changed root and all intersections; keep central runner unchanged.
10. **Outcome/provenance omissions (P2).** host:2083–2091 lacks independent grader
    dependency-lock digest. App empty/no-code:131–147 omits grader/dataset provenance;
    evaluator:243–253 sets grader_invoked=True even on no_code_block. Test all native
    statuses, no-call outcomes and durable independent identities through both callers.
11. **Public request identity/errors (P2).** evaluator allows missing metadata task_id
    and substitutes literal BigCodeBench, losing request identity. App:197–204 leaks
    ProtocolError on oversize/NUL request construction. Validate exact strings/identifier
    correspondence and normalize protocol failures to GraderInfrastructureError; preserve
    the frozen distinction between NUL identifiers and permissible code/test contents.
12. **Explicit accepted path still allowed (P2).** host:1114–1121 accepts explicit
    grader-manifest.json. None alone selects accepted. Production limits are now checked,
    but role/path negative regressions and exact candidate-only explicit selection remain.
13. **Legacy registry fallback (P2).** registry:130–135 still uses source resources
    when root is explicitly passed, and its test enshrines this route. BCB always uses
    the single trusted prepared locator; preserve other evaluators' root behavior. Entire
    old setup/wrapper/config deletion is otherwise source-closed.
14. **Missing closure regressions.** Startup failure now stops app construction and
    normal single cancellation waits for the worker while holding the semaphore, but
    neither has a failure/cancellation regression. Add them, plus all missing identity,
    lock drift, redirect, role, workspace and public-input regressions. Mocked caller/
    metadata unit tests establish orchestration only, not real isolation.

## Independent safe deltas

- Installer `833df6b9` uses quoted verified harness Python -I -B and exact-path
  non-following xattr inspection. ENODATA alone succeeds; empty/nonempty attributes,
  other errno and exceptions fail with a fixed outer diagnostic. Existing binary
  metadata/ELF checks remain, Meson is verbose, and no test is disabled. Sol closes this
  source independently. Corrected fixtures at `240d5d37` pass all 17 preparation methods,
  but test:372 still needs narrowing of SystemExit.code for strict typing. Real Linux
  retry is pending; metadata mocks do not prove actual file-capability/sandbox behavior.
- Baseline `7282be1a` preserves version/settings/old two entries and adds exactly 62
  classified public digest fingerprints on the five approved paths. Sol finds no source
  relaxation. Targeted hook passes and an unrelated private negative control is detected.
  Full tracked hook finds two pre-existing ALPS config digest fingerprints outside the
  previous five paths; these need finite classification, not blanket exclusion.

## Correction accounting and next batch

This is the first failed correction of the fe23 public source review, not a reset of
earlier host/codec/preparation histories. The original two uv corrective failures remain
recorded and that issue is closed. Ninja closed after one correction. Getcap had one
initial actual Linux failure; its first source correction is reviewed but real retry
has not run. The two preparation fixture errors were corrected once and now pass.

Next Luna first writes concrete reproductions for the above defects, then performs one
consolidated second public correction with full related unit/strict/Ruff validation.
Save before long validation and within 15 minutes. If the same issue fails again, retire
that approach, preserve the count, analyze the cause and state a revised, testable approach
before the user-authorized extra attempt. If that fails, hold the issue and dependent
acceptance while continuing independent in-plan work. No routine user confirmation is
needed, and no unaccepted public source or candidate environment becomes acceptance.
