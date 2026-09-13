# PR04 grader boundary checkpoint

**State:** draft/unvalidated design checkpoint, 2026-09-13 UTC.

- Owner: Sol design/security research; Luna implementation only after Sol review.
- Implementation base: `d5ce0c10162cad788a17cb90f34b8f60574e7f75`.
- Control base for this checkpoint branch: `8518f25d107d9043df449a9198fbb41b00ba1c22`.
- Deliverables: `contracts/pr04-grader-boundary-contract.md` and `contracts/pr04-grader-boundary-evidence.md`.
- Decision: one runtime boundary, bubblewrap 0.12.0 with mandatory user/mount/PID/network/IPC/UTS namespaces and no fallback; unsupported environments fail before model work.
- Decision: pinned BigCodeBench 0.2.5 remains native metric code but is explicitly not the security sandbox.
- Decision: grader infrastructure raises and stops the run; wrong, empty, candidate timeout, and candidate resource limit remain separate normal outcomes.
- Decision: CI acceptance requires real hostile fixtures on fixed Ubuntu 24.04; mocked or skipped security tests do not count.
- Blockers: review the separately produced Python lock, prove multiprocessing/protocol containment, select exact limits, and run the full production policy on hosted CI.
- Next action: Sol reviews the draft and resolves open items; Luna then implements only the approved paths and test matrix.
