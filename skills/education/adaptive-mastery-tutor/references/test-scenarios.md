# Behavioral Test Scenarios

Use these as forward-test fixtures. Judge behavior against the assertions, not exact wording.

## Test 1: Complete Beginner and Prerequisites

**User:** “Redis가 뭔지 하나도 몰라. 완전 처음부터 가르쳐줘.”

**Expected first response:**

- Briefly identify the goal or make a stated beginner assumption.
- Show a compact map including data, memory/storage, server/database, key-value, and Redis where relevant.
- Start with only the first missing prerequisite, not Redis commands or all data structures.
- Ask 1–3 questions and wait.

**Failure:** Dumps the entire Redis curriculum, teaches several data types, or continues without a learner response.

## Test 2: Correct Conclusion, Wrong Reason

**User:** “결제 내역은 PostgreSQL에 넣어요. 자주 조회하지 않으니까요.”

**Expected response:**

- Preserve the correct PostgreSQL choice.
- Identify access frequency as the wrong central reason.
- Explain durability, correctness, transaction consistency, settlement, and evidence at the appropriate level.
- Give a counterexample such as a frequently read payment record that still belongs in durable storage.
- Ask one focused recheck.

**Failure:** Marks the whole answer wrong or accepts the reason without correction.

## Test 3: Short and Incomplete Answer

**Context:** The tutor used a folder analogy for key-value lookup.

**User:** “B 폴더처럼 보여서.”

**Expected response:**

- Infer that the learner sees a labeled grouping or lookup analogy.
- Confirm that useful intuition.
- State that the structure is not necessarily a literal operating-system folder.
- Continue or recheck without demanding a formal sentence.

**Failure:** Calls the answer meaningless, asks the learner to rewrite it formally, or claims full understanding without checking the distinction.

## Test 4: Memorized Definition

**User:** “Redis는 RAM 기반 Key-Value 데이터베이스입니다.”

**Expected response:**

- Acknowledge the definition as accurate.
- Mark understanding as not yet verified.
- Ask for a plain-language explanation, case classification, consequence prediction, or comparison.
- Do not reteach all beginner material unless the answer reveals a missing prerequisite.

**Failure:** Declares mastery from the definition alone.

## Test 5: Advanced Learner

**User:** “Redis 자료구조는 아는데 분산 락과 캐시 일관성이 약해.”

**Expected response:**

- Skip beginner explanations of databases and basic Redis data types.
- Map the focused route through lock safety, lease/TTL failure modes, ownership-safe release, fencing tokens, and cache invalidation/consistency as appropriate.
- Diagnose the first weak concept with an advanced scenario or prediction question.
- Still teach one core concept at a time.

**Failure:** Restarts at strings and hashes or lectures on all advanced topics in one turn.

## Test 6: Invocation Boundary

**User A:** “Redis가 뭐야? 두 문장으로 알려줘.”

**Expected:** Do not force the mastery loop; provide the requested brief explanation.

**User B:** “Redis를 완전 처음부터 문제 내면서 가르쳐줘.”

**Expected:** Invoke the adaptive mastery workflow automatically.

**Failure:** Turns every one-off explanation into a course or fails to recognize explicit learning intent.

## Test 7: Save and Resume

**User A:** “오늘 학습 진행을 저장해줘.”

**Expected:** Create or update one topic progress file containing current state rather than a transcript.

**Later user:** “Redis 학습 이어서 하자.”

**Expected:** Read the unique matching progress file, restate the checkpoint briefly, and begin with one varied review item unless review is declined.

**Failure:** Writes progress without authorization, edits `SKILL.md`, silently merges multiple goals, or treats the saved state as proof of present mastery.
