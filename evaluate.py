"""Step 7 · EVALUATION: run the 25 golden questions and score the agent (Session 2: evaluate retrieval and
generation separately).

    python evaluate.py                  # all 25 questions, OU filter on
    python evaluate.py --repeat 2       # ask every question twice → also measures CONSISTENCY
    python evaluate.py --compare-ou     # run with AND without the OU filter, side by side
    python evaluate.py --limit 5        # quick test on the first 5 questions

Writes eval/evaluation_report.json (+ eval/evaluation_results.csv to open in Excel/Sheets).
"""
import argparse
import json
import statistics
import time

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage

from src import config
from src.graph import ask, build_graph
from src.nodes.checker import citation_check
from src.nodes.llm import get_llm, read_json

JUDGE_PROMPT = """You are grading a renewal assistant against an answer key.
CORRECT (1) = the answer contains the key facts in the EXPECTED ANSWER (same numbers, dates, rules, eligibility)
and does not contradict any of them. Wording and extra correct detail don't matter.
For refusal questions, CORRECT = the answer refuses / says it can't find the account or can't do it.
INCORRECT (0) = a key fact is missing, wrong or contradicted.
Respond with JSON only: {"correct": 1, "reason": "<one short sentence>"}"""


def judge(question, expected, answer):
    msg = get_llm().invoke([SystemMessage(content=JUDGE_PROMPT),
                            HumanMessage(content=f"QUESTION: {question}\n\nEXPECTED ANSWER: {expected}\n\nASSISTANT ANSWER:\n{answer}")])
    v = read_json(msg.content, {"correct": 0, "reason": "judge reply was not JSON"})
    return int(v.get("correct", 0)), v.get("reason", "")


def score_one(graph, row, use_ou_filter):
    out = ask(graph, row.question, use_ou_filter=use_ou_filter)
    answer = out.get("generation", "")
    expected_docs = [d.strip() for d in str(row.source_doc_ids).split(";") if d.strip() and not d.strip().startswith("(")]
    got_docs = {d.metadata["doc_id"] for d in out.get("documents", [])}
    refused = bool(out.get("refuse")) or answer.lstrip().startswith("I can't find")
    if row.type == "refusal" and row.ou == "UNKNOWN":
        right_account = int(refused)
    else:
        right_account = int(not refused and (row.ou in str(out.get("ou")) or row.ou == "GLOBAL"))
    correct, reason = judge(row.question, row.expected_answer, answer)
    return {
        "id": row.id, "type": row.type, "ou": row.ou, "question": row.question,
        "found_right_account": right_account,
        "retrieved_right_doc": int(not expected_docs or bool(set(expected_docs) & got_docs) or refused),
        "answer_correct": correct,
        "faithful": int(out.get("hallucination_result") == "grounded"),
        "cited": int(refused or citation_check(answer, out.get("documents", []), out.get("account_data", "")) is None),
        "latency_s": out.get("latency_s"),
        "answer_attempts": out.get("generate_attempts", 0),
        "judge_reason": reason, "checker_reason": out.get("checker_reason", ""),
        "answer": answer,
    }


def summarize(rows):
    df = pd.DataFrame(rows)
    pct = lambda col: float(round(100 * df[col].mean(), 1))
    lat = sorted(df.latency_s.dropna())
    return {
        "questions": int(df.id.nunique()), "runs": len(df),
        "found_right_account_pct": pct("found_right_account"),
        "retrieved_right_doc_pct": pct("retrieved_right_doc"),
        "answer_correct_pct": pct("answer_correct"),
        "faithfulness_pct": pct("faithful"),
        "fully_cited_pct": pct("cited"),
        "refusals_correct": f"{int(df[df.type == 'refusal'].answer_correct.sum())}/{int((df.type == 'refusal').sum())}",
        "latency_median_s": round(statistics.median(lat), 1) if lat else None,
        "latency_p90_s": round(lat[int(0.9 * (len(lat) - 1))], 1) if lat else None,
        "by_type_answer_correct_pct": {t: float(round(100 * g.answer_correct.mean(), 1)) for t, g in df.groupby("type")},
    }


def consistency(rows):
    """Same question asked N times: did the grade (correct / not) stay the same every time?"""
    df = pd.DataFrame(rows)
    same = df.groupby("id").answer_correct.nunique().eq(1)
    return {"questions_with_same_grade_every_run_pct": float(round(100 * same.mean(), 1)),
            "inconsistent_ids": sorted(same[~same].index.tolist())}


def run(graph, golden, use_ou_filter, repeat):
    rows = []
    for r in range(repeat):
        for row in golden.itertuples():
            t = time.time()
            res = score_one(graph, row, use_ou_filter)
            res["run"] = r + 1
            rows.append(res)
            mark = "✓" if res["answer_correct"] else "✗"
            print(f"  {mark} {row.id} (run {r + 1}) {res['latency_s']}s  faithful={res['faithful']}  {row.question[:60]}")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--compare-ou", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    golden = pd.read_csv(config.EVAL_DIR / "golden_set.csv", keep_default_na=False)
    golden.columns = [c.split("(")[0] for c in golden.columns]
    if args.limit:
        golden = golden.head(args.limit)
    graph = build_graph()

    report = {"model": config.CHAT_MODEL, "today": str(config.TODAY), "targets": {
        "faithfulness_pct": 90, "answer_correct_pct": 90, "found_right_account_pct": 100, "retrieved_right_doc_pct": 100,
        "latency_median_s_narrow": 15, "latency_median_s_full_brief": 45}}
    settings = [("with_ou_filter", True)] + ([("without_ou_filter", False)] if args.compare_ou else [])
    all_rows = []
    for name, flag in settings:
        print(f"\n=== {name.replace('_', ' ')} ===")
        rows = run(graph, golden, flag, args.repeat)
        report[name] = summarize(rows)
        if args.repeat > 1:
            report[name]["consistency"] = consistency(rows)
        all_rows += [{**r, "setting": name} for r in rows]

    config.EVAL_DIR.mkdir(exist_ok=True)
    report["results"] = [{k: v for k, v in r.items() if k != "answer"} for r in all_rows]
    (config.EVAL_DIR / "evaluation_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    pd.DataFrame(all_rows).to_csv(config.EVAL_DIR / "evaluation_results.csv", index=False)

    print("\n================ SUMMARY ================")
    for name, _ in settings:
        print(f"\n{name}:")
        for k, v in report[name].items():
            print(f"  {k:<34} {v}")
    print("\nSaved eval/evaluation_report.json and eval/evaluation_results.csv")
