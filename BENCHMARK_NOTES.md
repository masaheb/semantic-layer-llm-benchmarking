# bench-harness branch

This branch holds a modified copy of the benchmark harness
[dbt-labs/dbt-llm-sl-bench](https://github.com/dbt-labs/dbt-llm-sl-bench) (see LICENSE),
adapted to run against a Redshift-backed dbt Semantic Layer with Amazon Bedrock models.
It is unrelated to the dbt project on `main`; dbt Cloud only builds `main`.

- Run: `uv sync`, create `.env` from `.env.example`, then `uv run python run_dbt11.py <semantic_layer|sql> <iterations>`
- Changes vs upstream: Bedrock provider, acme_prod table qualification, SL column-case fix,
  DuckDB data_json type fix, Bedrock pricing, ACME_enhanced_redshift.ddl, run scripts.
- Not included: `.env` (secrets), result databases, Redshift credentials.

---

# dbt-llm-sl-bench on Redshift (Path A) — STATUS

## ✅ WORKING END TO END
The full benchmark pipeline runs:
LLM (Bedrock Claude) → generates dbt Semantic Layer query → executed against the
dbt SL (backed by Redshift) → compared to gold → scored.

Verified with a 1-question `semantic_layer` smoke test:
- Bedrock generated the correct SL query:
  `select * from {{ semantic_layer.query(metrics=['number_of_policies']) }}`
- SL returned 7 metrics; query executed; result scored.

## Infrastructure
- Redshift Serverless: dedicated public workgroup `dbt-sl-bench-wg` (ns `dbt-sl-bench-ns`),
  SG `sg-<redacted>` locked to dbt Cloud us1 IPs, least-priv user `dbt_cloud`.
- dbt Cloud: project on Fusion, fork `masaheb/semantic-layer-llm-benchmarking`,
  deployment env `sl-deploy` (id <redacted>), Semantic Layer enabled.
- 29 seeds + 30 models built; semantic models migrated to Fusion new-format;
  metricflow_time_spine registered.

## Harness changes (in dbt-llm-sl-bench)
- Added `bedrock:` model provider support (prompt_executor.py, validation.py, boto3 dep).
- Normalized SL result column names to upper case (database.py) — this SL cell
  returns lower-case columns; harness assumes upper-case.
- `.env`: SL_URL, ENVIRONMENT_ID=<your sl-deploy env id>, service token, AWS_REGION, no LLM key (Bedrock).

## Known calibration items (not blockers)
- Gold-vs-generated comparison: gold is plain SQL (`SELECT COUNT(*) AS NoOfPolicy
  FROM policy`) vs SL metric output (`NUMBER_OF_POLICIES`) — column/shape mismatch
  can score a correct answer as incorrect. Normal benchmark calibration.
- pricing.py has no Bedrock model pricing → cost shows 0/None (cosmetic).

## Fork fixes committed to main
- +schema seed config (Fusion), new-format semantic models, 3 bridge-table
  primary entities, time_spine.yml.

---

## UPDATE: first scored run + the fixes that got us there

### Gold-query resolution fix (the real root cause of "0 correct")
Gold SQL is UNqualified (`FROM claim`); the dbt SL SQL-passthrough resolves on
search_path `$user, public`, where the ACME tables don't live — they're in the
`acme_prod` schema. Fix: `qualify_gold_tables()` in `runners/benchmark.py` rewrites
known ACME table names in FROM/JOIN position to `acme_prod.<table>` (conservative:
columns & SPARQL bodies untouched, already-qualified names skipped). Verified
`FROM acme_prod.claim` returns rows through the SL. Schema overridable via GOLD_SCHEMA.

### DuckDB storage fix
The first (empty-result) run made DuckDB infer the `data_json` column as INT, so
later string payloads failed to cast → the writer raised → workers died → the run
stalled at 4/86. Fix: force `data_json` to VARCHAR in `storage/database.py`, and
start from a fresh `llm_bench.db` (old one saved as `llm_bench.db.poisoned.bak`).

### pricing.py
Added Bedrock Claude Haiku/Sonnet pricing entries so cost computes.

### FIRST SCORED RUN — semantic_layer, Claude Haiku (Bedrock), this ACME project
- 22 answers, **6 correct = 27.3%**.
- All 6 correct are clean single-metric questions (how many claims/policies, total
  loss amount). All 16 incorrect: the LLM GENERATED a query (gen_ok=True) but the
  execution/comparison errored — the harder multi-hop / ratio / premium-join
  questions the SL can't answer on the raw (un-remodeled) ACME schema.
- This matches dbt's own finding: the highly-normalized ACME schema needs ~3 extra
  dbt models before the SL covers every question. dbt's headline ~98-100% used the
  REMODELED project (refresh-2025-additional-models), and Sonnet 4.6 / GPT-5.3 Codex
  — not Haiku on the raw schema. SPARQL gold entries also can't run on Redshift.

### To move accuracy toward dbt's numbers (options, not yet done)
1. Add the `refresh-2025-additional-models` 3 models so the SL covers multi-hop Qs.
2. Restrict to the 11-question subset dbt actually used (TTL has 43, many extra).
3. Normalize the gold-vs-generated comparison (column-name/shape).
4. Use Sonnet instead of Haiku.

---

## UPDATE 2: remodeled project + Sonnet 5.5 + 11-question subset

### Changes
- Added dbt's 3 bridge models (claim_policy_bridge, policy_holder_policy,
  policy_premium_detail) from refresh-2025-additional-models, migrated to Fusion
  YAML, pushed to fork main; deploy job built 33 models. SL now exposes 10 metrics
  (adds average_policy_size, total_premium, total_policies).
