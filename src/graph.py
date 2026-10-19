"""Step 5 · THE AGENT: connect the 5 nodes with LangGraph (same shape as the solution kit).

    router ─(unknown company → refuse → END)
      ↓
    retriever → grader ─┬─ relevant ──→ offers → generator → checker ─┬─ grounded ─────→ END
                        └─ not relevant → retry_retrieve ↩ grader       └─ not grounded → generator (retry)
    (offers = every promotion/SPIFF checked one by one; only for full strategies and comparisons)
    Both loops stop after MAX_RETRIES = 2.

Try it in the terminal:   python -m src.graph "Build me a renewal strategy for Helvetia Logistics AG"
"""
import sys
import time
from typing import List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src import config
from src.nodes.checker import checker
from src.nodes.generator import generator
from src.nodes.grader import grader
from src.nodes.offers import offers
from src.nodes.retriever import retriever, retry_retrieve
from src.nodes.router import router


class RenewalState(TypedDict, total=False):
    question: str                  # what the AE typed
    previous_account_id: Optional[str]   # the customer from the last chat turn (for follow-ups)
    use_ou_filter: bool            # True = only this region's + global rules
    refuse: bool                   # router: True = unknown company → answer "can't find" and stop
    account_ids: List[str]         # router: which customer(s) (2 = comparison)
    targets: list                  # router: (OU, account_id) pairs to search for
    account_id: Optional[str]      # router: the first customer
    account_name: Optional[str]
    segment: str
    industry: str
    ou: Optional[str]              # router: which region
    account_data: str              # router: exact facts + math from the tables
    mode: str                      # "strategy" (full brief), "compare" (2 accounts) or "question" (narrow)
    namespaces: List[str]          # retriever: which Pinecone sections were searched
    documents: list                # retriever → grader keeps only the useful ones
    dropped: List[str]             # grader: chunk_ids it threw away
    grading_result: str            # "relevant" / "not_relevant"
    offers_md: str                 # offers: table of every promotion/program, eligible or not
    generation: str                # generator: the answer
    hallucination_result: str      # "grounded" / "not_grounded"
    checker_reason: str
    retrieve_attempts: int
    generate_attempts: int


def decide_after_routing(state):
    return "refuse" if state.get("refuse") else "search"


def decide_after_grading(state):
    if state["grading_result"] == "relevant" or state.get("retrieve_attempts", 0) >= config.MAX_RETRIES:
        return "generate"
    return "retry_retrieve"


def decide_after_checking(state):
    if state["hallucination_result"] == "grounded" or state.get("generate_attempts", 0) > config.MAX_RETRIES:
        return "finish"
    return "regenerate"


def build_graph():
    g = StateGraph(RenewalState)
    g.add_node("router", router)
    g.add_node("retriever", retriever)
    g.add_node("retry_retrieve", retry_retrieve)
    g.add_node("grader", grader)
    g.add_node("offers", offers)
    g.add_node("generator", generator)
    g.add_node("checker", checker)

    g.add_edge(START, "router")
    g.add_conditional_edges("router", decide_after_routing, {"refuse": END, "search": "retriever"})
    g.add_edge("retriever", "grader")
    g.add_conditional_edges("grader", decide_after_grading, {"generate": "offers", "retry_retrieve": "retry_retrieve"})
    g.add_edge("offers", "generator")
    g.add_edge("retry_retrieve", "grader")
    g.add_edge("generator", "checker")
    g.add_conditional_edges("checker", decide_after_checking, {"finish": END, "regenerate": "generator"})
    return g.compile()


def ask(graph, question, previous_account_id=None, use_ou_filter=True):
    start = time.time()
    out = graph.invoke({"question": question, "previous_account_id": previous_account_id, "use_ou_filter": use_ou_filter})
    out["latency_s"] = round(time.time() - start, 1)
    return out


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Build me a renewal strategy for Helvetia Logistics AG"
    result = ask(build_graph(), question)
    print(result["generation"])
    print("\n---")
    print(f"Account: {result.get('account_name')} | OU: {result.get('ou')} | searched: {result.get('namespaces')}")
    print(f"Chunks kept by grader: {len(result.get('documents', []))} | dropped: {len(result.get('dropped', []))}")
    print(f"Checker: {result.get('hallucination_result')} ({result.get('checker_reason')}) | "
          f"answer attempts: {result.get('generate_attempts')} | {result['latency_s']} s")
