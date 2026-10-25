# Sprint 1 — Schema design and SQL proof of concept

## Goal and current state

Prepare a justified Bronze/Silver/Gold design and tested transformation queries for
an agreed one-week prototype. The final system must support the mobility questions,
territorial levels, and 2023 reference year described in the course brief.

Environment setup and smoke checks are available. The actual analytical schema,
source integration, transformations, and assessed prototype are **not implemented**.
A successful environment check is not completion of this sprint. Confirm any review
date or submission instructions against the lecturer's current announcements.

## Work board

Every owner starts **Unassigned**. Assign people together; the suggested workstream
is a coordination aid, not an assumption about anyone's skills or responsibilities.

| ID | Task / suggested workstream | Depends on | Owner | Status | Acceptance evidence |
|---|---|---|---|---|---|
| S1-01 | Extract requirements and acceptance criteria / shared | — | Unassigned | Pending | Requirements mapped to source material, all three layers and final use cases; distinguish sprint and final deliverables |
| S1-02 | Read methodology and inventory sources / sources + documentation | S1-01 | Unassigned | Pending | Source sheets with links, versions, real periods, units, categories, censoring, territorial levels and known limitations |
| S1-03 | Agree the prototype week and source alignment / shared | S1-02 | Unassigned | Pending | Recorded decision on inconsistent sample dates, missing district days, INE reference periods, geometries and crosswalk availability |
| S1-04 | Propose and review the data model / model + documentation | S1-03 | Unassigned | Pending | Diagram of Bronze/Silver/Gold, table sheets with grain, measures, keys, joins, lineage and partitioning rationale |
| S1-05 | Agree transformation and quality contracts / shared | S1-04 | Unassigned | Pending | Column types, code mapping, units, censoring/null rules, duplicate policy, join cardinalities and validation tolerances explicitly reviewed |
| S1-06 | Implement the reproducible SQL prototype / code | S1-05 | Unassigned | Pending | Versioned SQL and a documented command producing Bronze → Silver → Gold for the agreed sample; configurable paths |
| S1-07 | Validate and reconcile outputs / code + review | S1-06 | Unassigned | Pending | Coverage, keys, nulls, duplicates, join multiplication and aggregate reconciliation checked against agreed contracts |
| S1-08 | Prepare the lecturer review / shared | S1-07 | Unassigned | Pending | Clean-run instructions, sample results, completed diagram/table sheets, limitations, decisions and questions for feedback |

## Collaboration and handoffs

1. Assign owners and reviewers in the work board; keep statuses factual.
2. Use the [source inventory template](../templates/source-inventory.md) for S1-02.
   Mark methodology interpretations as proposals until supported by evidence.
3. Record the S1-03 decision with the [design decision template](../templates/design-decision.md).
   GAU for 9–15 March 2022 is available for initial exploration, not automatically
   accepted as the final integrated prototype. Missing districts, municipalities from
   another month, and quality files from another year require explicit treatment.
4. Draft one [table sheet](../templates/table-sheet.md) per proposed table for S1-04.
   Agree what a row represents before choosing keys or writing aggregations.
5. At S1-05, review model and transformation contracts together. Code implementation
   starts from reviewed contracts. Documentation, diagrams, and code can then progress
   in parallel. A change in grain, keys, or measures reopens the relevant decision.
6. Keep completed artifacts under this sprint directory: `sources/`, `model/`, and
   `decisions/` as they are authored. Create those directories only when adding real
   content. Maintain one current diagram and current table sheets, rather than copying
   independent versions for each teammate.

A contract must identify source/target columns, row grain, keys, territorial and
reference-year alignment, measures and units, null/censoring handling, duplicate
policy, join cardinality, validation checks and their acceptance tolerances. An
unresolved assumption must remain visible and block affected code, not become an
undocumented default.

## Code work after design approval

S1-06 will add the actual SQL transformations and a command-line entry point using
the existing data configuration. Reusable Python belongs in `src/mobility_lakehouse/`
when needed; transformation SQL belongs in `sql/bronze/`, `sql/silver/`, and
`sql/gold/`. Those components do not exist yet. Keep large processing inside DuckDB
rather than loading the entire week into Pandas. The notebook explains exploration;
it must not become the only way to reproduce the submitted transformation pipeline.

S1-07 must verify the agreed week and level, preservation of original identifiers
and lineage, declared grain/uniqueness, casts and rejected values, censoring policy,
join coverage/cardinality, and reconciliation of trip totals through aggregations.
Store counts and validation evidence with the reviewed outputs. Do not invent
zero values for censored counts or infer a territorial crosswalk from similar codes.

## Definition of done

- [ ] The agreed prototype scope and its relationship to final 2023 coverage are documented.
- [ ] Sources and their methodology have evidence-backed inventories.
- [ ] All three layers have a reviewed schema diagram and table sheets.
- [ ] Grain, keys, relationships, source mapping, and partitioning are justified.
- [ ] Nulls, censoring, duplicates, data types, and territorial alignment have reviewed rules.
- [ ] Tested SQL demonstrates Bronze → Silver and Silver → Gold over the agreed week.
- [ ] Coverage and aggregate reconciliation checks pass with documented tolerances.
- [ ] A teammate can reproduce the prototype from a clean checkout and configured data.
- [ ] README links, limitations, open questions, and review evidence are current and in English.
- [ ] Every teammate can explain the decisions and queries they present.

Airflow, AWS Batch, S3, and Neon/Postgres deployment belong to later sprints.
Do not mark these tasks complete merely because a synthetic environment fixture
uses schemas named Bronze, Silver, and Gold.
