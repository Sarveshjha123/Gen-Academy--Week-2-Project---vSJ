"""Node 1 · ROUTER: who is this question about, and which region's rules apply?

Solution kit: the router asks the LLM to pick a namespace.
Our version: we look the customer(s) up in the accounts table instead. A table lookup is exact and free,
and each account's OU tells us which namespace to search (Session 2: metadata filtering).

Three outcomes:
  - 1 customer found   → normal answer (or full strategy)
  - 2 customers found  → comparison
  - a company is named that is NOT in our table → refuse in code, before any LLM call (can't hallucinate)
"""
import re
from functools import lru_cache

from src.accounts import AccountBook

STRATEGY_WORDS = ("strategy", "plan", "brief", "prepare", "approach", "what should i do", "renewing")
COMPANY_SUFFIXES = {"inc", "corp", "corporation", "ltd", "llc", "gmbh", "ag", "group", "company", "co", "plc", "sa", "bv"}
REFUSAL = "I can't find **{name}** in Cloudpaw's records. Please check the account name and try again."


@lru_cache(maxsize=1)
def book():
    return AccountBook()


@lru_cache(maxsize=1)
def known_words():
    """Capitalised words that are NOT customer names: industries, segments, countries, products, AE names, regions."""
    b = book()
    words = set()
    for col in ("industry", "segment", "country"):
        for v in b.acc[col].unique():
            words.update(re.findall(r"[a-z]+", v.lower()))
    for v in b.ae.ae_name:
        words.update(v.lower().split())
    words.update({"product", "amer", "emea", "latam", "anz", "south", "asia", "dach", "global", "cloudpaw",
                  "spiff", "spiffs", "acv", "the", "renew", "early", "q1", "q2", "q3", "q4", "fy27"})
    return words


def unknown_company(question):
    """Find names like 'Globex Corporation' after for/about/with/and/of that are not in our customer table."""
    for m in re.finditer(r"\b(?:for|about|with|and|of|vs\.?|versus)\s+((?:[A-Z][\w&'.-]*\s?){1,4})", question):
        words = re.sub(r"'s", "", m.group(1)).strip().split()
        lowered = [w.lower().strip(".?,!") for w in words]
        name = " ".join(words).strip(".?,!")
        if all(w in known_words() or len(w) == 1 for w in lowered):
            continue                                   # e.g. "Product B", "Public Sector", "United States"
        if book().find_accounts(name) or book().find_ae(name):
            continue                                   # a real customer or AE
        if lowered and lowered[0] in ("product", "the"):
            continue
        if len(words) >= 2 or (lowered and lowered[-1] in COMPANY_SUFFIXES):
            return name
    return None


def router(state):
    q = state["question"]
    ids = book().find_accounts(q)
    stranger = unknown_company(q)

    # A company we don't know, and no known one → stop here with a clear refusal (no LLM, no guessing)
    if stranger and not ids and not book().find_ae(q):
        return {"refuse": True, "generation": REFUSAL.format(name=stranger), "account_ids": [], "ou": None,
                "namespaces": [], "documents": [], "hallucination_result": "grounded",
                "checker_reason": "Refused in code: account not in the customer table."}

    # Follow-up like "and the commission?" → same customer as the previous chat turn
    if not ids and state.get("previous_account_id") and not book().find_ou(q):
        ids = [state["previous_account_id"]]

    ae_id = None if ids else book().find_ae(q)
    targets, blocks = [], []                  # targets = (ou, account_id) pairs to search for
    for aid in ids:
        text, ou, _ = book().account_brief_data(aid)
        blocks.append(text)
        targets.append((ou, aid))
    if ae_id:
        text, ou = book().ae_portfolio_data(ae_id)
        blocks.append(text)
        targets.append((ou, None))
    if not targets:
        targets.append((book().find_ou(q), None))
        blocks.append("No customer was named. Answer from the policy documents only.")
    if stranger and ids:
        blocks.append(f"NOTE: '{stranger}' is NOT a Cloudpaw customer. Say so; do not invent data for it.")

    if len(ids) > 1:
        mode = "compare"
    elif ids and any(w in q.lower() for w in STRATEGY_WORDS):
        mode = "strategy"
    else:
        mode = "question"

    first = book().acc[book().acc.account_id == ids[0]].iloc[0] if ids else None
    names = [book().acc[book().acc.account_id == a].iloc[0].account_name for a in ids]
    return {
        "refuse": False,
        "account_ids": ids,
        "account_id": ids[0] if ids else None,
        "account_name": " vs ".join(names) if names else None,
        "segment": first.segment if first is not None else "",
        "industry": first.industry if first is not None else "",
        "ou": " + ".join(dict.fromkeys(t[0] for t in targets if t[0])) or None,
        "targets": targets,
        "account_data": "\n\n".join(blocks),
        "mode": mode,
        "retrieve_attempts": 0,
        "generate_attempts": 0,
    }
