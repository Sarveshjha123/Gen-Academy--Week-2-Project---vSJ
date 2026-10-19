"""The customer database: look up one account and do the exact math in plain code (no LLM).

Session 2 lesson: anything that must be exact (dates, sums, %) is computed in code, not by the model.
"""
import re
import unicodedata
from datetime import date, timedelta

import pandas as pd

from src import config
from src.rules import health_play, rules_block

OU_WORDS = {
    "AMER": ["amer", "united states", "us ", "usa", "canada", "north america"],
    "EMEA": ["emea", "europe", "uk", "united kingdom", "germany", "france", "netherlands", "switzerland", "uae", "dach"],
    "South Asia": ["south asia", "india", "sri lanka", "bangladesh"],
    "LATAM": ["latam", "latin america", "brazil", "mexico", "chile", "colombia", "argentina"],
    "ANZ": ["anz", "australia", "new zealand"],
}
GENERIC = {"the", "of", "and", "group", "ltd", "inc", "llc", "gmbh", "ag", "bv", "sa", "pvt", "co", "de", "services", "&"}


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


class AccountBook:
    def __init__(self):
        d = config.DATA_DIR
        self.acc = pd.read_csv(d / "accounts.csv", keep_default_na=False)
        self.ae = pd.read_csv(d / "ae_roster.csv")
        self.lines = pd.read_csv(d / "contract_lines.csv")
        self.cons = pd.read_csv(d / "consumption_monthly.csv")

    # ------------------------------------------------------------ who is the question about?
    def find_accounts(self, question):
        q = " " + _norm(question) + " "
        hits = []
        for _, r in self.acc.iterrows():
            name = _norm(r.account_name)
            if name in q:
                hits.append((1.0, r.account_id)); continue
            toks = [t for t in name.split() if t not in GENERIC]
            if toks:
                share = sum(1 for t in toks if f" {t} " in q) / len(toks)
                if share >= 0.67:
                    hits.append((share, r.account_id))
        hits.sort(reverse=True)
        return [a for _, a in hits[:2]]

    def find_ae(self, question):
        q = _norm(question)
        for _, r in self.ae.iterrows():
            if _norm(r.ae_name) in q:
                return r.ae_id
        return None

    @staticmethod
    def find_ou(question):
        q = " " + _norm(question) + " "
        for ou, words in OU_WORDS.items():
            if any(f" {w.strip()} " in q for w in words):
                return ou
        return None

    # ------------------------------------------------------------ calculations
    def product_signals(self, account_id):
        """Per product: utilization last 3 vs previous 3 months, trend, band, per-user rate, true-up math."""
        rows = []
        for _, ln in self.lines[self.lines.account_id == account_id].iterrows():
            c = self.cons[self.cons.line_id == ln.line_id].sort_values("month")
            last3, prev3 = c.utilization_pct.tail(3).mean(), c.utilization_pct.iloc[-6:-3].mean()
            change = (last3 - prev3) / prev3 * 100 if prev3 else 0
            trend = "rising" if change > 5 else "falling" if change < -5 else "flat"
            months_below_50 = int((c.utilization_pct.tail(6) < 50)[::-1].cumprod().sum())
            band = ("OVERAGE" if last3 > 100 else "expansion-ready" if last3 >= 85
                    else "healthy" if last3 >= 50 else "SHELFWARE")
            last = c.iloc[-1]
            r = dict(product=ln.product_name, code=ln.product_code, model=ln.pricing_model,
                     licensed=f"{ln.licensed_qty:,.0f} {ln.licensed_unit}", line_acv_usd=int(ln.line_acv_usd),
                     discount_pct=int(ln.discount_pct), util_last3=round(last3, 1), util_prev3=round(prev3, 1),
                     trend=f"{trend} ({change:+.0f}%)", band=band, consecutive_months_below_50=months_below_50,
                     last_month=(f"{last.month}: " + (
                         f"{int(last.active_users)} active of {last.entitlement_qty:,.0f} seats ({last.utilization_pct:g}% of seats active); "
                         f"total {last.consumed_qty:,.0f} {last.consumed_unit}; " if ln.pricing_model == "seat" else
                         f"{int(last.active_users)} active users; consumed {last.consumed_qty:,.0f} {last.consumed_unit} of "
                         f"{last.entitlement_qty:,.0f} committed ({last.utilization_pct:g}% used); ")
                         + f"{last.per_user_rate:,.1f} {last.per_user_unit}"))
            peers = self._region_util(ln.product_code, self.acc.loc[self.acc.account_id == account_id, "ou"].iloc[0], account_id)
            if peers:
                r["vs_region"] = f"{peers[1]} other accounts in the same OU average {peers[0]:.1f}% utilization on this product"
            if ln.pricing_model == "seat" and 85 <= last3 <= 100:
                add = max(1, round(ln.licensed_qty * 0.10))
                r["expansion_calc"] = (f"+10% seats = {add:,} x net price ${ln.net_price_per_unit_yr:,.0f} = "
                                       f"${add * ln.net_price_per_unit_yr:,.0f} extra ACV (illustrative step)")
            if ln.pricing_model == "consumption" and last3 > 100:
                run_rate = c.consumed_qty.tail(3).mean() * 12
                qty = run_rate - ln.licensed_qty
                r["true_up_calc"] = (f"trailing-3-month run rate x 12 = {run_rate:,.0f}; committed {ln.licensed_qty:,.0f}; "
                                     f"true-up qty = {qty:,.0f} x net price ${ln.net_price_per_unit_yr:g} = ${qty * ln.net_price_per_unit_yr:,.0f} ACV")
            rows.append(r)
        return rows

    def _region_util(self, code, ou, exclude_id):
        """Average last-3-month utilization of one product across the OTHER accounts in the same OU."""
        ids = set(self.acc[(self.acc.ou == ou) & (self.acc.account_id != exclude_id)].account_id)
        c = self.cons[(self.cons.product_code == code) & (self.cons.account_id.isin(ids))]
        if c.empty:
            return None
        per_acc = c.sort_values("month").groupby("account_id").utilization_pct.apply(lambda s: s.tail(3).mean())
        return per_acc.mean(), len(per_acc)

    def cross_sell_estimates(self, account_id, top=3):
        """Products this account does NOT own, ranked by how many same-OU peers own them.
        Estimated ACV = median (peer line ACV / peer employees) x this account's employees. All in code, no LLM."""
        a = self.acc[self.acc.account_id == account_id].iloc[0]
        owned = set(self.lines[self.lines.account_id == account_id].product_code)
        peers = self.acc[(self.acc.ou == a.ou) & (self.acc.account_id != account_id)]
        pl = self.lines[self.lines.account_id.isin(peers.account_id)].merge(peers[["account_id", "employees"]], on="account_id")
        out = []
        for code, g in pl[~pl.product_code.isin(owned)].groupby("product_code"):
            if len(g) < 2:
                continue                                   # too few peers to estimate honestly
            per_emp = (g.line_acv_usd / g.employees).median()
            out.append((len(g), code, g.product_name.iloc[0], per_emp, per_emp * a.employees))
        out.sort(key=lambda x: (-x[0], -x[4]))
        return [f"{name}: owned by {n} of {len(peers)} other {a.ou} accounts; est. ACV = median peer ACV per employee "
                f"${per_emp:,.2f} x {a.employees:,} employees = ${est:,.0f} (estimate from peer data, not a quote)"
                for n, code, name, per_emp, est in out[:top]]

    @staticmethod
    def fiscal_year(d):
        """Cloudpaw FY runs Feb 1 - Jan 31 and is named by the year it ends (Feb 2026 - Jan 2027 = FY27)."""
        return f"FY{(d.year + (1 if d.month >= 2 else 0)) % 100:02d}"

    def account_brief_data(self, account_id):
        a = self.acc[self.acc.account_id == account_id].iloc[0]
        ae = self.ae[self.ae.ae_id == a.owner_ae_id].iloc[0]
        end = date.fromisoformat(a.contract_end)
        days = (end - config.TODAY).days
        before = {n: (end - timedelta(days=n)) for n in (30, 45, 60, 90, 120)}
        lines = [
            f"ACCOUNT: {a.account_name} ({a.account_id})",
            f"OU: {a.ou} | Country: {a.country} | Segment: {a.segment} ({a.employees:,} employees) | Industry: {a.industry} | Nature: {a.nature_of_business}",
            f"Contract: {a.contract_start} to {a.contract_end} ({a.term_months} months) | Current ACV: ${a.current_acv_usd:,.0f} | Auto-renew: {a.auto_renew}",
            f"Today: {config.TODAY} (in {self.fiscal_year(config.TODAY)}) | Days to contract end: {days} | "
            f"The renewal books in {self.fiscal_year(end)} (Cloudpaw FY = Feb 1 to Jan 31)",
            "Dates N days before contract end (use with the OU's notice period / program rules): "
            + "; ".join(f"{n}d = {dt} ({'PASSED' if dt < config.TODAY else 'upcoming'})" for n, dt in before.items()),
            f"Health: {a.health_score} ({a.health_band}) | Exec sponsor changed: {a.exec_sponsor_changed} | Open P1 cases: {a.open_p1_cases}",
            f"Owner AE: {ae.ae_name} ({ae.ae_id}) | FY27 quota ${ae.fy27_quota_usd:,.0f} | Attainment to date {ae.attainment_ytd_pct}%",
        ]
        lines += rules_block(a)[0]
        lines.append("PRODUCTS AND CONSUMPTION (owned products only):")
        for p in self.product_signals(account_id):
            lines.append("  - " + "; ".join(f"{k}: {v}" for k, v in p.items()))
        lines.append("CROSS-SELL ESTIMATES (products not owned, computed from same-OU peer data):")
        lines += ["  - " + x for x in self.cross_sell_estimates(account_id)] or ["  - none with enough peer data"]
        return "\n".join(lines), a.ou, a

    def facts_markdown(self, account_id):
        """Sections 2 and 3 of a strategy, built in code so they look the same every time (no LLM)."""
        a = self.acc[self.acc.account_id == account_id].iloc[0]
        ae = self.ae[self.ae.ae_id == a.owner_ae_id].iloc[0]
        end = date.fromisoformat(a.contract_end)
        r = rules_block(a)[1]
        rows = [("OU / country", f"{a.ou} / {a.country}"), ("Segment / industry", f"{a.segment} / {a.industry}"),
                ("Contract", f"{a.contract_start} to {a.contract_end} ({a.term_months} months)"),
                ("Days to contract end", f"{(end - config.TODAY).days} (books in {self.fiscal_year(end)})"),
                ("Notice date", f"{r['notice_date']} ({r['notice_days']} days, {'PASSED' if r['notice_passed'] else 'upcoming'}) [{r['notice_doc']}]"),
                ("Uplift cap", f"{r['uplift_cap']} [{r['uplift_doc']}]"),
                ("Health play", health_play(a)),
                ("Current ACV", f"${a.current_acv_usd:,.0f}"), ("Auto-renew", "Yes" if str(a.auto_renew) == "True" else "No"),
                ("Health", f"{a.health_score} ({a.health_band})"),
                ("Exec sponsor changed / open P1 cases", f"{'Yes' if str(a.exec_sponsor_changed) == 'True' else 'No'} / {a.open_p1_cases}"),
                ("Owner AE", f"{ae.ae_name}, {ae.attainment_ytd_pct}% of FY27 quota ${ae.fy27_quota_usd:,.0f}")]
        out = ["## 2. Account snapshot", "", "| Item | Value | Source |", "|---|---|---|"]
        for k, v in rows:
            cites = re.findall(r"\[([A-Z]+-[A-Z]+-\d{3})\]", v)          # move [DOC-IDs] into the Source column
            text = re.sub(r"\s*\[[A-Z]+-[A-Z]+-\d{3}\]", "", v)
            out.append(f"| {k} | {text} | {' '.join(f'[{c}]' for c in cites) or '[Account data]'} |")
        out += ["", "## 3. Health and consumption", "",
                "| Product | Licensed | Used (last 3 months) | Trend | Band | Region average | Source |",
                "|---|---|---|---|---|---|---|"]
        for p in self.product_signals(account_id):
            region = p.get("vs_region", "").split(" average ")[-1].replace(" utilization on this product", "") or "n/a"
            out.append(f"| {p['product']} | {p['licensed']} | {p['util_last3']}% | {p['trend']} | {p['band']} | {region} | [Account data] |")
        return "\n".join(out)

    def ae_portfolio_data(self, ae_id):
        ae = self.ae[self.ae.ae_id == ae_id].iloc[0]
        lines = [f"AE: {ae.ae_name} ({ae.ae_id}) | OU: {ae.ou} | Focus: {ae.segment_focus} | "
                 f"Quota ${ae.fy27_quota_usd:,.0f} | Attainment {ae.attainment_ytd_pct}% | Today: {config.TODAY}",
                 "ACCOUNTS OWNED:"]
        for _, a in self.acc[self.acc.owner_ae_id == ae_id].sort_values("contract_end").iterrows():
            days = (date.fromisoformat(a.contract_end) - config.TODAY).days
            prods = ", ".join(f"{p['code']} {p['util_last3']}% {p['band']}" for p in self.product_signals(a.account_id))
            lines.append(f"  - {a.account_name}: ends {a.contract_end} (in {days} days), ACV ${a.current_acv_usd:,.0f}, "
                         f"health {a.health_score} {a.health_band}, products: {prods}")
        return "\n".join(lines), ae.ou
