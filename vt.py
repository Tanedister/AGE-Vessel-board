#!/usr/bin/env python3
"""AGE Vessel Tracker helper - keeps the routine work out of the model's context.

  python3 -B vt.py show  STATE.json [VESSEL]        compact view of the board state (+ round / holiday check)
  python3 -B vt.py text  FILE [MAXCHARS] [--all]    readable text of a saved Outlook message (HTML stripped, quoted thread cut)
  python3 -B vt.py build STATE.json PATCH.json OUTDIR [--url DASHBOARD_URL]
        applies the patch, recalculates hours / laytime / lost time, writes OUTDIR/board.json,
        renders index.html (TV page, next to this script) and OUTDIR/email.html + email.txt

No vessel data lives in this file - it only holds logic and layout.

PATCH.json (every key optional):
{ "vessels": {"<VESSEL>": {"<field>": value, ...}},      merge into an existing vessel ("laytime" is merged key by key; null clears it)
  "add":     [{...full vessel object...}],                new vessel (only after nomination + both acceptances)
  "remove":  ["<VESSEL>"],
  "events":  [{"id","vessel","start","end","cause","side","hours"?}],   upsert by id; hours = end-start when omitted
  "pending": [...],                                       replaces the whole pending list
  "notice":  "", "no_new": true }
Times are port local, "DD Mon HH:MM"; estimates start with "E ".
laytime = {"basis","allowed_h","start","as_of"}: with "start" the script works out used_h / rain_h / left_h and
laytime_expiry itself (deducting this vessel's Weather and Owners events that begin on/after start).
An event whose cause ends with "(ongoing)" is extended to now (vessel "tz", hours from UTC) on every build.
"""
import html, json, os, re, sys

sys.dont_write_bytecode = True
from datetime import datetime, timedelta, timezone

BKK = timezone(timedelta(hours=7))
HOLIDAYS = {"2026-01-01", "2026-01-02", "2026-03-03", "2026-04-06", "2026-04-13", "2026-04-14", "2026-04-15", "2026-05-01",
            "2026-06-03", "2026-07-28", "2026-07-29", "2026-08-12", "2026-10-13", "2026-10-23", "2026-12-07", "2026-12-31"}
EMAIL_HOURS = {9: "เช้า", 15: "บ่าย"}
MILES = ["eta_lp", "comm_l", "comp_l", "etd_lp", "eta_dp", "comm_d", "comp_d"]
MLAB = ["ETA LP", "COMM L", "COMP L", "ETD LP", "ETA DP", "COMM D", "COMP D"]
ORDER = {"Completed": 0, "Discharging": 1, "At sea": 2, "Loading": 3, "Pre-arrival": 4}
SHOW = ["Completed", "Discharging", "Waiting Discharge", "Laden", "Loading", "Waiting Load", "Ballast"]
FLAG = {"On track": "ok", "Monitor": "watch", "Caution!": "alert", "Alert": "alert", "Done": "done"}
SIDES = {"Shipper": "shipper", "Receiver / charterers": "receiver", "Owners": "owners", "Weather": "weather"}
TZ_HINT = [("shakhtersk", 11), ("taboneo", 8), ("bunati", 8), ("bunyu", 8), ("kaliorang", 8), ("adang", 8), ("samarinda", 8),
           ("balikpapan", 8), ("muara", 8)]
MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
TH_MON = "ม.ค. ก.พ. มี.ค. เม.ย. พ.ค. มิ.ย. ก.ค. ส.ค. ก.ย. ต.ค. พ.ย. ธ.ค.".split()


def now_bkk():
    return datetime.now(timezone.utc).astimezone(BKK)


def load(p):
    d = json.load(open(p, encoding="utf-8"))
    return d.get("data", d) if isinstance(d.get("data"), dict) and "vessels" in d.get("data", {}) else d


def actual(x):
    s = str(x or "").strip()
    return bool(s) and not s.startswith("E ")