- Switched to bedrock:us.anthropic.claude-sonnet-5-5.
- Scoped to an 11-question subset (run_sl_sonnet11.py).

### Bedrock concurrency gotcha
Running with parallel challenge workers (3) made Sonnet 5.5 return CANNOT_ANSWER
for every question (throttling/empty-response artifact). Running SEQUENTIALLY
(parallel_challenges=False) fixed it — a direct single call always produced a
valid query. Keep SL runs sequential on Bedrock.

### Result: 14/22 = 63.6% (up from 27.3% with Haiku on raw schema)
- 6 questions fully correct (claims, policies, policy counts, avg policy size,
  avg time to settle, total premiums by policy, total loss).
- 8 failures are ALL "Could not map all gold columns" on GROUPED questions
  (by policy holder id / agent id / policy number). The generated SL query is
  correct (right metric + group_by), but the gold SQL's grouping column
  (e.g. party_identifier / AGENTID) doesn't value-map 1:1 to the SL's semantic
  dimension output → the strict column mapper rejects it even though the numbers
  are right. This is a comparison-calibration gap, NOT an SL capability gap.

### Why dbt hits ~98-100% and we're at 63.6%
dbt's modeled project exposes dimensions whose output columns line up exactly with
the gold grouping columns, so the mapper matches. To close our gap we'd need the
SL dimension names/output to match the gold grouping columns (or relax the
comparison for grouped queries). The single-value questions already pass.

---

## UPDATE 3: verified the 8 grouped failures — honest finding

Pulled gold vs. generated for the failed grouped questions and ran both:

1. "premium amount of all policies by policy number"
   - GOLD returns RAW ROWS (5 premium lines for policy 31003000336: 15000,16000,
     17000,18000,20000).
   - SL returns the AGGREGATE (31003000336 -> 86000 = the sum). Numerically the SL
     is self-consistent, but the gold wants a row-level DETAIL LISTING, which a
     semantic layer fundamentally cannot produce (it aggregates). True coverage
     boundary, NOT a scoring bug.

2. "how many policies have agents sold by agent id"
   - GOLD filters party_role_code='AG' -> one row (agent 2, 2 policies).
   - SL query grouped by party + role and returned BOTH PH and AG rows, with the
     AG row's party id = None. The LLM picked the wrong dimension/filter — a real
     query difference, not just column naming.

