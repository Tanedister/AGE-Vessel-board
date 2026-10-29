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
STAGE_LABEL = {"At sea": "Sailing"}
STATUS_LABEL = {"Watch": "Monitor"}
MILES = ["eta_lp", "comm_l", "comp_l", "etd_lp", "eta_dp", "comm_d", "comp_d"]
HEAD = ["ETA LP", "COMM L", "COMP L", "ETD LP", "ETA DP", "COMM D", "COMP D"]
e = lambda s: html.escape(str(s if s is not None else ""))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def two_line(s):
    # "12 Oct 02:42" -> date on top, time below, so milestone columns stay narrow on a TV
    parts = s.split(" ")
    if len(parts) >= 3:
        return f'{e(" ".join(parts[:2]))}<br><span class="tm">{e(" ".join(parts[2:]))}</span>'
    return e(s)


def cell(v):
    s = str(v or "").strip()
    if not s:
        return '<td class="t nil">&mdash;</td>'
    if s.startswith("E "):
        return f'<td class="t est">{two_line(s[2:])}</td>'
    return f'<td class="t">{two_line(s)}</td>'


def next_idx(v):
    if v.get("stage") == "Completed":
        return -1
    for i, k in enumerate(MILES):
        s = str(v.get(k) or "").strip()
        if not s or s.startswith("E "):
            return i
    return -1


def dh(h):
    h = num(h)
    if h is None:
        return None
    m = int(round(abs(h) * 60))
    d, r = divmod(m, 1440)
    return f"{d}d {r // 60:02d}h" if d else f"{r // 60}h {r % 60:02d}m"


def laytime_line(v):
    lt = v.get("laytime") or {}
    if v.get("stage") not in ("Loading", "Discharging") or not lt:
        return ""
    used, rain, left, allowed = dh(lt.get("used_h")), dh(lt.get("rain_h")), num(lt.get("left_h")), dh(lt.get("allowed_h"))
    parts = []
    if used:
        parts.append(f"Laytime used <b>{used}</b>" + (f" / {allowed}" if allowed else ""))
    if rain and num(lt.get("rain_h")):
        parts.append(f"rain {rain}")
    if left is not None:
        parts.append(f'<b class="ov">On demurrage {dh(left)}</b>' if left < 0 else f"left <b>{dh(left)}</b>")
    elif used:
        parts.append("terms TBC")
    if not parts:
        return ""
    basis = e(lt.get("basis") or "")
    return f'<div class="lt">{" · ".join(parts)}{f" <span>({basis})</span>" if basis else ""}</div>'


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
        why = f'<div class="why">{e(v.get("reason"))}</div>' if flag in ("watch", "alert") and v.get("reason") else ""
        rows.append(
            f'<tr class="{flag}"><td class="v"><b>{"" if tb else "MV "}{e(v.get("vessel"))}</b> <em>{e(v.get("owners"))}</em>'
            f'<div class="m">{e(v.get("shipment") or "—")} · {e(v.get("laycan") or "—")}</div>'
            f'<div class="rt">{e(v.get("load_port") or "—")} &rarr; {e(v.get("disch_port") or "—")}</div></td>'
                        f'<td><span class="sg {STAGE_CLS.get(v.get("stage"), "pre")}">{e(STAGE_LABEL.get(v.get("stage"), v.get("stage")) or "—")}</span></td>'
            f'{miles}<td class="q">{qty}</td>'
            f'<td><span class="st {flag}">{e(STATUS_LABEL.get(v.get("status"), v.get("status")) or "—")}</span></td>'
            f'<td class="r">{why}{laytime_line(v)}{e(v.get("remark") or "")}</td></tr>'
        )
    if not rows:
        rows.append('<tr><td colspan="12" class="nil" style="padding:40px;text-align:center">ไม่มีเรือ active</td></tr>')
    attn_html = " &nbsp;•&nbsp; ".join(f'<b>{e(v.get("vessel"))}</b> {e(v.get("reason") or v.get("remark") or v.get("status"))}' for v in attn) or "ทุกลำ On track"
    notice = st.get("notice") or ""
    page = f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<meta name="robots" content="noindex,nofollow">