def stage(v):
    st = v.get("stage")
    if st == "Discharging":
        return "Discharging" if actual(v.get("comm_d")) else "Waiting Discharge"
    if st == "Loading":
        return "Loading" if actual(v.get("comm_l")) else "Waiting Load"
    if st == "At sea":
        if actual(v.get("eta_dp")) and not actual(v.get("comm_d")):
            return "Waiting Discharge"
        return "Laden" if (actual(v.get("comm_l")) or actual(v.get("etd_lp"))) else "Ballast"
    if st == "Pre-arrival":
        return "Waiting Load" if actual(v.get("eta_lp")) else "Ballast"
    return st or "Ballast"


def tz_of(v):
    if isinstance(v.get("tz"), (int, float)):
        return v["tz"]
    at_lp = v.get("stage") in ("Pre-arrival", "Loading")
    where = (str(v.get("load_port") if at_lp else v.get("disch_port")) + " " + str(v.get("port"))).lower()
    for k, off in TZ_HINT:
        if k in where:
            return off
    return 7


def parse(s, ref):
    """'E 06 Nov 20:18' / '06 Nov 20:18' -> naive datetime (year taken from ref); None if no clock time."""
    m = re.search(r"(\d{1,2}) ([A-Z][a-z]{2}) (\d{1,2}):(\d{2})", str(s or ""))
    if not m or m.group(2) not in MON:
        return None
    d = datetime(ref.year, MON.index(m.group(2)) + 1, int(m.group(1)), int(m.group(3)), int(m.group(4)))
    if d - ref > timedelta(days=200):
        d = d.replace(year=ref.year - 1)
    elif ref - d > timedelta(days=200):
        d = d.replace(year=ref.year + 1)
    return d


def fmt(d):
    return d.strftime("%d %b %H:%M")


def dh(h):
    if h in ("", None):
        return "—"
    m = int(round(abs(h) * 60))
    d, r = divmod(m, 1440)
    return f"{d}d {r // 60}h" if d else f"{r // 60}h {r % 60:02d}m"


def round_info(now=None):
    now = now or now_bkk()
    r = now + timedelta(minutes=15)
    hour = r.hour
    skip = now.weekday() >= 5 or now.strftime("%Y-%m-%d") in HOLIDAYS
    name = EMAIL_HOURS.get(hour, "")
    label = f"{r.day} {MON[r.month - 1]} {r.year} {hour:02d}:00" + (f" · {name}" if name else "")
    return {"skip": skip, "email": bool(name) and not skip, "name": name, "label": label, "now": now, "hour": hour}


