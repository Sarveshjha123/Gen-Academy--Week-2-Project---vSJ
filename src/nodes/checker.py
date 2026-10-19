"""Node 5 · CHECKER: is every fact in the answer backed by the account data or the documents? (hallucination check)"""
import re

from langchain_core.messages import HumanMessage, SystemMessage

from src.nodes.generator import format_context
from src.nodes.llm import get_llm, read_json

CHECKER_PROMPT = """You are a hallucination detector. Decide whether an AI-generated answer is fully supported
by the ACCOUNT DATA and the DOCUMENTS provided.
Score "yes" -> every fact, date and rule in the answer appears in the data or documents, AND every dollar amount
               or percentage either appears there or is a sum/difference of amounts that appear there.
Score "no"  -> the answer contains a fact, rule, date or number NOT found there. Be strict about money:
               an upsell, forecast or deal size that is not in the data (e.g. "up to $200k") is a "no",
               even if it sounds reasonable or is built from catalog list prices.
What counts:
- Check FACTS: numbers, dates, rates, rules, eligibility, requirements, deadlines, approvals.
- Recommendations and judgement (which scenario to choose, what to prioritise, which product to propose) are
  ALLOWED when they are built on facts that are in the data or documents. Do not fail an answer for recommending.
- But score "no" if the answer presents something as a REQUIREMENT, RULE or DEADLINE ("must", "required",
  "needs approval") that no document or ACCOUNT DATA line states.
- Lines under "RULES THAT APPLY TO THIS ACCOUNT", "AE accelerator" and "OFFERS ALREADY CHECKED" were produced by
  code from the documents: treat them as correct, with the doc_ids shown.
- A fact may be cited to any document that states it. Minor wording differences are fine.
Facts tagged [Account data] must match ACCOUNT DATA.
A refusal such as "I can't find that account" or "I couldn't find that" counts as "yes".
Respond with JSON only.
Format: {"score": "yes", "reason": "<one short sentence; if no, name the unsupported claim>"}"""


DOC_ID = re.compile(r"\b(?:GLB|AMER|EMEA|SA|LATAM|ANZ)-[A-Z]+-\d{3}\b|\bTR-ACC\d{3}-\d{8}\b")
SEPARATOR = re.compile(r"^\|[\s:|-]+\|?$")


def citation_check(answer, docs, account_data=""):
    """Rule-based check in plain code (no LLM). Two rules the LLM can't argue its way past:
    1. every doc_id it cites must be one we actually retrieved (no made-up sources);
    2. every bullet and table row must carry a source tag: [doc_id] or [Account data]."""
    retrieved = {d.metadata["doc_id"] for d in docs} | set(DOC_ID.findall(account_data))
    fake = sorted(set(DOC_ID.findall(answer)) - retrieved)
    if fake:
        return f"cites documents that were not retrieved: {', '.join(fake)}"
    lines = [l.strip() for l in answer.splitlines()]
    untagged = []
    for i, line in enumerate(lines):
        is_header = i + 1 < len(lines) and SEPARATOR.match(lines[i + 1] or "")
        is_row = line.startswith("|") and not SEPARATOR.match(line) and not is_header
        is_bullet = re.match(r"^([-*]|\d+\.)\s", line)
        is_list_title = line.rstrip("*").endswith(":")       # e.g. "- **Cross-sell estimates:**" introducing sub-bullets
        if (is_row or is_bullet) and not is_list_title and len(line) > 45 and not (DOC_ID.search(line) or "[Account data]" in line):
            untagged.append(line[:70])
    if untagged:
        return f"{len(untagged)} line(s) have no source, e.g. '{untagged[0]}'"
    return None


def checker(state):
    problem = citation_check(state["generation"], state.get("documents", []), state.get("account_data", ""))
    if problem and not state["generation"].lstrip().startswith("I can't find"):
        return {"hallucination_result": "not_grounded", "checker_reason": "Code check: " + problem}
    human = (f"ACCOUNT DATA:\n{state['account_data']}\n\nDOCUMENTS:\n{format_context(state.get('documents', []))}\n\n"
             f"ANSWER TO CHECK:\n{state['generation']}")
    msg = get_llm().invoke([SystemMessage(content=CHECKER_PROMPT), HumanMessage(content=human)])
    verdict = read_json(msg.content, {"score": "yes", "reason": "checker reply was not JSON"})
    grounded = str(verdict.get("score", "yes")).lower().startswith("y")
    return {"hallucination_result": "grounded" if grounded else "not_grounded",
            "checker_reason": verdict.get("reason", "")}