### Corrected conclusion
The 8 failures are a MIX of (a) genuine SL coverage boundaries (gold expects
row-level detail the SL can't emit) and (b) the LLM choosing a slightly wrong
dimension/filter on multi-hop grouped questions. It is NOT purely a scoring
artifact as first thought. The 6 single-value / clean-aggregate questions pass
correctly and deterministically.

### So where does 63.6% sit vs dbt's 98-100%?
dbt reached ~98-100% by (1) curating the 11 questions to ones the modeled SL can
answer as AGGREGATES (not detail listings), and (2) aligning modeled dimensions to
the gold grouping columns so comparisons match. Our subset still included
detail-listing questions and some whose gold grouping doesn't align with the SL's
dimensions. The pipeline is faithful; the remaining gap is question-selection +
dimension/gold alignment, which is exactly the modeling/curation work dbt did.

---

## HEAD-TO-HEAD: text-to-SQL vs semantic layer (same 11 Qs, Sonnet 5.5, sequential)

| Method | Accuracy |
|---|---|
| Semantic Layer | 14/22 = 63.6% |
| Text-to-SQL (sql, ACME_small.ddl) | 12/22 = 54.5% |

Harness change for a fair text-to-SQL run: generated raw SQL is qualified to
acme_prod (same as gold) before executing via the SL SQL passthrough; SL/mcp
queries are NOT rewritten (benchmark.py _execute_and_compare_query).

### Key qualitative finding (the benchmark's whole point)
"How many claims do we have?" — a trivial question:
- Semantic Layer: iter0 correct, iter1 correct — IDENTICAL, deterministic.
- Text-to-SQL: iter0 incorrect (same SQL returned no data), iter1 correct —
  SAME query, DIFFERENT outcome across runs = text-to-SQL inconsistency.

Both methods fail the detail-listing gold questions (raw rows vs aggregate) — a
wash driven by gold shape, not method quality.

### Takeaway
On this Redshift+Bedrock reproduction, the semantic layer beat text-to-SQL
(63.6% vs 54.5%) on the same questions/model, and — more importantly — was
DETERMINISTIC where text-to-SQL was inconsistent. This mirrors dbt's thesis:
SL trades coverage for correctness+consistency; text-to-SQL attempts everything
but varies and can be subtly wrong. Absolute numbers are below dbt's 98-100%
because of question curation + gold-shape/dimension alignment (see Update 3),
not a difference in the methods' relative behavior.

---

## UPDATE 4: semantic layer reaches 100% on the 8 aggregate questions

Modeling fixes (guided by dbt-agent-skills `building-dbt-semantic-layer` best practices):
1. Unhid `policies_per_holder` / `policy_holder_count` and added labels (they were
   `hidden: true`, so the LLM could not select them).
2. Added `policies_by_party_role` (count distinct policies) on `agreement_party_role`,
   covering agents (AG) and holders (PH).
3. Set `agg_time_dimension: effective_date` on `agreement_party_role` (Fusion requires a
   primary time dimension for a model with metrics).
4. Renamed that model's party dimension `party_identifier_dim` -> `role_party_identifier`.
   The duplicate name collided with `policy_holder_policy` (holders only), so the agent id
   resolved through the wrong model and came back null.

Progression (semantic_layer, Sonnet 5.5 unless noted):
| Step | Accuracy |
|---|---|
| Raw schema, Haiku, all questions | 27.3% |
| + 3 bridge models, 11 questions | 63.6% |
| Scored on the 8 aggregate questions only | 75.0% |
| + visible/labeled metrics, policies_by_party_role, time dimension | 87.5% |
| + dimension rename | **100.0% (16/16)** |

Verified the agent question is a real pass: query groups by `policy__role_party_identifier`
with `party_role_code = 'AG'` and returns agent 2 -> 2 policies, matching gold exactly.

Scope note: the 3 "list the rows" questions are excluded because a semantic layer returns
aggregates, not row listings. The text-to-SQL figure (54.5%) was on the 11 questions with the
old DDL and is not yet a like-for-like comparison.

---

## UPDATE 5: dbt's exact 11 questions x 20 runs (Sonnet 5.5, Bedrock, sequential)

Question set taken from dbt's published `llm_bench_dashboard.db` (blog doesn't list them).
dbt used 20 runs only for its headline models; sweeps used 5. Script: `run_dbt11.py`.
Text-to-SQL used `ACME_enhanced_redshift.ddl` = dbt's enhanced DDL (includes the 3 bridge
tables) repointed from dbt's dev schema to `acme_prod`, matching dbt's "updated DDL" step.

| Method | Raw score | Notes |
|---|---|---|
| Semantic Layer | **220/220 = 100.0%** | every question 100% |
| Text-to-SQL | **180/220 = 81.8%** | ~90.5% excluding the settle-time gold artifact |
| dbt (Sonnet 4.6, modeled) | SL 98.2% / text-to-SQL 90.0% | for comparison |

