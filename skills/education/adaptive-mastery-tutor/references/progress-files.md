# Learning Progress Files

Use progress files only with explicit user authorization to save, update, list, or delete them. A request to continue or resume authorizes reading a matching file.

## Location

Store one current-state file per topic at:

```text
~/.codex/learning-progress/<topic-slug>.md
```

Use a short lowercase ASCII slug. If two goals share a topic, add the goal, for example `english-business-email.md`. Do not place learner state inside the skill directory or a project repository unless the user explicitly chooses that location.

## File Format

Use YAML frontmatter for routing fields and Markdown for readable state:

```markdown
---
schema_version: 1
topic: Redis
goal: Design practical caching and session storage
current_stage: Storage foundations
current_concept: RAM and disk
updated_at: 2026-07-15T15:00:00+09:00
---

## Mastered

- Role of a database — explained accurately and classified two examples

## Partially understood

- Persistence — understands data survival but not failure modes

## Weak points

- Confuses access frequency with the need for durable records

## Prerequisites missing

- None currently observed

## Review queue

- Compare RAM and disk using a new scenario
- Decide between Redis and PostgreSQL for a payment record

## Examples that worked

- Desk versus archive-room analogy, with the durability limitation stated

## Learning preferences

- Short explanations followed by two open questions

## Next step

- Key-value representation
```

## Save and Update Rules

- Create or update a file only after requests such as “학습 진행 저장해줘”.
- If the user asks for a summary but not a file, show the same information in the conversation without writing.
- Store the latest state, not a transcript. Preserve still-relevant weak points and review items; remove an item only after evidence of stable understanding.
- Avoid sensitive personal information that is unnecessary for learning continuity.
- Before overwriting a file whose topic or goal conflicts with the current session, ask whether to update it or create a separate goal-specific file.

## Resume Rules

When the user asks to continue:

1. Use an explicitly provided path when available.
2. Otherwise look for an exact topic-slug match.
3. If several plausible files exist, show the filenames and ask which one; do not merge them silently.
4. Briefly restate the saved goal, current stage, and next step.
5. Start with one varied review question from the queue before introducing new material, unless the user asks to skip review.
6. Treat the saved file as evidence, not unquestionable truth; update the state when the learner demonstrates a different level.
