"""Node 2 · RETRIEVER (+ retry_retrieve): hybrid search from Step 4, inside each customer's own region only.

For a full renewal strategy we search several topics (renewal rules, ACV, attrition, commission, promotions,
programs, benchmark, the customer's meetings) so no part of the brief is missing (Session 2: query decomposition).
For a comparison we do this once per customer, each in its own region, then put the results together.
"""
from langchain_core.documents import Document

from src import config
from src.retriever import hybrid_search, sections_for

TOPICS = [
    "{ou} renewal addendum notice period uplift cap approvals legal requirements",
    "ACV booking policy overage true-up consumption commitment",
    "attrition downsell right-size shelfware save desk quota impact",
    "commission rates quota retirement accelerator",
    "{ou} promotions eligibility {segment} {industry}",
    "{ou} SPIFF quota programs renew early cross-sell",
    "{ou} consumption benchmark {segment} {industry} products",
    "health score bands plays",
    "customer priorities concerns demos interest in products",
]
COMPARE_TOPICS = [0, 4, 5, 7, 8]          # the topics that differ most between two customers


def _queries(state, ou, account_id):
    queries = [state["question"]]
    if account_id:   # add who the customer is, so rules for their country / segment / industry are found too
        from src.nodes.router import book
        a = book().acc[book().acc.account_id == account_id].iloc[0]
        queries.append(f"{state['question']} {a.country} {a.segment} {a.industry} renewal rules")
    if state["mode"] in ("strategy", "compare") and account_id:
        from src.nodes.router import book
        a = book().acc[book().acc.account_id == account_id].iloc[0]
        picks = range(len(TOPICS)) if state["mode"] == "strategy" else COMPARE_TOPICS
        queries += [TOPICS[i].format(ou=ou, segment=a.segment, industry=a.industry) for i in picks]
    return queries


def _search(state, k):
    found, seen, namespaces = [], set(), []
    for ou, account_id in state.get("targets", [(None, None)]):
        ou = ou if state.get("use_ou_filter", True) else None
        namespaces += [n for n in sections_for(ou, account_id) if n not in namespaces]
        for q in _queries(state, ou, account_id):
            for doc in hybrid_search(q, ou=ou, account_id=account_id, k=k):
                if doc.metadata["chunk_id"] not in seen:
                    seen.add(doc.metadata["chunk_id"])
                    found.append(doc)
    limit = {"strategy": 24, "compare": 28}.get(state["mode"], 8)
    found = found[:limit]
    if any(ou for ou, _ in state.get("targets", [])):
        pinned = pinned_docs(state)
        pinned_ids = {d.metadata["chunk_id"] for d in pinned}
        found = pinned + [d for d in found if d.metadata["chunk_id"] not in pinned_ids]
    return {"documents": found, "namespaces": namespaces}


PINNED_KINDS = ("-REN-", "-PROMO-", "-PROG-")


def pinned_docs(state):
    """The region's renewal addendum, promotions and SPIFF/program documents are short (about 1,000 characters
    each), so whenever we know the region we add them COMPLETE, plus the global commission plan for account
    questions. Then the agent can also say what does NOT exist (e.g. "no Renew Early in LATAM") and never misses
    an approval limit or tax rule. Search alone can't prove something is absent: it only returns what matches."""
    from src.retriever import _keyword_index
    chunks, _ = _keyword_index()
    out = []
    for ou, _account in state.get("targets", []):
        if not ou or not state.get("use_ou_filter", True):
            continue
        for c in chunks:
            m = c.metadata
            regional = m.get("ou") == ou and any(k in m["doc_id"] for k in PINNED_KINDS) and m["doc_id"] != "GLB-REN-001"
            comp_plan = _account is not None and m["doc_id"] == "GLB-COMP-006"
            if (regional or comp_plan) and m["chunk_id"] not in {d.metadata["chunk_id"] for d in out}:
                out.append(Document(page_content=c.page_content, metadata={**m, "pinned": True}))
    return out


def retriever(state):
    return _search(state, k=3 if state["mode"] in ("strategy", "compare") else config.TOP_K)


def retry_retrieve(state):
    """Grader found nothing useful → search again, wider (more chunks per search). Still the same region(s) only:
    we never borrow another OU's rules."""
    out = _search(state, k=config.TOP_K * 2)
    out["retrieve_attempts"] = state.get("retrieve_attempts", 0) + 1
    return out