Text-to-SQL failures:
1. "Policies agents sold by agent id": 0/20. LLM filtered `Party_Role_Code = 'Agent'`, but the
   data codes agents as `'AG'` -> empty result. Genuine semantic error; the SL has the role
   encoded in the model, so it can't make this mistake. This is dbt's core thesis.
2. "Average time to settle by policy": 1/20. Gold on Redshift returns 20 because Redshift AVG of
   an integer truncates; text-to-SQL cast to decimal and returned 20.5 (mathematically right).
   SL also returns 20 (same engine). Redshift dialect artifact in the gold, not a text-to-SQL
   error. Counting it correct gives text-to-SQL ~199/220 = 90.5%.
3. "How many claims": 19/20.

Consistency (comparing answer values, ignoring column aliases): SL 11/11 questions identical
across all 20 runs; text-to-SQL 9/11. Text-to-SQL wrote up to 10 distinct SQL variants per
question vs 1-4 for the SL.

Tokens: SL 3.90M in / 23K out (big prompt: full metric+dimension catalog); text-to-SQL 1.10M in
/ 50K out. Roughly $16 total at Sonnet 5.5 rates (pricing.py has no Sonnet 5.5 entry, so the
recorded cost column is 0).

Harness fix: run_dbt11.py ends with os._exit(0). Flight SQL/asyncio threads kept finished runs
alive, which stalled the chained run and left many "running" background processes.

---

## Cross-verification against dbt's own results (llm_bench_dashboard.db + repo history)

Every blog number reproduces exactly from dbt's database (11 questions):
| Run | dbt result | input tokens/call |
|---|---|---|
| GPT-4 (2023), SL / text-to-SQL | 60.5% / 32.7% | n/a |
| Sonnet 4.6, no extra models, SL / SQL (20x) | 72.7% / 64.5% | 9,293 / 2,108 |
| Sonnet 4.6, with models, SL / enhanced-DDL SQL (20x) | 98.2% / 90.0% | 13,683 / 3,647 |
| GPT-5.3 Codex, with models, SL / SQL (20x) | 100% / 84.1% | 8,720 / 2,802 |
| Claude Sonnet 5 (Aug 2026), with models, SL (5x) | 87.3-94.5% | 17,533 |
"Too many hops" split also matches (SL 100%/0%, SQL 62.5%/70% for Sonnet 4.6).

What dbt did vs what we did:
| Item | dbt | Us |
|---|---|---|
| Questions | 11 (in their DB) | same 11 |
| Iterations | 20 for headline models, 5 or 3 for sweeps | 20 |
| Strategies run | sql + semantic_layer only (no mcp rows) | same |
| Warehouse | Snowflake (branch commit "Convert datediff to snowflake dialect") | Redshift Serverless |
| dbt engine / spec | legacy semantic-model spec | Fusion 2.0.9, migrated with dbt-autofix |
| Modeling | 3 bridge models (refresh-2025-additional-models) | same 3 + 4 Fusion fixes (see below) |
| SL prompt | before commit 291782f (all headline runs ended by 2026-02-25 11:34 UTC) | after 291782f (adds single-query / CANNOT_ANSWER rule) |
| Text-to-SQL DDL | ACME_enhanced.ddl (their dev schema) | same, schema repointed to acme_prod |
| LLM access | OpenAI / Anthropic APIs | Bedrock (Sonnet 5.5) via added `bedrock:` provider |

Confirmed by dbt's data:
- dbt's text-to-SQL also scores 0% on the agent question, with the same mistake
  (`Party_Role_Code = 'Agent'` instead of 'AG').
- dbt's text-to-SQL scores 100% on settle-time; ours 5% because Redshift AVG(int) truncates the
  gold to 20 (Snowflake returns 20.5). Supports the "Redshift artifact" diagnosis.
- Token load is the same order: our ~17.7K/call matches dbt's Claude Sonnet 5 runs (17.5K).

Where we deviated (honest note):
dbt's SL answered the agent/holder questions with the existing `number_of_policies` metric grouped
by `policy__party_identifier_dim` + a role filter. Our extra changes (unhiding policies_per_holder,
adding policies_by_party_role, renaming the party dimension) compensate for a dbt-autofix/Fusion
migration side effect (a second `party_identifier_dim` made the name ambiguous); dbt didn't need
them. Our 100% = dbt's modeling + Fusion migration fixes, on Redshift, with a newer prompt.
