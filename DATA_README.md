# Cloudpaw Renewal Agent: project data pack

> **All data is fictional.** Cloudpaw Inc., Products A–J, every price, policy, program, customer and person were invented for a course project.

A Renewal Agent for account executives (AEs). Name a customer and it reads the account's health and per-product consumption, checks Cloudpaw's renewal, ACV, attrition, commission and promotion rules for that customer's region, and writes a cited renewal strategy.

**Pattern 1 RAG** (hybrid search + OU metadata filter + re-rank + refusal), with a simple **account lookup** that feeds the filter.

## One-liner
> My Renewal Agent helps AEs build a renewal strategy for any of 60 accounts across AMER, EMEA, South Asia, LATAM and ANZ, from account health and 12 months of per-product consumption plus 29 renewal, ACV, attrition, commission and promotion documents, in a chat interface, with ≥90% faithfulness and a brief in under 10 seconds.

## What's inside
```
data/                      ← the database (lookup only, one account at a time)
  accounts.csv               60 accounts, 12 per OU
  ae_roster.csv              15 AEs, 3 per OU, with quota and attainment
  contract_lines.csv         167 lines: which products each account owns (1–4 each)
  consumption_monthly.csv    2,004 rows: per account, per product, per month (Nov 2025 – Oct 2026)
  cloudpaw_renewal_data.xlsx the same four tables as tabs (use with a Google Sheets node in n8n)
docs/                      ← the knowledge base (the RAG part)
  global/      9 docs        renewal, ACV, attrition, approvals, catalog, comp plan, health playbook, strategy playbook, glossary
  amer/ emea/ south-asia/ latam/ anz/   4 docs each: renewal addendum, promotions, SPIFFs & quota programs, consumption benchmark
  metadata_index.csv         one row per doc
eval/
  golden_set.csv             25 test questions with expected answers (computed from the data) and blank scoring columns
scripts/                   ← how the data was generated (reproducible, seed = 27)
```
"Today" in the data is **October 17, 2026**. FY27 runs Feb 1, 2026 – Jan 31, 2027.

## The 10 products
| Code | Product | Billed by | Utilization | Per-user signal |
|---|---|---|---|---|
| A | Sales CRM | seats | active users ÷ seats | opportunities updated per user |
| B | Service Desk | seats | active agents ÷ seats | cases closed per agent |
| C | Analytics & BI | seats | active users ÷ seats | dashboard views per user |
| D | Team Chat | seats | active users ÷ seats | messages per user |
| E | Customer Data Platform | credits | used ÷ monthly commitment | credits per user |
| F | AI Agents | credits | used ÷ monthly commitment | credits per user |
| G | Marketing Automation | million messages | used ÷ monthly commitment | messages per user |
| H | Commerce | GMV | used ÷ monthly commitment | GMV per user |
| I | Customer Portal | member logins | used ÷ monthly commitment | logins per admin |
| J | Integration Platform | million API calls | used ÷ monthly commitment | calls per owner |

Seat products can't exceed 100%. Consumption products can (overage).

## Data dictionary (key columns)
**accounts:** account_id, account_name, ou, country, segment (SMB/Commercial/Enterprise/Strategic), employees, industry, nature_of_business, owner_ae_id, contract_start, contract_end, term_months, current_acv_usd, auto_renew, products_owned, health_score, health_band, exec_sponsor_changed, open_p1_cases, dpa_version (EMEA), gstin_on_file (India)
**contract_lines:** line_id, account_id, product_code, pricing_model, licensed_qty, licensed_unit, list/net price per unit per year, discount_pct, line_acv_usd
**consumption_monthly:** line_id, account_id, product_code, month, active_users, entitlement_qty, consumed_qty, consumed_unit, utilization_pct, per_user_rate, per_user_unit
**ae_roster:** ae_id, ae_name, ou, segment_focus, fy27_quota_usd, attainment_ytd_pct

`health_score` follows the formula in GLB-HEALTH-007 exactly, so the agent can explain any score.

## Demo accounts (built-in scenarios)
| Account | OU | What makes it interesting |
|---|---|---|
| **Helvetia Logistics AG** | EMEA | DACH notice date already passed · old DPA blocks booking · E in overage · F shelfware · exec sponsor changed |
| **Andes Retail Group** | LATAM | Red health · Save Desk · Logo Retention SPIFF · Commerce Fiesta promo · no Renew Early in LATAM |
| **Summit Ridge Software** | AMER | Product E overage → true-up math, commission with 1.5x accelerator, True-Up SPIFF |
| **Prairie Fresh Grocers** | AMER | Product G shelfware → right-sizing rules and attrition quota impact |
| **Harbor City Transit Authority** | AMER | US Public Sector: 3% uplift cap, 120-day notice |
| **Saffron Retail Pvt Ltd** | South Asia | GSTIN missing blocks booking |
| **Canberra Digital Services Agency** | ANZ | Strategic → Quota Booster 120%; government data residency |
| **São Paulo Saúde** | LATAM | Renews Oct 31, 2026 (14 days); notice already passed |
| **Thames Valley Building Society / Kiwi Harbour Bank** | EMEA / ANZ | Promotion eligibility checks |