<title>AGE Vessel Board</title>
<style>
body{{margin:0;background:#0b1622;color:#e8eef4;font-family:Tahoma,"Segoe UI",sans-serif;font-size:22px}}
.w{{padding:18px 24px}}
h1{{margin:0;font-size:46px;letter-spacing:2px}} h1 span{{background:#2fb37a;color:#0b1622;padding:2px 8px;border-radius:4px;margin-right:10px}}
.top{{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px;margin-bottom:12px}}
.u{{color:#7f94a8;text-align:right;font-size:20px}} .u b{{color:#f2b84b;font-size:28px}}
.c{{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}} .c div{{background:#112131;padding:6px 14px;border-left:4px solid #7f94a8;color:#7f94a8;text-transform:uppercase;font-size:19px}}
.c b{{color:#e8eef4;font-size:36px;margin-left:8px}}
table{{border-collapse:collapse;width:100%;table-layout:auto;background:#112131}} td.r{{width:18%}} td.v{{width:21%}}
th{{color:#7f94a8;font-size:17px;text-align:left;padding:10px 8px;border-bottom:2px solid #1f3448;text-transform:uppercase;white-space:nowrap}}
td{{padding:13px 8px;border-bottom:1px solid #1f3448;vertical-align:middle}}
tr.watch td.v{{border-left:5px solid #f2b84b}} tr.alert td.v{{border-left:5px solid #ff5b5b}} tr.ok td.v{{border-left:5px solid #3ccf7e}} tr.done td.v{{border-left:5px solid #5f7387}}
.v b{{font-size:26px}} .v em{{color:#7f94a8;font-style:normal;font-size:18px}} .m{{color:#7f94a8;font-size:16px;font-family:monospace}}
.t{{font-family:Consolas,monospace;white-space:nowrap;font-size:21px;line-height:1.25}} .tm{{opacity:.8}} .est{{color:#f2b84b;font-weight:bold}} .nil{{color:#3a5068}}
.sg{{border:1px solid;padding:3px 8px;border-radius:4px;font-size:18px;font-weight:bold;text-transform:uppercase;white-space:nowrap}}
.pre{{color:#8a9bb0}} .load{{color:#2fc4b2}} .sea{{color:#4aa3ff}} .dis{{color:#a98bff}} .done{{color:#9fb0c0}}
.q{{font-family:Consolas,monospace;white-space:nowrap;font-size:21px}} .q span{{color:#7f94a8}}
.bar{{height:9px;background:#1f3448;border-radius:3px;margin-top:4px}} .bar i{{display:block;height:9px;background:#2fb37a;border-radius:3px}}
.st{{padding:4px 10px;border-radius:14px;font-weight:bold;font-size:18px;white-space:nowrap}}
.st.ok{{background:#12352a;color:#3ccf7e}} .st.watch{{background:#3a2f12;color:#f2b84b}} .st.alert{{background:#3d1717;color:#ff5b5b}} .st.done{{background:#1d2a36;color:#c8d3dd}}
.r{{color:#b8c6d3;font-size:18px}} .why{{color:#f2b84b;font-weight:bold;margin-bottom:4px}} .lt{{color:#e8eef4;margin-bottom:4px}} .lt span{{color:#7f94a8}} .lt .ov{{color:#ff5b5b}} .rt{{color:#b8c6d3;font-size:17px;margin-top:2px}}
.a{{margin-top:12px;background:#112131;padding:14px 18px;font-size:22px}} .a b{{color:#f2b84b}}
.n{{background:#3a2f12;color:#f2b84b;font-size:22px;padding:10px 16px;margin-bottom:10px}}
.f{{color:#7f94a8;font-size:16px;margin-top:8px}}
</style></head><body><div class="w">
<div class="top"><h1><span>AGE</span>VESSEL BOARD</h1>
<div class="u">Last updated <b>{e(u)}</b><br>Updates 09:00 · 12:00 · 15:00 (workdays) · page reloads every 5 min</div></div>
{f'<div class="n">{e(notice)}</div>' if notice else ''}
<div class="c"><div>Active<b>{sum(1 for v in vs if v.get("stage") != "Completed")}</b></div><div>Pre-arrival<b>{cnt("Pre-arrival")}</b></div>
<div>Loading<b>{cnt("Loading")}</b></div><div>Sailing<b>{cnt("At sea")}</b></div><div>Discharging<b>{cnt("Discharging")}</b></div>
<div>Completed<b>{cnt("Completed")}</b></div><div style="border-color:#ff5b5b">Attention<b>{len(attn)}</b></div></div>
<table><tr><th>Vessel / Route</th><th>Stage</th>{''.join(f'<th>{h}</th>' for h in HEAD)}<th>Cargo MT</th><th>Status</th><th>Remark</th></tr>
{''.join(rows)}</table>
<div class="a">Needs attention: {attn_html}</div>
<div class="f"><span class="est">Amber</span> = estimate · shaded = next milestone · port local time · source: agent / owners reports · generated by Claude</div>
</div></body></html>"""
    import re
    page = re.sub(r"(font-size|padding|gap|height|margin-top|margin-bottom|border-left|border-radius):([^;}]*)",
                  lambda m: m.group(1) + ":" + re.sub(r"(\d+(?:\.\d+)?)px", lambda n: f"{float(n.group(1))/19.2:.3f}vw", m.group(2)), page)
    open(dst, "w", encoding="utf-8").write(page)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
