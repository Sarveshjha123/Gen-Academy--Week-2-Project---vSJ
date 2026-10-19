"""The few renewal rules that must ALWAYS be applied exactly: notice period, uplift cap, legal booking blockers.

Evaluation showed the LLM sometimes picked the GLOBAL rule instead of the stricter regional one
(e.g. 7% uplift instead of 3% for US Public Sector) or forgot the DACH 120-day notice.
So, like the dates and the maths, these rules are applied in code. Each rule names the document it comes from,
so the answer can still cite it. (In a real company this table would be kept in sync with the policy docs.)
"""
from datetime import date, timedelta

from src import config

DACH = {"Germany", "Austria", "Switzerland"}


def notice_rule(a):
    """Returns (days, why, doc_id)."""
    if a.ou == "AMER" and a.industry == "Public Sector" and a.country == "United States":
        return 120, "US Public Sector", "AMER-REN-101"
    if a.ou == "EMEA" and a.country in DACH:
        return 120, "DACH customer", "EMEA-REN-201"
    days = {"AMER": 90, "EMEA": 90, "ANZ": 90, "LATAM": 60, "South Asia": 60}[a.ou]
    return days, f"{a.ou} standard", {"AMER": "AMER-REN-101", "EMEA": "EMEA-REN-201", "ANZ": "ANZ-REN-501",
                                      "LATAM": "LATAM-REN-401", "South Asia": "SA-REN-301"}[a.ou]


def uplift_rule(a):
    """Returns (text, doc_id) for the cap that applies to THIS account."""
    multi = int(a.term_months) > 12
    if a.ou == "AMER":
        if a.industry == "Public Sector" and a.country == "United States":
            return "capped at 3% (US Public Sector)", "AMER-REN-101"
        return ("up to 5% per year (multi-year)" if multi else "up to 7% (1-year)"), "AMER-REN-101"
    if a.ou == "EMEA":
        return ("up to 4% per year (multi-year)" if multi else
                "up to 5% (1-year), or 6% if the contract has an inflation-indexation clause"), "EMEA-REN-201"
    if a.ou == "ANZ":
        return ("up to 4% per year (multi-year)" if multi else "up to 6% (1-year)"), "ANZ-REN-501"
    if a.ou == "LATAM":
        return ("up to 6% per year (multi-year)" if multi else
                "6% (1-year), or up to 10% only with a written FX or inflation justification"), "LATAM-REN-401"
    return ("up to 6% per year (multi-year)" if multi else "up to 8% (1-year)"), "SA-REN-301"


def legal_blockers(a):
    """Only the legal checks that apply in this account's OU/country."""
    out = []
    if a.ou == "EMEA":
        if a.dpa_version != "v4.2":
            out.append(f"DPA is {a.dpa_version}; EMEA renewals need DPA v4.2 re-signed BEFORE booking [EMEA-REN-201]")
        else:
            out.append("DPA v4.2 already signed: no DPA blocker [EMEA-REN-201]")
    if a.country == "India":
        if str(a.gstin_on_file) != "True":
            out.append("GSTIN is NOT on file; India needs the GSTIN on the order form BEFORE booking [SA-REN-301]")
        else:
            out.append("GSTIN on file: no GSTIN blocker [SA-REN-301]")
    return out or ["No DPA or GSTIN requirement applies to this OU/country"]


def health_play(a):
    """What the health playbook says to do for this account's band."""
    score = int(a.health_score)
    if score < 50:
        save_by = date.fromisoformat(a.contract_end) - timedelta(days=60)
        return (f"Red ({score}): register with the Save Desk at least 60 days before contract end, i.e. by {save_by} "
                f"[GLB-ATTR-003]; lead with value, not price [GLB-HEALTH-007]")
    if score < 75:
        return f"Amber ({score}): fix the weak driver before the proposal [GLB-HEALTH-007]"
    return f"Green ({score}): renewal likely; focus on expansion [GLB-HEALTH-007]"


def accelerator(a):
    """GLB-COMP-006 section 3, applied to the owner AE's attainment."""
    from src.nodes.router import book
    att = float(book().ae[book().ae.ae_id == a.owner_ae_id].iloc[0].attainment_ytd_pct)
    if att > 125:
        return f"AE at {att:g}% of quota -> incremental bookings paid at 2x the commission rate [GLB-COMP-006]"
    if att >= 100:
        return f"AE at {att:g}% of quota -> incremental bookings paid at 1.5x the commission rate [GLB-COMP-006]"
    return f"AE at {att:g}% of quota -> standard commission rates, no accelerator [GLB-COMP-006]"


def rules_block(a):
    """Lines added to ACCOUNT DATA so the generator gets the exact rules for this account."""
    end = date.fromisoformat(a.contract_end)
    days, why, doc = notice_rule(a)
    notice_date = end - timedelta(days=days)
    passed = notice_date < config.TODAY
    cap, cap_doc = uplift_rule(a)
    lines = ["RULES THAT APPLY TO THIS ACCOUNT (applied in code from the regional addendum):",
             f"  * Notice period: {days} days ({why}) [{doc}] -> notice date {notice_date}: "
             + ("PASSED. An uplift is only allowed with the customer's written agreement; otherwise renew at the "
                "current price [GLB-REN-001]" if passed else f"upcoming, {(notice_date - config.TODAY).days} days from today"),
             f"  * Uplift cap: {cap} [{cap_doc}] (regional rule overrides the GLOBAL default)"]
    lines += [f"  * Legal: {x}" for x in legal_blockers(a)]
    lines.append(f"  * Health play: {health_play(a)}")
    lines.append(f"  * AE accelerator: {accelerator(a)}")
    return lines, {"notice_days": days, "notice_date": str(notice_date), "notice_passed": passed,
                   "notice_doc": doc, "uplift_cap": cap, "uplift_doc": cap_doc}
