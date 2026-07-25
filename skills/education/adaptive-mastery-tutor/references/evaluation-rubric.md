# Evaluation and Correction Rubric

Use this rubric to diagnose evidence, not to manufacture a score.

## Assessment Dimensions

Evaluate only the dimensions relevant to the question:

| Dimension | Look for | Common false positive |
| --- | --- | --- |
| Conclusion | The selected answer, result, or action is correct | A lucky guess |
| Reason | The explanation identifies the actual causal reason | A plausible but irrelevant reason |
| Principle | The learner understands the mechanism or rule | Repeating a memorized definition |
| Scope | The learner knows when the rule does and does not apply | Treating a conditional rule as universal |
| Terminology | Terms are used with the right boundaries | Correct idea expressed with an overbroad term |
| Transfer | The learner can apply the idea to a changed situation | Repeating the original example |

## Diagnostic Labels

- **Mastered:** Gives accurate reasoning and succeeds on at least one comparison, prediction, example, or transfer task appropriate to the goal.
- **Sufficient to advance:** Understands the core principle without a blocking misconception; minor wording errors can be repaired while advancing.
- **Partially understood:** Contains a correct component but has a missing reason, boundary, or transfer ability.
- **Memorized but unverified:** States the accepted definition or procedure without evidence of meaning.
- **Misconception:** Uses a wrong causal model or rule that will generate wrong answers elsewhere.
- **Insufficient evidence:** The answer is too ambiguous to diagnose even after charitable interpretation.

Avoid presenting these labels as bureaucratic grades unless they help the learner.

## Evaluate Partial Answers

Use this order:

1. Name the part that is correct.
2. Identify the exact faulty or missing part.
3. Explain why it matters.
4. Give a more precise formulation.
5. Contrast it with a nearby case.
6. Ask one short recheck if the defect is important.

Example:

> “PostgreSQL을 선택한 결론은 맞습니다. 다만 ‘자주 조회하지 않아서’가 핵심 이유는 아닙니다. 결제 기록에는 영구 보존, 정확성, 거래 일관성, 정산·증빙 가능성이 필요합니다. 자주 조회하는 결제 기록도 PostgreSQL에 둘 수 있습니다. 그렇다면 조회 빈도가 높아지면 원본 결제 기록을 Redis로 옮겨도 될까요? 이유도 말해보세요.”

## Handle Memorized Definitions

When the learner says, “Redis는 RAM 기반 Key-Value 데이터베이스입니다”:

- acknowledge that the definition is accurate;
- do not mark mastery yet;
- ask for a plain-language explanation, case classification, consequence prediction, or comparison;
- check whether the learner understands RAM, persistence tradeoffs, and why key-value access matters at the depth required by the goal.

## Handle Short or Incomplete Replies

Infer conservatively:

> “`B 폴더처럼 보여서`라는 말은 값을 이름표별로 묶어 찾는 모습이 폴더와 비슷하다는 뜻으로 이해했습니다. 그 직관은 맞습니다. 다만 실제 운영체제 폴더라는 뜻은 아닙니다.”

If two interpretations are materially different, name both and ask one discriminating question. Do not demand a complete sentence merely for formality.

## Correct Misconceptions Efficiently

Do not restart the entire lesson. Target the broken link in the learner's mental model.

- **Wrong conclusion, sound earlier steps:** find the decision point where the reasoning diverged.
- **Correct conclusion, wrong reason:** use a counterexample where that reason predicts the wrong result.
- **Correct rule, wrong scope:** show one valid case and one exception.
- **Vocabulary error, correct idea:** repair the term without erasing the conceptual success.
- **Repeated error:** change the representation or example rather than repeating the same wording.

## Design High-Information Questions

Mix question types over time:

- explain in one's own words;
- compare two concepts;
- classify valid and invalid examples;
- find the error in a worked example;
- create an example or counterexample;
- predict an outcome;
- interpret code, a command, a formula, a sentence, or a document clause;
- apply the idea to the learner's real situation.

Avoid an all-multiple-choice sequence. When using multiple choice, ask for the reason or follow it with a transfer question.
