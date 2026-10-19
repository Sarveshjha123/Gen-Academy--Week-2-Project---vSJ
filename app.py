"""Step 6 · THE CHAT WINDOW (Streamlit).   Run:   streamlit run app.py
A browser tab opens. Type like you'd message a colleague.
"""
import re
from datetime import date

import streamlit as st

from src import config
from src.graph import ask, build_graph
from src.nodes.router import book

st.set_page_config(page_title="Cloudpaw Renewal Desk", page_icon="🐾", layout="wide")

# ---------------------------------------------------------------- look and feel
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Figtree:wght@400;500;600&display=swap');
:root { --ink:#1C2733; --muted:#5B6878; --line:#DCE1E7; --paper:#F6F7F9; --teal:#0F5E63; --teal-soft:#E3F0EF;
        --amber:#A86F06; --amber-soft:#FBF1DC; --red:#B4372F; --red-soft:#FBE7E5; --green:#2E7D4F; --green-soft:#E3F2E8; }
html, body, [class*="css"], .stMarkdown, .stChatMessage, p, li, td, th { font-family:'Figtree', sans-serif !important; color:var(--ink); }
.stApp { background:var(--paper); }
.block-container { max-width:980px; padding-top:4.5rem; padding-bottom:6rem; }
h1, h2, h3, .desk-title { font-family:'Bricolage Grotesque', sans-serif !important; letter-spacing:-0.01em; }
.stChatMessage p, .stChatMessage li { font-size:0.98rem; line-height:1.6; }
.stChatMessage table { border-collapse:collapse; font-size:0.9rem; margin:0.6rem 0; }
.stChatMessage th { background:var(--teal-soft); color:var(--teal); text-align:left; padding:6px 10px; font-weight:600; }
.stChatMessage td { border-top:1px solid var(--line); padding:6px 10px; vertical-align:top; }
.stChatMessage h1, .stChatMessage h2, .stChatMessage h3 { font-size:1.08rem; margin:1rem 0 0.3rem; color:var(--teal); }
[data-testid="stSidebar"] { background:#FFFFFF; border-right:1px solid var(--line); }
.desk-title { font-size:1.9rem; font-weight:700; color:var(--ink); margin:0; line-height:1.3; padding-top:0.2rem; }
.desk-sub { color:var(--muted); margin:0.35rem 0 1.4rem; font-size:1rem; }
.acct { background:#FFFFFF; border:1px solid var(--line); border-left:4px solid var(--teal); border-radius:10px;
        padding:14px 16px; margin-bottom:12px; }
.acct.Red { border-left-color:var(--red); } .acct.Amber { border-left-color:var(--amber); } .acct.Green { border-left-color:var(--green); }
.acct .name { font-weight:600; font-size:1rem; margin-bottom:2px; }
.acct .where { color:var(--muted); font-size:0.85rem; margin-bottom:10px; }
.acct .days { font-family:'Bricolage Grotesque', sans-serif; font-size:2.3rem; font-weight:700; line-height:1; }
.acct .days small { font-family:'Figtree', sans-serif; font-size:0.85rem; font-weight:500; color:var(--muted); margin-left:6px; }
.acct .row { display:flex; justify-content:space-between; font-size:0.86rem; margin-top:8px; color:var(--muted); }
.acct .row b { color:var(--ink); font-weight:600; }
.chip { display:inline-block; padding:2px 9px; border-radius:999px; font-size:0.8rem; font-weight:600; }
.chip.Red { background:var(--red-soft); color:var(--red); } .chip.Amber { background:var(--amber-soft); color:var(--amber); }
.chip.Green { background:var(--green-soft); color:var(--green); }
.meta { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
.pill { background:#FFFFFF; border:1px solid var(--line); border-radius:999px; padding:3px 10px; font-size:0.8rem; color:var(--muted); }
.pill.ok { border-color:#BFDCCB; color:var(--green); } .pill.warn { border-color:#EBC9C5; color:var(--red); }
.empty { background:#FFFFFF; border:1px dashed var(--line); border-radius:12px; padding:22px 24px; color:var(--muted); }
.empty b { color:var(--ink); }
div.stButton > button { border-radius:8px; border:1px solid var(--line); background:#FFFFFF; color:var(--ink);
        text-align:left; font-size:0.88rem; padding:0.45rem 0.7rem; }
div.stButton > button:hover { border-color:var(--teal); color:var(--teal); }
div.stButton > button:focus-visible { outline:2px solid var(--teal); outline-offset:2px; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Loading the agent (first time takes ~30 s)...")
def get_graph():
    return build_graph()


def tidy(text):
    """Make LLM text render cleanly in Streamlit.
    Streamlit treats text between two $ signs as a math formula (that's what broke the fonts), so escape every $.
    Also join '30 %' into '30%'."""
    text = re.sub(r"(?<!\\)\$", r"\\$", text or "")
    return re.sub(r"(\d)\s+%", r"\1%", text)


def account_card(account_id):
    a = book().acc[book().acc.account_id == account_id].iloc[0]
    ae = book().ae[book().ae.ae_id == a.owner_ae_id].iloc[0]
    end = date.fromisoformat(a.contract_end)
    days = (end - config.TODAY).days
    return f"""
<div class="acct {a.health_band}">
  <div class="name">{a.account_name}</div>
  <div class="where">{a.ou}, {a.country} &nbsp;|&nbsp; {a.segment} &nbsp;|&nbsp; {a.industry}</div>
  <div class="days">{days}<small>days to renewal ({end:%b %d, %Y})</small></div>
  <div class="row"><span>Current ACV</span><b>${a.current_acv_usd:,.0f}</b></div>
  <div class="row"><span>Health</span><span class="chip {a.health_band}">{a.health_score} {a.health_band}</span></div>
  <div class="row"><span>Books in</span><b>{book().fiscal_year(end)}</b></div>
  <div class="row"><span>Owner</span><b>{ae.ae_name}</b></div>
</div>"""


EXAMPLES = [
    "Build me a renewal strategy for Helvetia Logistics AG",
    "Compare Andes Retail Group with Helvetia Logistics",
    "Summit Ridge Software is over its Product E commitment. What would a true-up add to ACV?",
    "What is the notice period for a price increase in EMEA?",
    "Build a renewal plan for Globex Corporation",
]

st.session_state.setdefault("messages", [])
st.session_state.setdefault("last_account", None)

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown('<p class="desk-title" style="font-size:1.35rem">🐾 Renewal Desk</p>', unsafe_allow_html=True)
    st.caption(f"Cloudpaw Inc. (fictional) · data as of {config.TODAY:%b %d, %Y}")
    last_ids = next((m["info"]["account_ids"] for m in reversed(st.session_state.messages)
                     if m.get("info") and m["info"].get("account_ids")), [])
    if last_ids:
        st.markdown("**In this conversation**")
        for aid in last_ids:
            st.markdown(account_card(aid), unsafe_allow_html=True)
    use_filter = st.toggle("Only use the customer's regional rules", value=True,
                           help="On: search the customer's OU + global documents. Off: search every region (for comparison).")
    st.markdown("**Try asking**")
    for i, ex in enumerate(EXAMPLES):
        if st.button(ex, key=f"ex{i}", use_container_width=True):
            st.session_state.pending = ex
    if st.button("Start a new conversation", use_container_width=True):
        st.session_state.messages, st.session_state.last_account = [], None
        st.rerun()

# ---------------------------------------------------------------- header
st.markdown('<p class="desk-title">Plan your next renewal</p>', unsafe_allow_html=True)
st.markdown('<p class="desk-sub">Name a customer. I check their health and usage, the renewal, commission and '
            'promotion rules for their region, and what they said in recent meetings, then cite every rule I use.</p>',
            unsafe_allow_html=True)


def show_details(info):
    checked = '<span class="pill ok">Fact-checked</span>' if info["grounded"] else '<span class="pill warn">Fact-check failed: review before using</span>'
    region = f'<span class="pill">Rules: {info["ou"]}</span>' if info["ou"] else ""
    st.markdown(f'<div class="meta">{checked}{region}<span class="pill">{len(info["sources"])} sources</span>'
                f'<span class="pill">{info["latency"]} s</span></div>', unsafe_allow_html=True)
    if info["sources"] or info.get("account_data"):
        with st.expander("Sources and checks"):
            if info.get("account_data"):
                st.markdown("**[Account data]** (from the customer tables, calculated in code)")
                st.text(info["account_data"])
            st.markdown("**Searched:** " + ", ".join(info["namespaces"] or []))
            for chunk_id, text in info["sources"]:
                st.markdown(f"**{chunk_id}**")
                st.text(text[:600])
            if info["dropped"]:
                st.markdown("**Left out by the grader:** " + ", ".join(info["dropped"]))
            st.markdown(f"**Fact-checker:** {tidy(info['reason'])}")


# ---------------------------------------------------------------- chat history
if not st.session_state.messages:
    st.markdown('<div class="empty"><b>Start with a customer name.</b> For example, ask for a renewal strategy for '
                'Helvetia Logistics AG, or compare two accounts. Follow-up questions remember the customer.</div>',
                unsafe_allow_html=True)

for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="🧑‍💼" if m["role"] == "user" else "🐾"):
        st.markdown(tidy(m["content"]))
        if m.get("info"):
            show_details(m["info"])

# ---------------------------------------------------------------- new question
question = st.chat_input("Ask about a customer's renewal...") or st.session_state.pop("pending", None)
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(tidy(question))
    with st.chat_message("assistant", avatar="🐾"):
        with st.spinner("Looking up the account, searching the rules, writing and fact-checking..."):
            out = ask(get_graph(), question, st.session_state.last_account, use_filter)
        st.markdown(tidy(out["generation"]))
        info = {"account_ids": out.get("account_ids", []), "ou": out.get("ou"), "latency": out["latency_s"],
                "grounded": out.get("hallucination_result") == "grounded", "reason": out.get("checker_reason", ""),
                "namespaces": out.get("namespaces"), "dropped": out.get("dropped", []),
                "account_data": out.get("account_data", "") if out.get("account_ids") else "",
                "sources": [(d.metadata["chunk_id"], d.page_content) for d in out.get("documents", [])]}
        show_details(info)
    if out.get("account_id"):
        st.session_state.last_account = out["account_id"]
    st.session_state.messages.append({"role": "assistant", "content": out["generation"], "info": info})
    st.rerun()   # refresh the sidebar account card
