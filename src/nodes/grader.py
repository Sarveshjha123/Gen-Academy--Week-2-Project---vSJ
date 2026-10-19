"""Node 3 · GRADER: throw away chunks that don't help answer the question (LLM-as-judge).

Solution kit: one LLM call per chunk. Ours: ONE call that grades all chunks at once
(same idea, about 10x cheaper and faster with 24 chunks).
"""
from langchain_core.messages import HumanMessage, SystemMessage

from src.nodes.llm import get_llm, read_json

GRADER_PROMPT = """You are a relevance grader. You get a user question, some account facts, and numbered document chunks.
A chunk is relevant if it contains keywords, rules, facts or meaning that could help answer the question
for this account. Be generous: partial relevance counts.
Respond with JSON only, listing the numbers of the relevant chunks.
Format: {"relevant": [1, 4, 5]}   (use [] if none are relevant)"""


def grader(state):
    docs = state.get("documents", [])
    if not docs:
        return {"documents": [], "grading_result": "not_relevant"}
    numbered = "\n\n".join(f"[{i}] {d.page_content[:700]}" for i, d in enumerate(docs, 1))
    facts = "\n".join(l for l in state["account_data"].splitlines() if not l.startswith("  - "))[:1500]
    msg = get_llm().invoke([SystemMessage(content=GRADER_PROMPT),
                            HumanMessage(content=f"ACCOUNT FACTS:\n{facts}\n\nCHUNKS:\n{numbered}\n\nQUESTION: {state['question']}")])
    keep_numbers = read_json(msg.content, {"relevant": list(range(1, len(docs) + 1))}).get("relevant", [])
    keep = set(int(n) for n in keep_numbers if str(n).isdigit())
    kept = [d for i, d in enumerate(docs, 1) if i in keep or d.metadata.get("pinned")]   # pinned = always kept
    return {"documents": kept,
            "dropped": [d.metadata["chunk_id"] for d in docs if d not in kept],
            "grading_result": "relevant" if kept else "not_relevant"}
