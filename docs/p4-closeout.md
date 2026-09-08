# P4 closeout and preservation

As of 2026-09-09, the P4 batch/comparison implementation and closed-study evidence are locally
verified. The actual experiment completed 72 Trials and 72 Attempts with no retries. This
closes the local engineering work; public package/evidence release remains separately open.
Positive Agent improvement is the next P4.5 milestone, not an outcome of this study.

## What the study establishes

| Outcome | Count |
| --- | ---: |
| pass | 18 |
| behavioral_fail | 33 |
| evaluation_invalid | 0 |
| infrastructure_unavailable | 21 |

Held-out reliable success was baseline 8/9 and candidate 1/9, a delta of -7/9 with the
reported 95% interval [-1, -2/3]. The comparison concluded `regressed`. Hard guardrails
remain uncertain or unavailable and do not support promotion. These results concern the
frozen study only; 72 completed Trials do not mean 72 successful Agent tasks.

The original design specified nine Cases and 54 Trials. The actual study completed 72 Trials;
keep that design as history and the closed evidence as the authority for what ran.

## Preserved historical authority

The private local archive `p4-72-trials-2026-09-09` retains source snapshots, complete Git
history bundles, exact project wheels, closed custody, materialization, revealed cases, image
authority, an offline dependency snapshot and `reproduce.py`. A SHA-256 inventory binds them.

- Historical Core revision: `7b46258457142cfd32bc8c7ea46bc21740b475de`.
- Historical Companion revision: `5790ff6379bae80818602b2e1ca0dea29c2eaf72`.
- Closed artifact: `0119b96a7ff267b188c450ae01fb861a258b09016e27039840769f543580f9ae`.
- Core 0.1.4 wheel SHA-256:
  `4ef10a5eb2f9961943883576ab81bc97ce32d2f3f8a88cb9679d5c51c81e368d`.
- Companion 0.4.2 wheel SHA-256:
  `6b8acee8b58017597d13931b5427f795e6981287ea4da877ca81ae7c79f3316b`.

Two isolated historical-wheel reconstructions, with socket creation disabled, reproduced all
702 evidence files byte-for-byte. Newly built wheels must never replace these historical
ImplementationLock bytes, even if an unreleased display version has not changed.

The separate `p4-cleanup-round2-2026-09-09` archive preserves before/after cleanup snapshots,
file hashes, tests and reconstruction results. Both archive inventories were rechecked at
closeout: 1,953 and 19 indexed files respectively matched. Archives remain private local
preservation, not an off-device backup or third-party downloadable evidence release.

## Cleanup and verification

| Scope | Change | Existing verification |
| --- | --- | --- |
| Companion first cleanup | Retire Pilot, diagnostic and parallel M4 runners | All 579 remaining tests passed across the full run and permission-corrected rerun. |
| Companion second cleanup | Retire unused producers/types; retain specification construction; move fixture generators to test support | 547 tests passed; 18 specification hashes/Experiment IDs unchanged; new Companion wheel reconstructed the same 702 files. |
| Core cleanup | Reuse closed-package publication; share completed-export example file operations | 240 tests passed; 243 output file hashes matched before/after and in an isolated new wheel. |

Core source decreased by 200 lines. Companion package source decreased from 24,437 to 17,452
lines; 410 lines of the second-round decrease moved into test support. Public Core contracts
remain unchanged. Ruff, formatting, applicable source typing and wheel/sdist builds passed.
Companion full-tree mypy retains 23 pre-existing errors in three script-test files; source
and scripts passed. Unchanged tested code reuses that validation evidence.

## Remaining limits and next work

- The 72-Trial live loop used a temporary driver that was already missing when archiving began.
  Offline evidence reconstruction is verified; a fresh live rerun is not.
- The ordinary `study advance` CLI still uses its existing live executor; cleanup does not
  establish it as the complete driver for this controlled study.
- Companion cleanup lives on `codex/p4-controlled-study`; the separate main checkout has not
  received those changes. Local commits do not imply a merge, push or package release.
- Public P4 package/evidence release and its original third-party acceptance remain open.
  They are not prerequisites for beginning P4.5 with the preserved local implementation.
- Next, preserve real external-tool CLI replay cases and human reference judgments, establish a
  fixed downstream Agent baseline, and verify one targeted improvement on unused cases.
  Use a small calibrated helper Judge only when qualitative scoring requires it.

See the [roadmap](../ROADMAP.md) for P4.5 and the following thin Chora integration.
