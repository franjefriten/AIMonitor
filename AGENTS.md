# AI Agent Rules

These rules apply to the work of AI assistants in software projects.

## Collaboration principles

- The code belongs to the developer. The assistant should help understand, design, and improve the system without replacing the developer's work.
- Before editing, read the current implementation and form a concrete hypothesis about the bug or required change.
- Apply small, targeted patches to the existing implementation.
- Do not rewrite a function or subsystem from scratch when an incremental fix resolves the issue.
- Preserve existing design decisions, public names, contracts, and structure unless a change is truly necessary.
- If the solution requires a structural change or spans multiple layers, explain it before proceeding and break it into reviewable steps.
- Do not fix unrelated bugs without notifying the user first.
- If the user's implementation is incomplete but valid as an initial approach, improve it gradually instead of replacing it outright.
- Do not remove clarifying comments from the developer; keep them when patching and restore them if a change accidentally deletes them.

## Changes and validation

- Before editing, review recent user changes as well and avoid overwriting them.
- After each substantial patch, run the smallest relevant test or validation closest to the changed code.
- Keep tests aligned with the current contract, but do not hide incompatibilities by changing expectations without explanation.
- Report remaining risks, major changes, and any validation that could not be executed.
- Do not create commits or revert user changes unless explicitly requested.

## Health checks and recovery

- Keep responsibilities separate for updating snapshots, detecting/publishing transitions, and writing logs.
- Transition detection must compare the previous snapshot with the new one before overwriting it.
- Recovery should evolve through incremental patches to the existing flow; it should not be rewritten in full without warning and agreement on scope.
- A successful recovery must distinguish between `recover()` completing successfully and a later health check confirming the system is healthy again.
