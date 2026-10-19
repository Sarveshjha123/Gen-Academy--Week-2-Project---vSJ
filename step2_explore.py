"""Step 2: look at the three kinds of information the agent will use.
Run:  python step2_explore.py
Each block shows the SQL you already know, then the same thing in pandas (Python's "Excel/SQL" library).
"""
from pathlib import Path

import pandas as pd

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 12)

# ------------------------------------------------------------------ 1. TABLES (structured data)
accounts = pd.read_csv("data/accounts.csv", keep_default_na=False)
lines = pd.read_csv("data/contract_lines.csv")
usage = pd.read_csv("data/consumption_monthly.csv")
print(f"TABLES: {len(accounts)} accounts, {len(lines)} contract lines, {len(usage)} monthly usage rows\n")

# SQL:    SELECT * FROM accounts WHERE account_name = 'Helvetia Logistics AG';
acc = accounts[accounts.account_name == "Helvetia Logistics AG"]
print("ONE ACCOUNT ROW:")
print(acc[["account_id", "ou", "country", "segment", "current_acv_usd", "contract_end", "health_score", "health_band", "dpa_version"]].to_string(index=False))

# SQL:    SELECT product_name, licensed_qty, licensed_unit, line_acv_usd FROM contract_lines WHERE account_id = 'ACC-013';
acc_id = acc.iloc[0].account_id
print("\nPRODUCTS IT OWNS:")
print(lines[lines.account_id == acc_id][["product_name", "licensed_qty", "licensed_unit", "line_acv_usd"]].to_string(index=False))

# SQL:    SELECT product_code, AVG(utilization_pct) FROM consumption_monthly
#         WHERE account_id = 'ACC-013' AND month >= '2026-08' GROUP BY product_code;
recent = usage[(usage.account_id == acc_id) & (usage.month >= "2026-08")]
print("\nAVERAGE % USED, LAST 3 MONTHS (over 100 = overage, under 50 = unused licences):")
print(recent.groupby("product_code").utilization_pct.mean().round(1).to_string())

# ------------------------------------------------------------------ 2. POLICY DOCUMENTS (for RAG)
docs = pd.read_csv("docs/metadata_index.csv")
print(f"\nPOLICY DOCUMENTS: {len(docs)}. How many per region (OU):")
print(docs.groupby("ou").doc_id.count().to_string())

# ------------------------------------------------------------------ 3. MEETING TRANSCRIPTS (for RAG, per account)
files = sorted(Path("transcripts").glob("*.md"))
print(f"\nMEETING TRANSCRIPTS: {len(files)}")
for f in files:
    head = f.read_text(encoding="utf-8").split("---")[1]
    meta = dict(line.split(": ", 1) for line in head.strip().splitlines())
    print(f"  {meta['meeting_date']}  {meta['account_name']:<34} {meta['meeting_type']}")

print("\nFIRST LINES OF ONE TRANSCRIPT:")
text = Path("transcripts/TR-ACC013-20260820.md").read_text(encoding="utf-8")
print(text.split("## Transcript")[1].strip()[:600], "...")