# ---------------------------------------------------------------- show
def cmd_show(path, only=None):
    st = load(path)
    ri = round_info()
    if ri["skip"]:
        print("SKIP - AGE holiday / weekend. Reply 'Skipped — AGE holiday' and stop.")
        return
    print(f"ROUND {ri['label']} | team email this round: {'YES' if ri['email'] else 'no'}")
    upd = st.get("updated_at") or ""
    try:
        after = (datetime.fromisoformat(upd) - timedelta(minutes=20)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")
    except ValueError:
        after = "yesterday"
    print(f"last update {upd} ({st.get('run_label', '')}) -> Outlook afterDateTime: {after}")
    if st.get("notice"):
        print("notice:", st["notice"])
    for v in st.get("vessels", []):
        if only and only.lower() not in v["vessel"].lower():
            continue
        if only:
            print(json.dumps(v, ensure_ascii=False, indent=1))
            continue
        lt = v.get("laytime") or {}
        print(f"\n[{v['vessel']}] {v.get('owners', '')} {v.get('shipment', '')} | {stage(v)} (stage {v.get('stage')}) | "
              f"{v.get('status')} | as_of {v.get('as_of')} | tz+{tz_of(v)} | {v.get('load_port')} -> {v.get('disch_port')}")
        print("  " + " ".join(f"{k}={v.get(k) or '-'};" for k in MILES))
        print(f"  cargo {v.get('cargo_mt')} done {v.get('done_mt')} bal {v.get('balance_mt')} bl {v.get('bl_qty') or '-'} | "
              f"dem {v.get('dem_rate') or 'MISSING'} | laytime {json.dumps(lt, ensure_ascii=False) if lt else '-'} "
              f"exp {v.get('laytime_expiry') or '-'}")
        if v.get("reason"):
            print("  reason:", v["reason"])
        print("  remark:", v.get("remark", ""), "| last:", v.get("last_report", ""))
        note = str(v.get("note", ""))
        print("  note:", note[:260] + ("…" if len(note) > 260 else ""))
    if only:
        return
    print("\nEVENTS (id | vessel | start -> end | h | side | cause)")
    for e in st.get("events", []):
        print(f"  {e['id']} | {e['vessel']} | {e['start']} -> {e['end']} | {e['hours']} | {e['side']} | {e['cause']}")
    print("\nPENDING (not on the board)")
    for p in st.get("pending", []):
        print(f"  {p.get('vessel')} | {p.get('shipment')} | nominated={p.get('nominated')} shipper_accepted={p.get('shipper_accepted')} "
              f"receiver_accepted={p.get('receiver_accepted')} | {str(p.get('note', ''))[:160]}")


# ---------------------------------------------------------------- text
def cmd_text(path, limit=5000, whole=False):
    raw = open(path, encoding="utf-8", errors="replace").read()
    head = ""
    try:
        d = json.loads(raw)
        body = (d.get("body") or {}).get("content") or d.get("bodyPreview") or ""
        rec = d.get("receivedDateTime", "")
        try:
            rec = datetime.fromisoformat(rec.replace("Z", "+00:00")).astimezone(BKK).strftime("%d %b %H:%M BKK")
        except ValueError:
            pass
        att = ", ".join(a.get("name", "") for a in d.get("attachments") or [])
        head = f"SUBJECT: {d.get('subject')}\nFROM: {(d.get('sender') or {}).get('address')} | {rec}" + (f"\nATTACH: {att}" if att else "") + "\n---\n"
    except (ValueError, AttributeError):
        body = raw
    t = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", "", body)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>|</li>", "\n", t)
    t = re.sub(r"(?i)</td>", " | ", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r"\n[ |]*\n+", "\n", t).strip()
    if not whole:
        m = re.search(r"\n(From:|จาก:|-{3,} ?Original Message|On .{5,90} wrote:|-----Original)", t[150:])
        if m:
            t = t[:150 + m.start()] + "\n[older quoted thread cut - add --all to see it]"
    print(head + t[:limit] + ("\n[cut at %d chars]" % limit if len(t) > limit else ""))


