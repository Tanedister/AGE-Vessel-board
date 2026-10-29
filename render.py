#!/usr/bin/env python3
"""Render the lightweight public TV page (index.html) from the AGE Vessel Board state JSON.

Usage: python3 render.py state.json index.html
Omits commercially sensitive fields (demurrage rates, lost-time split by party, notes).
Plain HTML + CSS, no JavaScript framework, so low-RAM TV browsers can load it.
"""
import html, json, sys
from datetime import datetime, timedelta, timezone

BKK = timezone(timedelta(hours=7))
ORDER = {"Completed": 0, "Discharging": 1, "At sea": 2, "Loading": 3, "Pre-arrival": 4}
STAGE_CLS = {"Pre-arrival": "pre", "Loading": "load", "At sea": "sea", "Discharging": "dis", "Completed": "done"}
MILES = ["eta_lp", "comm_l", "comp_l", "etd_lp", "eta_dp", "comm_d", "comp_d"]
HEAD = ["ETA LP", "COMM L", "COMP L", "ETD LP", "ETA DP", "COMM D", "COMP D"]
e = lambda s: html.escape(str(s if s is not None else ""))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cell(v):
    s = str(v or "").strip()
    if not s:
        return '<td class="t nil">&mdash;</td>'
    if s.startswith("E "):
        return f'<td class="t est">{e(s[2:])}</td>'
    return f'<td class="t">{e(s)}</td>'


def next_idx(v):
    if v.get("stage") == "Completed":
        return -1
    for i, k in enumerate(MILES):
        s = str(v.get(k) or "").strip()
        if not s or s.startswith("E "):
            return i
    return -1


def main(src, dst):
    st = json.load(open(src, encoding="utf-8"))
    vs = sorted(st.get("vessels", []), key=lambda v: ORDER.get(v.get("stage"), 9))
    upd = st.get("updated_at") or ""
    try:
        u = datetime.fromisoformat(upd).astimezone(BKK).strftime("%a %d %b %Y %H:%M")
    except ValueError:
        u = upd
    cnt = lambda s: sum(1 for v in vs if v.get("stage") == s)
    attn = [v for v in vs if v.get("flag") in ("watch", "alert")]
    rows = []
    for v in vs:
        ni = next_idx(v)
        flag = v.get("flag") if v.get("flag") in ("ok", "watch", "alert", "done") else "ok"
        tb = str(v.get("vessel", "")).upper().startswith("TB ")
        cargo = num(v.get("cargo_mt")) or num(v.get("bl_qty"))
        done = num(v.get("done_mt"))
        if cargo and v.get("stage") in ("Loading", "Discharging") and done is not None:
            pct = min(100, done / cargo * 100)
            qty = f'{done:,.0f}<span> / {cargo:,.0f}</span><div class="bar"><i style="width:{pct:.0f}%"></i></div>'
        elif cargo:
            qty = f"{cargo:,.0f}<span> MT</span>"
        else:
            qty = "&mdash;"
        miles = "".join(
            cell(v.get(k)).replace("<td ", '<td style="background:#2a2614" ', 1) if i == ni else cell(v.get(k))
            for i, k in enumerate(MILES)
        )
        rows.append(
            f'<tr class="{flag}"><td class="v"><b>{"" if tb else "MV "}{e(v.get("vessel"))}</b> <em>{e(v.get("owners"))}</em>'
            f'<div class="m">{e(v.get("shipment") or "—")} · {e(v.get("laycan") or "—")}</div></td>'
            f'<td>{e(v.get("load_port") or "—")} &rarr; {e(v.get("disch_port") or "—")}</td>'
            f'<td><span class="sg {STAGE_CLS.get(v.get("stage"), "pre")}">{e(v.get("stage") or "—")}</span></td>'
            f'{miles}<td class="q">{qty}</td>'
            f'<td><span class="st {flag}">{e(v.get("status") or "—")}</span></td>'
            f'<td class="r">{e(v.get("remark") or "")}</td></tr>'
        )
    if not rows:
        rows.append('<tr><td colspan="13" class="nil" style="padding:40px;text-align:center">ไม่มีเรือ active</td></tr>')
    attn_html = " &nbsp;•&nbsp; ".join(f'<b>{e(v.get("vessel"))}</b> {e(v.get("remark") or v.get("status"))}' for v in attn) or "ทุกลำ On track"
    notice = st.get("notice") or ""
    page = f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<meta name="robots" content="noindex,nofollow">
