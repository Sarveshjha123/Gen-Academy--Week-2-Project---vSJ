"""Node 3b · OFFERS: check every promotion and SPIFF/program for the customer, one by one.

Evaluation showed the big strategy prompt kept skipping some offers (e.g. the LATAM AI Agents Pilot) and never said
what does NOT exist (e.g. "no Renew Early in LATAM"). So this is now its own small, focused LLM task
(Session 2: break a big task into smaller ones). Its JSON answer is turned into a table by code.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from src.nodes.llm import get_llm, read_json

OFFERS_PROMPT = """You check promotion and sales-program eligibility for ONE customer.
You get ACCOUNT FACTS and the COMPLETE promotions and SPIFF/program documents for the customer's region.
Return JSON only:
{"offers": [{"name": "...", "kind": "promotion" or "SPIFF/program", "eligible": "yes" or "no" or "if ...",
             "reason": "<which conditions are met or not: dates vs today, segment, industry, ACV, products owned, health>",
             "doc_id": "<doc id>"}],
 "notes": [{"text": "...", "doc_id": "<doc id>"}]}
Rules:
- One entry in "offers" for EVERY offer section (## heading) in the documents. Do not skip any.
- "if ..." = eligible only if a future action happens (e.g. "if closed by 2026-12-02").
- "notes": (a) every sentence in the documents saying a program is NOT run in this region;
  (b) for every owned product whose band is SHELFWARE or OVERAGE: does any promotion here target that product?
  e.g. {"text": "No promotion for Product F in EMEA", "doc_id": "EMEA-PROMO-202"}.
- Use only the documents and facts given. No advice."""


def _facts(account_data, account_id):
    """The account's own block of ACCOUNT DATA (for a comparison there are two blocks)."""
    for block in account_data.split("\n\n"):
        if f"({account_id})" in block.splitlines()[0]:
            return "\n".join(l for l in block.splitlines() if not l.startswith("CROSS-SELL"))
    return account_data


def check_offers(account_id, ou, account_data, docs):
    region_docs = [d for d in docs if d.metadata.get("pinned") and d.metadata.get("ou") == ou
                   and ("-PROMO-" in d.metadata["doc_id"] or "-PROG-" in d.metadata["doc_id"])]
    if not region_docs:
        return [], []
    text = "\n\n".join(f'<doc id="{d.metadata["doc_id"]}">\n{d.page_content}\n</doc>' for d in region_docs)
    msg = get_llm().invoke([SystemMessage(content=OFFERS_PROMPT),
                            HumanMessage(content=f"ACCOUNT FACTS:\n{_facts(account_data, account_id)}\n\nDOCUMENTS:\n{text}")])
    data = read_json(msg.content, {"offers": [], "notes": []})
    return data.get("offers", []) or [], data.get("notes", []) or []


def offers_markdown(name, offers, notes):
    if not offers and not notes:
        return ""
    out = [f"## Promotions and programs: {name} (each one checked)", "",
           "| Offer | Type | Eligible? | Why | Source |", "|---|---|---|---|---|"]
    for o in offers:
        out.append(f"| {o.get('name', '')} | {o.get('kind', '')} | {o.get('eligible', '')} | "
                   f"{str(o.get('reason', '')).replace('|', '/')} | [{o.get('doc_id', '')}] |")
    out += [""] + [f"- {n.get('text', '')} [{n.get('doc_id', '')}]" for n in notes]
    return "\n".join(out)


def offers(state):
    """Runs only for full strategies and comparisons. Adds the checked offers to ACCOUNT DATA (so the generator and
    the checker both see them) and keeps the table to show in the answer."""
    if not any(account_id for _, account_id in state.get("targets", [])):
        return {}            # region-only or general questions: no customer to check offers for
    from src.nodes.router import book
    tables, extra = [], []
    for ou, account_id in state.get("targets", []):
        if not account_id:
            continue
        name = book().acc[book().acc.account_id == account_id].iloc[0].account_name
        found, notes = check_offers(account_id, ou, state["account_data"], state.get("documents", []))
        md = offers_markdown(name, found, notes)
        if md:
            tables.append(md)
            extra.append(f"OFFERS ALREADY CHECKED FOR {name} (final, shown to the user as a table):\n{md}")
    if not tables:
        return {}
    return {"offers_md": "\n\n".join(tables), "account_data": state["account_data"] + "\n\n" + "\n\n".join(extra)}