# ---------------------------------------------------------------- build
def apply_patch(st, patch, ri):
    now = ri["now"]
    warn, info = [], []
    vs = st.setdefault("vessels", [])
    by = {v["vessel"]: v for v in vs}
    for name in patch.get("remove", []):
        if name in by:
            vs.remove(by.pop(name))
            st["events"] = [e for e in st.get("events", []) if e["vessel"] != name]
            info.append(f"removed {name}")
    for v in patch.get("add", []):
        if v["vessel"] in by:
            by[v["vessel"]].update(v)
        else:
            vs.append(v)
            by[v["vessel"]] = v
            info.append(f"added {v['vessel']}")
    for name, ch in (patch.get("vessels") or {}).items():
        v = by.get(name) or next((x for k, x in by.items() if name.lower() in k.lower()), None)
        if not v:
            warn.append(f"patch vessel '{name}' is not on the board (use \"add\")")
            continue
        for k, val in ch.items():
            if k == "laytime" and isinstance(val, dict) and val and isinstance(v.get("laytime"), dict):
                v["laytime"].update(val)
            else:
                if k == "note" and len(str(v.get("note", ""))) > 400 and not v.get("info"):
                    v["info"] = v["note"]  # keep the long historical note once
                v[k] = val
    evs = st.setdefault("events", [])
    for e in patch.get("events", []):
        old = next((x for x in evs if x["id"] == e["id"]), None)
        if old:
            if "hours" not in e and ("start" in e or "end" in e):
                old.pop("hours", None)
            old.update(e)
        else:
            evs.append(e)
    if "pending" in patch:
        st["pending"] = patch["pending"]
    st.setdefault("pending", [])
    st["notice"] = patch.get("notice", "")

    # completed vessels drop off 24 h after completion
    for v in list(vs):
        loc = now.astimezone(timezone(timedelta(hours=tz_of(v)))).replace(tzinfo=None)
        cd = parse(v.get("comp_d"), loc) if actual(v.get("comp_d")) else None
        if v.get("stage") == "Completed" and cd and loc - cd > timedelta(hours=24):
            vs.remove(v)
            st["events"] = evs = [e for e in evs if e["vessel"] != v["vessel"]]
            info.append(f"removed {v['vessel']} (completed > 24 h ago)")

    by = {v["vessel"]: v for v in vs}
    for e in evs:
        v = by.get(e["vessel"])
        loc = now.astimezone(timezone(timedelta(hours=tz_of(v) if v else 7))).replace(tzinfo=None)
        ongoing = str(e.get("cause", "")).rstrip().endswith("(ongoing)")
        if ongoing:
            e["end"] = fmt(loc)
            e.pop("hours", None)
            if v:
                v["as_of"] = e["end"]
        if "hours" not in e:
            a, b = parse(e.get("start"), loc), parse(e.get("end"), loc)
            if a and b:
                e["hours"] = round((b - a).total_seconds() / 3600, 1)
            else:
                e["hours"] = 0
                warn.append(f"event {e['id']}: cannot compute hours from '{e.get('start')}' -> '{e.get('end')}'")
        if ongoing and v:
            h = e["hours"]
            v["reason"] = re.sub(r"(No cargo loaded(?: for)?) [\d.]+ ?h", rf"\1 {h:.0f} h", str(v.get("reason", "")))
            v["reason"] = re.sub(r"(No cargo loaded(?: for)?) [\d.]+ days", rf"\1 {h / 24:.1f} days", v["reason"])
            v["note"] = re.sub(r"(no cargo loaded for) [\d.]+ days", rf"\1 {h / 24:.1f} days", str(v.get("note", "")))
            info.append(f"ongoing {e['id']} {e['vessel']}: {h} h = {h / 24:.1f} days since {e['start']}"
                        + ("  ** over 72 h: status must be Caution! **" if h > 72 and v.get("status") != "Caution!"
                           and v.get("stage") in ("Pre-arrival", "Loading") else ""))

    for v in vs:
        loc = now.astimezone(timezone(timedelta(hours=tz_of(v)))).replace(tzinfo=None)
        v["flag"] = FLAG.get(v.get("status"), v.get("flag", "ok"))
        lt = v.get("laytime")
        if v.get("stage") not in ("Loading", "Discharging"):
            v["laytime"] = lt = {}
        if lt and lt.get("start") and lt.get("allowed_h") not in ("", None):
            a = parse(lt["start"], loc)
            done_key = "comp_l" if v["stage"] == "Loading" else "comp_d"
            b = parse(v.get(done_key), loc) if actual(v.get(done_key)) else parse(lt.get("as_of"), loc)
            if a and b:
                ded = {"Weather": 0.0, "Owners": 0.0}
                for e in evs:
                    es = parse(e.get("start"), loc)
                    if e["vessel"] == v["vessel"] and e["side"] in ded and es and es >= a:
                        ded[e["side"]] += e["hours"]
                used = max(0.0, (b - a).total_seconds() / 3600 - ded["Weather"] - ded["Owners"])
                lt.update(used_h=round(used, 1), rain_h=round(ded["Weather"], 1), left_h=round(lt["allowed_h"] - used, 1), as_of=fmt(b))
                exp = b + timedelta(hours=lt["left_h"])
                v["laytime_expiry"] = fmt(exp) if (lt["left_h"] < 0 or actual(v.get(done_key))) else "E " + fmt(exp)
            else:
                warn.append(f"{v['vessel']}: laytime start/as_of not parseable")
        elif v.get("stage") in ("Loading", "Discharging") and not (lt or {}).get("allowed_h"):
            warn.append(f"{v['vessel']}: laytime terms missing (allowed_h) - look for CP / recap")
        if v.get("status") in ("Monitor", "Caution!", "Alert") and not v.get("reason"):
            warn.append(f"{v['vessel']}: status {v['status']} needs a reason")
        if v.get("status") == "On track" and v.get("reason"):
            v["reason"] = ""
        for k in ("reason", "remark"):
            s = str(v.get(k, ""))
            if len(s) > 60:
                warn.append(f"{v['vessel']}: {k} is {len(s)} chars (max 60)")
            if re.search(r"USD|\$|PDPR", s):
                warn.append(f"{v['vessel']}: {k} shows money / dem rate - not allowed on the public TV page")
        if re.search(r"USD|\$", str((lt or {}).get("basis", ""))):
            warn.append(f"{v['vessel']}: laytime.basis shows money")
        if not v.get("dem_rate"):
            warn.append(f"{v['vessel']}: dem_rate missing")
        if len(str(v.get("note", ""))) > 400:
            warn.append(f"{v['vessel']}: note is long ({len(v['note'])} chars) - keep it to 1-2 sentences when you next change it")
        if isinstance(lt, dict) and lt.get("left_h") not in ("", None) and lt["left_h"] < 24 and v.get("status") == "On track" \
                and not actual(v.get("comp_l" if v["stage"] == "Loading" else "comp_d")):
            warn.append(f"{v['vessel']}: laytime left {lt['left_h']} h (< 24 h) - status should be at least Monitor")

    lost = {}
    for e in evs:
        row = lost.setdefault(e["vessel"], {"vessel": e["vessel"], "shipper": 0, "receiver": 0, "owners": 0, "weather": 0})
        k = SIDES.get(e.get("side"))
        if k:
            row[k] = round(row[k] + e["hours"], 1)
        else:
            warn.append(f"event {e['id']}: unknown side '{e.get('side')}'")
    st["lost_hours"] = list(lost.values())
    vs.sort(key=lambda v: ORDER.get(v.get("stage"), 9))
    st["updated_at"] = now.strftime("%Y-%m-%dT%H:%M:00+07:00")
    st["run_label"] = ri["label"]
    st["source"] = "Outlook daily reports via Microsoft 365"
    return warn, info