## Filled-in project framework
| Field | Decision |
|---|---|
| **Use case** | AEs ask for a renewal strategy or a specific renewal question about a named account, in a chat UI. |
| **Corpus** | 29 markdown docs (9 global + 4 per OU) owned by Global Renewals & Deal Desk, plus 4 lookup tables. English. |
| **Ingestion + cleaning** | Parse YAML front matter into metadata; drop the front matter and the fictional-data banner from chunk text. Tables load as CSV or a Google Sheet. |
| **Ingestion + freshness** | Policies re-indexed when changed; benchmark docs monthly; consumption table monthly. Docs carry effective dates, and expired promotions are filtered or flagged. |
| **Chunking + embedding** | Split on markdown headings (one rule or promo per chunk) with an 800 / 100 recursive fallback. Prepend "OU · doc title · heading" to each chunk. `text-embedding-3-small`. |
| **Retrieve** | Hybrid dense + BM25 with RRF; filter `ou IN (<account OU>, GLOBAL)`; 6 topic queries per brief (renewal rules, ACV, attrition, comp, promotions, benchmark); top-20 → re-rank → top-5 per topic. |
| **Generate** | GPT-4.1-mini or a Nebius model, using the brief template below. Cite doc_id for every rule. Show the math. |
| **"I don't know" path** | Unknown account → "I can't find that account. Please check the name." Rule not in that OU's docs → say so; never borrow another OU's rule. |
| **Success metrics** | Faithfulness ≥90% · right account 100% · right OU docs 100% · correct refusals 2/2 · latency <10 s. |

## Pipeline
```
OFFLINE  docs/*.md → front matter → chunk by heading → embed → vector DB (+ BM25)
         data/*.csv → load as tables
ONLINE   1 extract account name + intent (structured output)
         2 look up account, AE, contract lines, 12 months of consumption   ← tables
         3 compute in code: days to renewal, notice date, utilization & trend per product, per-user rate
         4 filter docs: ou IN (account OU, GLOBAL)
         5 hybrid retrieve per topic → re-rank
         6 generate the renewal brief (template, citations, math, warnings first)
```

## Renewal brief template (ask the LLM to follow it)
1. **Blockers and deadlines:** notice date, legal items, approvals
2. **Account snapshot:** ACV, contract end, segment, AE attainment
3. **Health and consumption:** per product: utilization, trend, per-user rate → shelfware, expansion-ready, overage
4. **Policy guardrails:** uplift cap, approval limits, attrition rules
5. **Opportunities:** true-ups, expansions, cross-sells (from the regional benchmark), eligible promotions
6. **Scenarios A/B/C:** ACV, commission, quota retired, SPIFFs, approvals needed
7. **Recommendation and next 3 actions**

## Starter system prompt
```
You are the Cloudpaw Renewal Agent. You help account executives plan renewals.
Today is {today}. You receive ACCOUNT DATA (from tables) and CONTEXT (policy documents).

Rules:
1. Use ONLY the account data and the documents in <context>. Cite the doc_id for every rule, e.g. [EMEA-REN-201].
2. The account's regional (OU) documents override GLOBAL documents when they conflict.
3. Never offer a promotion outside its valid dates or eligibility. Say why it doesn't apply.
4. Put blockers first: missed notice dates, legal requirements, required approvals.
5. Show the math for ACV, commission and quota. Apply the AE's accelerator if attainment is above 100%.
6. If the account isn't in the data, say "I can't find that account." If a rule isn't in the
   documents for this OU, say so. Never borrow a rule from another OU.
```

## How to score
Run each question in `eval/golden_set.csv` and fill in: found_right_account, retrieved_right_doc, answer_correct, faithful, cited, latency_s, notes.
Strong demo chart: run it **with and without** the OU filter and compare accuracy.

## Week 3 extension (not part of this project)
Turn the fixed pipeline into an agent with tools: a SQL tool for cross-region comparisons (by product, segment, industry, size), a portfolio tool ("rank all my renewals by risk") and CRM write-back.
