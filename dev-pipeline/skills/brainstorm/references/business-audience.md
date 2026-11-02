# Business requirements for customers and downstream authors

Use one canonical Markdown document for both audiences. The rendered document
must make sense to a business customer without knowledge of the pipeline.
Downstream authors read the same file, including its non-rendered metadata.
This reference specializes brainstorm's presentation rules; it takes precedence
over fixed English headings, visible protocol annotations and prefix-only IDs
in the other brainstorm references. It does not change SRS or plan formats.

## Readable content

Use headings and field labels in the customer's language. Order sections around
the actual content: purpose, users, capabilities, data, scenarios, examples,
scope and material dependencies. Do not add empty sections to fill a template.
Goal Capsule and Product Contract name semantic content, not mandatory visible
headings. A separate Key Decisions section is unnecessary when it only repeats
requirements; keep the decision rationale next to its owning requirement.

Number requirements consistently and keep their original identities during
restructuring. A customer can read "requirement 11" without learning R11.
State what happens in ordinary words; explain unfamiliar domain terms briefly.
Write scenarios and acceptance examples as complete situations and outcomes,
rather than sequences of unexplained IDs or English field labels.
Use descriptive links to relevant questions. Do not put a list of codes on
every requirement just to expose traceability. A summary or example can explain
a rule, but has to retain a metadata link to its owning requirement.

## Stable metadata in the same document

Use non-rendered HTML comments, not a second editable specification. These are
semantic markers of the same kind as ce-section: work-relationships; they carry
no layout. Keep the source meaningful even when comments are ignored.

```markdown
<!-- ce-section: requirements -->
## Что должен делать помощник

| № | Требование |
|---|---|
| 11 <!-- ce-requirement: R11; open: OQ-7 --> | Предлагать рекомендации по управлению проектами. |

<!-- ce-flow: F3; covers: R11; open: OQ-7 -->
### Получить рекомендацию

Пользователь получает рекомендацию по результатам проверки.
```

Section roles include goal-capsule, summary, actors, requirements, key-decisions,
key-flows, acceptance-examples, scope-boundaries, dependencies-assumptions,
sources and the existing work-relationships role. Use only those that apply.
ce-actor carries an A-ID; ce-example carries an AE-ID and its covers links.
ce-decision carries its governed R-IDs, the existing session-settled class,
rejected alternative and rationale. Preserve these facts verbatim when moving
them from visible annotations. Never infer new settlement from a rewrite.

Readers discover semantic roles from comments first, and accept the previous
English headings and visible IDs in existing documents. Do not renumber or
silently drop an identity, a dependency or an unresolved decision. The Markdown
renderer already removes comments; no new rendering feature is implied.

## Questions for the customer

Keep unresolved questions in the adjacent open-questions.md. For long questions,
use one numbered block per question with its full wording, context, options and
any recommendation. Avoid a large table cell containing an entire interview.
Use one permanent customer number, not a question number plus a historical
interview-round number. Preserve the original OQ-ID, classification and source
in a comment, for example:

```markdown
<!-- ce-question: OQ-7; class: Отложено; source: discussion, YYYY-MM-DD -->
## Вопрос 7

**Нужны ли объяснение рекомендации и ссылки на исходные сведения?**

Варианты остаются предложениями до согласования с заказчиком.
```

The file must say which questions are unresolved and that recommendations are
not approved behavior. A link or short orientation in the main document is
enough; do not duplicate the question register there.

## Before finishing

Check the rendered document without relying on comments: headings, scenarios
and references should be understandable to the customer. Then check the source:
every previous requirement, actor, scenario, example, dependency and open
question still has its identity and meaning. Preserve all option wording and
the unapproved status of recommendations. Check links to question headings.
An editorial rewrite does not resolve questions or make a draft ready for SRS.
