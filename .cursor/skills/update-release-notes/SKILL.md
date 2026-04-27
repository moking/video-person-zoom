---
name: update-release-notes
description: Update feature.md and optimization.md after code changes. Use when implementing new features, changing user-visible behavior, or adding accuracy/performance/reliability optimizations in this repository.
---

# Update Release Notes

Update project change logs immediately after implementation changes.

## Targets

- Feature log: [`feature.md`](../../../feature.md)
- Optimization log: [`optimization.md`](../../../optimization.md)

## Classification Rules

1. Write to `feature.md` when change is user-visible capability or behavior:
   - New mode, new command path, new output behavior.
   - New CLI flag that enables a capability.
   - Semantics users depend on.
2. Write to `optimization.md` when change improves quality/performance without adding core capability:
   - False-positive/false-negative reduction.
   - Tracking robustness, drift guards, dedup logic.
   - CPU/GPU speedups, parallelization, batching, caching.
3. If a change is both feature and optimization, update both files in the same task.

## Entry Style

- English section first, Chinese section second.
- Append-only; do not rewrite unrelated historical entries.
- Keep entries concise and specific:
  - what changed
  - why
  - user impact / CLI impact
- Add cross-links between `feature.md` and `optimization.md` when related.

## Workflow

1. Review code diff scope.
2. Decide target file(s) using Classification Rules.
3. Update TOC if adding new numbered sections in `optimization.md`.
4. Append English entry, then Chinese mirror entry.
5. Check for duplicate entry titles in same date block.
6. Ensure new CLI flags are reflected in optimization CLI table if relevant.
7. In final response, state both files were updated.

## Dry-Run Examples

### Example A: New feature + optimization

- Change: add `--parallel-mode force` plus overlap dedup fix.
- Update:
  - `feature.md`: add feature entry for new user-facing parallel policy flag.
  - `optimization.md`: add optimization entry for dedup robustness.

### Example B: Optimization only

- Change: reduce orange field-line false positives in sock detection.
- Update:
  - `optimization.md` only (no new capability).

## Verification Checklist

- [ ] Correct target file(s) chosen.
- [ ] English then Chinese order preserved.
- [ ] Cross-links added/updated.
- [ ] No duplicate headings.
- [ ] CLI table updated when flags/defaults changed.
- [ ] Final summary mentions doc updates.