E = lambda s: html.escape(str(s), quote=False)
F = "font-family:Calibri,Tahoma,sans-serif;font-size:12pt;"
BD = "border:1px solid #D0D7DE;padding:5px 7px;"
RANK = {"Caution!": 0, "Alert": 1, "Monitor": 2}


def vname(v):
    return v["vessel"] if v["vessel"].upper().startswith("TB ") else "MV." + v["vessel"]


def lt_text(v):
    lt = v.get("laytime") or {}
    if not lt or lt.get("used_h") in ("", None):
        return ""
    left = lt.get("left_h")
    tail = "terms TBC" if left in ("", None) else (f"On demurrage {dh(left)}" if left < 0 else f"left {dh(left)}")
    return f"Laytime: used {dh(lt['used_h'])} / {dh(lt.get('allowed_h'))} · rain {lt.get('rain_h', 0)} h · {tail} ({lt.get('basis', '')})"


def make_email(st, ri, url, no_new):
    now = ri["now"]
    vs = sorted(st["vessels"], key=lambda v: SHOW.index(stage(v)) if stage(v) in SHOW else 9)
    fol = sorted([v for v in vs if v.get("status") in RANK], key=lambda v: RANK[v["status"]])
    caut = [v for v in vs if v.get("status") == "Caution!"]
    counts = " · ".join(f"{k} {n}" for k in SHOW if (n := sum(1 for v in vs if stage(v) == k)))
    date_th = f"{now.day} {TH_MON[now.month - 1]} {now.year}"
    subject = ("[Caution!] " if caut else "") + f"AGE Vessel Tracker — สถานะเรือ {date_th} {ri['name'] or f'{ri['hour']:02d}:00'}"
    p = lambda s, x="": f'<p style="{F}{x}">{s}</p>'
    th = lambda s: (f'<td bgcolor="#D5E8F0" style="{F}background-color:#D5E8F0;color:#1F4E79;font-weight:bold;border:1px solid #A9C4D6;'
                    f'padding:5px 7px;white-space:nowrap;"><b>{s}</b></td>')
    td = lambda s, x="", bg="": f'<td{f" bgcolor={chr(34)}{bg}{chr(34)}" if bg else ""} style="{F}{BD}{f"background-color:{bg};" if bg else ""}{x}">{s}</td>'
    tbl = '<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #D0D7DE;">'
    intro = f"สรุปสถานะเรือ AGE ณ วันที่ {date_th} เวลา {ri['hour']:02d}:00 น. (เวลาไทย) จาก daily report ของ agent และ owners ใน Outlook"
    h = [f'<div style="{F}">', p("เรียนทีม Chartering"), p(intro), p(f'ดูแบบ live: <a href="{E(url)}">AGE Vessel Board</a>')]
    t = ["เรียนทีม Chartering", "", intro, f"ดูแบบ live: AGE Vessel Board {url}", ""]
    for v in caut:
        ev = [e for e in st["events"] if e["vessel"] == v["vessel"] and str(e["cause"]).rstrip().endswith("(ongoing)")]
        line = (f"Caution! — {vname(v)} ไม่มีสินค้าลงเรือ {ev[-1]['hours'] / 24:.1f} วันต่อเนื่อง (ตั้งแต่ {ev[-1]['start']} LT)" if ev
                else f"Caution! — {vname(v)}: {v.get('reason', '')}")
        h.append(f'<div style="{F}background-color:#FDECEA;border-left:4px solid #C0392B;padding:8px 12px;margin:6px 0;color:#C0392B;"><b>{E(line)}</b></div>')
        t.append(line)
    summ = f"เรือ active {sum(1 for v in vs if v.get('stage') != 'Completed')} ลำ — {counts} | " + (
        f"ต้องติดตาม {len(fol)} ลำ: {', '.join(v['vessel'] for v in fol)}" if fol else "ทุกลำ On track")
    if no_new:
        summ += " | รอบนี้ไม่มี report ใหม่จาก agent — สถานะตามข้อมูลล่าสุด"
    h.append(f'<div style="{F}background-color:#E2EFDA;border-left:4px solid #009D53;padding:8px 12px;margin:6px 0;">{E(summ)}</div>')
    t += [summ, "", "Cargo movement (operation status)"]
    hd = lambda s: p(f"<b>{s}</b>", "color:#1F4E79;")
    cols = ["#", "Vessel / Owners", "Shipment no.", "Laycan", "Quantity (MT)", "B/L QTY (MT)", "Load Port", "ETA LP<br>ถึงท่าโหลด",
            "COMM L<br>เริ่มโหลด", "COMP L<br>โหลดเสร็จ", "ETD LP<br>ออกจากท่าโหลด", "ETA DP<br>เรือถึง", "COMM D<br>เริ่มลงของ",
            "COMP D<br>ลงของเสร็จ", "หมายเหตุ"]
    h += [hd("Cargo movement (operation status)"), tbl + "<tr>" + "".join(th(c) for c in cols) + "</tr>"]
    for i, v in enumerate(vs, 1):
        sg, nxt = stage(v), None
        if sg != "Completed":
            for k in MILES:
                if sg in ("Laden", "Waiting Discharge", "Discharging") and k in MILES[:4]:
                    continue
                if not actual(v.get(k)):
                    nxt = k
                    break
        cells = []
        for k in MILES:
            x = str(v.get(k) or "")
            s = '<span style="color:#888888;">TBA</span>' if not x else (
                f'<b><span style="color:#C0392B;">{E(x[2:])}</span></b>' if x.startswith("E ") else E(x))
            cells.append(td(s, "white-space:nowrap;", "#FFF2CC" if k == nxt else ""))
        rm, red = v.get("reason") or v.get("remark") or "", v.get("status") in RANK
        bl = f"{v['bl_qty']:,.0f}" if isinstance(v.get("bl_qty"), (int, float)) else "—"
        h.append("<tr>" + td(i) + td(f"<b>{E(vname(v))} ({E(v.get('owners', ''))})</b>") + td(E(v.get("shipment", "")))
                 + td(E(v.get("laycan", "")), "white-space:nowrap;") + td(E(v.get("qty_contract", ""))) + td(bl) + td(E(v.get("load_port", "")))
                 + "".join(cells) + td(f'<span style="color:#C0392B;">{E(rm)}</span>' if red else E(rm)) + "</tr>")
        ms = " | ".join(f"{lab} {(x[2:] + ' (E)') if x.startswith('E ') else (x or 'TBA')}" for lab, x in zip(MLAB, (str(v.get(k) or "") for k in MILES)))
        t.append(f"{vname(v)} ({v.get('owners', '')}) | {sg} | {v.get('shipment', '')} | Laycan {v.get('laycan', '')} | Qty {v.get('qty_contract', '')} | "
                 f"B/L {bl} | LP {v.get('load_port', '')} | {ms} | {rm}")
    h.append("</table>" + p("ตัวหนาสีแดง = estimate (ETA/ETC/ETD ล่าสุดจาก agent/owners) · ตัวดำ = actual ตาม report · ช่องเหลือง = ขั้นถัดไปที่กำลังรอ · เวลาท้องถิ่นของท่าเรือ", "color:#888888;"))
    if fol:
        h += [hd("ประเด็นที่ต้องติดตาม"), f'<ul style="{F}">']
        t += ["", "ประเด็นที่ต้องติดตาม"]
        for v in fol:
            col = "#C0392B" if v["status"] in ("Caution!", "Alert") else "#B26A00"
            lt = lt_text(v)
            dem = v.get("dem_rate") or "ยังไม่พบ"
            h.append(f'<li style="{F}"><b><span style="color:{col};">{E(v["status"])}</span></b> <b>{E(vname(v))}</b> ({E(stage(v))}, {E(v.get("port", ""))}) — '
                     f'<b>{E(v.get("reason", ""))}</b>. {E(v.get("remark", ""))}. {E(lt) + ". " if lt else ""}Dem: {E(dem)} '
                     f'<span style="color:#888888;">[ที่มา: {E(v.get("last_report", ""))}]</span></li>')
            t.append(f"- {v['status']} {vname(v)} ({stage(v)}, {v.get('port', '')}) — {v.get('reason', '')}. {v.get('remark', '')}. {lt + '. ' if lt else ''}"
                     f"Dem: {dem} [ที่มา: {v.get('last_report', '')}]")
        h.append("</ul>")
    lost = [x for x in st.get("lost_hours", []) if any(x[k] for k in SIDES.values())]
    if lost:
        h += [hd("ชั่วโมงที่เสียไป (stoppage / waiting)"), tbl + "<tr>" + "".join(th(c) for c in ("Vessel", "แยกตามฝ่าย", "รวม")) + "</tr>"]
        t += ["", "ชั่วโมงที่เสียไป (stoppage / waiting)"]
        for x in lost:
            parts = " · ".join(f"{lab} {x[k]:,.1f} h" for lab, k in SIDES.items() if x[k])
            tot = sum(x[k] for k in SIDES.values())
            h.append("<tr>" + td(f"<b>{E(x['vessel'])}</b>") + td(E(parts)) + td(f"{tot:,.1f} h", "text-align:right;") + "</tr>")
            t.append(f"{x['vessel']}: {parts} = {tot:,.1f} h")
        h.append("</table>" + p("Shipper = เวลาที่ load port ซึ่ง claim back-to-back กับ shipper ได้ · Receiver / charterers = เวลาที่ discharge port ที่นับเข้า laytime ของ AGE · Weather = หักได้ภายใต้ WWD · Caution! = รอโหลดเกิน 3 วันต่อเนื่องโดยไม่มีสินค้าลงเรือ", "color:#888888;"))
    credit = "สรุปจากอีเมล daily report ของ agent / owners — โปรดตรวจสอบกับรายงานต้นทางก่อนนำไปใช้อ้างอิงเชิงพาณิชย์"
    h += [p("ขอบคุณครับ<br>Chartering"), '<hr style="border:0;border-top:1px solid #D0D7DE;">',
          p(f"<i><b>Powered by Claude AI</b> · {credit}</i>", "color:#888888;"), "</div>"]
    t += ["", "ขอบคุณครับ", "Chartering", "", f"Powered by Claude AI · {credit}"]
    return subject, "\n".join(h).replace("</td><td", "</td>\n<td"), "\n".join(t)