<title>AGE Vessel Board</title>
<style>
body{{margin:0;background:#0b1622;color:#e8eef4;font-family:Tahoma,"Segoe UI",sans-serif;font-size:15px}}
.w{{padding:14px 18px}}
h1{{margin:0;font-size:30px;letter-spacing:2px}} h1 span{{background:#2fb37a;color:#0b1622;padding:2px 8px;border-radius:4px;margin-right:10px}}
.top{{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px;margin-bottom:12px}}
.u{{color:#7f94a8;text-align:right;font-size:14px}} .u b{{color:#f2b84b;font-size:18px}}
.c{{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}} .c div{{background:#112131;padding:6px 14px;border-left:4px solid #7f94a8;color:#7f94a8;text-transform:uppercase;font-size:13px}}
.c b{{color:#e8eef4;font-size:24px;margin-left:8px}}
table{{border-collapse:collapse;width:100%;background:#112131}}
th{{color:#7f94a8;font-size:12px;text-align:left;padding:8px 6px;border-bottom:2px solid #1f3448;text-transform:uppercase;white-space:nowrap}}
td{{padding:9px 6px;border-bottom:1px solid #1f3448;vertical-align:middle}}
tr.watch td.v{{border-left:5px solid #f2b84b}} tr.alert td.v{{border-left:5px solid #ff5b5b}} tr.ok td.v{{border-left:5px solid #3ccf7e}} tr.done td.v{{border-left:5px solid #5f7387}}
.v b{{font-size:19px;white-space:nowrap}} .v em{{color:#7f94a8;font-style:normal;font-size:13px}} .m{{color:#7f94a8;font-size:12px;font-family:monospace}}
.t{{font-family:Consolas,monospace;white-space:nowrap;font-size:14px}} .est{{color:#f2b84b;font-weight:bold}} .nil{{color:#3a5068}}
.sg{{border:1px solid;padding:3px 8px;border-radius:4px;font-size:13px;font-weight:bold;text-transform:uppercase;white-space:nowrap}}
.pre{{color:#8a9bb0}} .load{{color:#2fc4b2}} .sea{{color:#4aa3ff}} .dis{{color:#a98bff}} .done{{color:#9fb0c0}}
.q{{font-family:Consolas,monospace;white-space:nowrap;font-size:14px}} .q span{{color:#7f94a8}}
.bar{{height:6px;background:#1f3448;border-radius:3px;margin-top:4px}} .bar i{{display:block;height:6px;background:#2fb37a;border-radius:3px}}
.st{{padding:4px 10px;border-radius:12px;font-weight:bold;font-size:13px;white-space:nowrap}}
.st.ok{{background:#12352a;color:#3ccf7e}} .st.watch{{background:#3a2f12;color:#f2b84b}} .st.alert{{background:#3d1717;color:#ff5b5b}} .st.done{{background:#1d2a36;color:#c8d3dd}}
.r{{color:#b8c6d3;font-size:13px;max-width:260px}}
.a{{margin-top:12px;background:#112131;padding:10px 14px;font-size:15px}} .a b{{color:#f2b84b}}
.n{{background:#3a2f12;color:#f2b84b;padding:8px 14px;margin-bottom:10px}}
.f{{color:#7f94a8;font-size:12px;margin-top:8px}}
</style></head><body><div class="w">
<div class="top"><h1><span>AGE</span>VESSEL BOARD</h1>
<div class="u">Last updated <b>{e(u)}</b><br>Updates 09:00 · 12:00 · 15:00 (workdays) · page reloads every 5 min</div></div>
{f'<div class="n">{e(notice)}</div>' if notice else ''}
<div class="c"><div>Active<b>{sum(1 for v in vs if v.get("stage") != "Completed")}</b></div><div>Pre-arrival<b>{cnt("Pre-arrival")}</b></div>
<div>Loading<b>{cnt("Loading")}</b></div><div>At sea<b>{cnt("At sea")}</b></div><div>Discharging<b>{cnt("Discharging")}</b></div>
<div>Completed<b>{cnt("Completed")}</b></div><div style="border-color:#ff5b5b">Attention<b>{len(attn)}</b></div></div>
<table><tr><th>Vessel</th><th>Route</th><th>Stage</th>{''.join(f'<th>{h}</th>' for h in HEAD)}<th>Cargo MT</th><th>Status</th><th>Remark</th></tr>
{''.join(rows)}</table>
<div class="a">Needs attention: {attn_html}</div>
<div class="f"><span class="est">Amber</span> = estimate · shaded = next milestone · port local time · source: agent / owners reports · generated by Claude</div>
</div></body></html>"""
    open(dst, "w", encoding="utf-8").write(page)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