def cmd_build(state_path, patch_path, outdir, url):
    st = load(state_path)
    patch = json.load(open(patch_path, encoding="utf-8")) if patch_path not in ("-", "none") else {}
    if not st.get("vessels") and not patch.get("add"):
        sys.exit("STOP: state has no vessels - do not overwrite the dashboard; report this to Aum.")
    ri = round_info()
    warn, info = apply_patch(st, patch, ri)
    os.makedirs(outdir, exist_ok=True)
    board = os.path.join(outdir, "board.json")
    json.dump(st, open(board, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import render
    render.main(board, os.path.join(here, "index.html"))
    print(f"ROUND {ri['label']}")
    print(f"board.json -> {board}   (ArtifactData set, collection board, doc current)")
    print(f"TV page    -> {os.path.join(here, 'index.html')}   (git add index.html only, commit 'Board update {ri['label']}', push)")
    if ri["email"]:
        subject, h, t = make_email(st, ri, url or "", bool(patch.get("no_new")))
        open(os.path.join(outdir, "email.html"), "w", encoding="utf-8").write(h)
        open(os.path.join(outdir, "email.txt"), "w", encoding="utf-8").write(t)
        bad = set(re.findall(r"font-size:([^;\"]+)", h)) - {"12pt"}
        print(f"EMAIL: YES  subject: {subject}\n  htmlBody -> {outdir}/email.html ({len(h):,} chars)   body -> {outdir}/email.txt ({len(t):,} chars)"
              + (f"   !! font sizes {bad}" if bad else ""))
    else:
        print("EMAIL: no (dashboard-only round)")
    vs = st["vessels"]
    print("SUMMARY:", len(vs), "vessels |", " · ".join(f"{k} {n}" for k in SHOW if (n := sum(1 for v in vs if stage(v) == k))),
          "|", "; ".join(f"{v['status']}: {v['vessel']} ({v.get('reason', '')})" for v in vs if v.get("status") in RANK) or "all On track")
    for v in vs:
        lt = lt_text(v)
        if lt:
            print(f"  {v['vessel']}: {lt} | expiry {v.get('laytime_expiry')}")
    for x in info:
        print("INFO:", x)
    for x in warn:
        print("WARN:", x)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "show":
        cmd_show(a[1], a[2] if len(a) > 2 else None)
    elif len(a) >= 2 and a[0] == "text":
        rest = [x for x in a[2:] if x != "--all"]
        cmd_text(a[1], int(rest[0]) if rest else 5000, "--all" in a)
    elif len(a) >= 4 and a[0] == "build":
        cmd_build(a[1], a[2], a[3], a[a.index("--url") + 1] if "--url" in a else "")
    else:
        sys.exit(__doc__)
