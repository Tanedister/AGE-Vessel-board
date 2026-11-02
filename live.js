/* AGE Vessel Board — live layer.
   Reads the public feed cell (feed!A1, JSON) from the Google Sheet "AGE Vessel Board — TV feed"
   and redraws the board when the sheet holds newer data than this page. ES5 only, for TV browsers. */
(function () {
  var SHEET_ID = "1PsesaYCiWdTl8C4l6Q7YCOVPnzjNwu1KYXtlOVdn2No";
  var URL = "https://docs.google.com/spreadsheets/d/" + SHEET_ID + "/gviz/tq?tqx=out:csv&sheet=feed&range=A1&headers=0";
  var ORDER = {"Completed": 0, "Discharging": 1, "At sea": 2, "Loading": 3, "Pre-arrival": 4};
  var SC = {"Pre-arrival": "pre", "Loading": "load", "At sea": "sea", "Discharging": "dis", "Completed": "done"};
  var MI = ["eta_lp", "comm_l", "comp_l", "etd_lp", "eta_dp", "comm_d", "comp_d"];
  var HD = ["ETA LP", "COMM L", "COMP L", "ETD LP", "ETA DP", "COMM D", "COMP D"];
  var DAYS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"], MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function esc(s) { return String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#x27;"); }
  function num(v) { if (v === "" || v == null) return null; var n = parseFloat(v); return isNaN(n) ? null : n; }
  function fmt(n, d) { return n.toFixed(d || 0).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function two(s) { var p = s.split(" "); return p.length >= 3 ? esc(p.slice(0,2).join(" ")) + '<br><span class="tm">' + esc(p.slice(2).join(" ")) + "</span>" : esc(s); }
  function cell(v, nx) {
    var s = String(v || "").replace(/^\s+|\s+$/g, ""), st = nx ? ' style="background:#2a2614"' : "";
    if (!s) return '<td' + st + ' class="t nil">&mdash;</td>';
    if (s.indexOf("E ") === 0) return '<td' + st + ' class="t est">' + two(s.slice(2)) + "</td>";
    return '<td' + st + ' class="t">' + two(s) + "</td>";
  }
  function nxi(v) { if (v.stage === "Completed") return -1; for (var i = 0; i < MI.length; i++) { var s = String(v[MI[i]] || ""); if (!s || s.indexOf("E ") === 0) return i; } return -1; }
  function dh(h) { h = num(h); if (h == null) return null; var m = Math.round(Math.abs(h) * 60), d = Math.floor(m / 1440), r = m % 1440;
    return d ? d + "d " + pad(Math.floor(r / 60)) + "h" : Math.floor(r / 60) + "h " + pad(r % 60) + "m"; }
  function ltl(v) {
    var lt = v.laytime || {}; if (!(v.stage === "Loading" || v.stage === "Discharging")) return "";
    var u = dh(lt.used_h), a = dh(lt.allowed_h), l = num(lt.left_h), p = [];
    if (u) p.push("Laytime used <b>" + u + "</b>" + (a ? " / " + a : ""));
    if (num(lt.rain_h)) p.push("rain " + dh(lt.rain_h));
    if (l != null) p.push(l < 0 ? '<b class="ov">On demurrage ' + dh(l) + "</b>" : "left <b>" + dh(l) + "</b>"); else if (u) p.push("terms TBC");
    if (!p.length) return "";
    return '<div class="lt">' + p.join(" · ") + (lt.basis ? " <span>(" + esc(lt.basis) + ")</span>" : "") + "</div>";
  }
  function stamp(iso) {
    var t = Date.parse(iso); if (isNaN(t)) return esc(iso || "—");
    var b = new Date(t + 7 * 3600e3);
    return DAYS[b.getUTCDay()] + " " + pad(b.getUTCDate()) + " " + MON[b.getUTCMonth()] + " " + b.getUTCFullYear() + " " + pad(b.getUTCHours()) + ":" + pad(b.getUTCMinutes());
  }
  function draw(st) {
    var vs = (st.vessels || []).slice().sort(function (a, b) { return (ORDER[a.stage] == null ? 9 : ORDER[a.stage]) - (ORDER[b.stage] == null ? 9 : ORDER[b.stage]); });
    function cnt(s) { var n = 0; for (var i = 0; i < vs.length; i++) if (vs[i].stage === s) n++; return n; }
    var attn = [], rows = [], i;
    for (i = 0; i < vs.length; i++) if (vs[i].flag === "watch" || vs[i].flag === "alert") attn.push(vs[i]);
    for (i = 0; i < vs.length; i++) {
      var v = vs[i], f = /^(ok|watch|alert|done)$/.test(v.flag) ? v.flag : "ok", tb = /^TB /i.test(v.vessel || ""), ni = nxi(v);
      var cg = num(v.cargo_mt) || num(v.bl_qty), dn = num(v.done_mt), q;
      if (cg && (v.stage === "Loading" || v.stage === "Discharging") && dn != null)
        q = fmt(dn) + "<span> / " + fmt(cg) + '</span><div class="bar"><i style="width:' + Math.min(100, dn / cg * 100).toFixed(0) + '%"></i></div>';
      else q = cg ? fmt(cg) + "<span> MT</span>" : "&mdash;";
      var mi = ""; for (var k = 0; k < MI.length; k++) mi += cell(v[MI[k]], k === ni);
      var why = (f === "watch" || f === "alert") && v.reason ? '<div class="why">' + esc(v.reason) + "</div>" : "";
      rows.push('<tr class="' + f + '"><td class="v"><b>' + (tb ? "" : "MV ") + esc(v.vessel) + "</b> <em>" + esc(v.owners) + "</em>" +
        '<div class="m">' + esc(v.shipment || "—") + " · " + esc(v.laycan || "—") + "</div>" +
        '<div class="rt">' + esc(v.load_port || "—") + " &rarr; " + esc(v.disch_port || "—") + "</div></td>" +
        '<td><span class="sg ' + (SC[v.stage] || "pre") + '">' + esc(v.stage === "At sea" ? "Sailing" : (v.stage || "—")) + "</span></td>" + mi +
        '<td class="q">' + q + '</td><td><span class="st ' + f + '">' + esc(v.status === "Watch" ? "Monitor" : (v.status || "—")) + "</span></td>" +
        '<td class="r">' + why + ltl(v) + esc(v.remark || "") + "</td></tr>");
    }
    if (!rows.length) rows.push('<tr><td colspan="12" class="nil" style="padding:3vw;text-align:center">ไม่มีเรือ active</td></tr>');
    function hrs(x) { var n = num(x) || 0; return n ? fmt(n, 1) : "&mdash;"; }
    var lo = [], L = st.lost_hours || [];
    for (i = 0; i < L.length; i++) {
      var sh = num(L[i].shipper) || 0, rc = num(L[i].receiver) || 0, ow = num(L[i].owners) || 0, wx = num(L[i].weather) || 0;
      if (!(sh || rc || ow || wx)) continue;
      lo.push("<tr><td>" + esc(L[i].vessel) + '</td><td class="nm">' + hrs(sh) + '</td><td class="nm">' + hrs(rc) + '</td><td class="nm">' + hrs(ow) + '</td><td class="nm">' + hrs(wx) + '</td><td class="nm dd">' + hrs(ow + wx) + "</td></tr>");
    }
    var at = []; for (i = 0; i < attn.length; i++) at.push("<b>" + esc(attn[i].vessel) + "</b> " + esc(attn[i].reason || attn[i].remark || attn[i].status));
    var hd = ""; for (i = 0; i < HD.length; i++) hd += "<th>" + HD[i] + "</th>";
    var w = document.querySelector(".w"); if (!w) return;
    w.innerHTML = '<div class="top"><h1><span>AGE</span>VESSEL BOARD</h1><div class="u">Last updated <b>' + stamp(st.updated_at) +
      "</b><br>Updates 09:00 · 12:00 · 15:00 (workdays) · live from cloud feed</div></div>" +
      (st.notice ? '<div class="n">' + esc(st.notice) + "</div>" : "") +
      '<div class="c"><div>Active<b>' + (vs.length - cnt("Completed")) + "</b></div><div>Pre-arrival<b>" + cnt("Pre-arrival") + "</b></div><div>Loading<b>" + cnt("Loading") +
      "</b></div><div>Sailing<b>" + cnt("At sea") + "</b></div><div>Discharging<b>" + cnt("Discharging") + "</b></div><div>Completed<b>" + cnt("Completed") +
      '</b></div><div style="border-color:#ff5b5b">Attention<b>' + attn.length + "</b></div></div>" +
      "<table><tr><th>Vessel / Route</th><th>Stage</th>" + hd + "<th>Cargo MT</th><th>Status</th><th>Remark</th></tr>" + rows.join("") + "</table>" +
      '<div class="bt"><div class="a">Needs attention: ' + (at.join(" &nbsp;•&nbsp; ") || "ทุกลำ On track") + "</div>" +
      '<div class="lo"><div class="lh">Lost time (hours)</div><table><tr><th style="text-align:left">Vessel</th><th>Shipper</th><th>Receiver</th><th>Owners</th><th>Weather</th><th>Deductible</th></tr>' +
      (lo.join("") || '<tr><td colspan="6" class="nil">No lost time recorded</td></tr>') + "</table>" +
      '<div class="lk">Shipper = load-port waiting, claim back-to-back · Receiver = counts in AGE laytime · Deductible = weather + owners\' stoppage, not counted</div></div></div>' +
      '<div class="f"><span class="est">Amber</span> = estimate · shaded = next milestone · port local time · source: agent / owners reports · Powered by Claude AI</div>';
  }
  function parseCell(csv) { csv = csv.replace(/^\s+|\s+$/g, ""); if (csv.charAt(0) === '"') csv = csv.slice(1, csv.lastIndexOf('"')).replace(/""/g, '"'); return JSON.parse(csv); }
  var shown = Date.parse(window.BOARD_UPDATED_AT || "") || 0;
  function pull() {
    var x = new XMLHttpRequest();
    x.open("GET", URL + "&t=" + new Date().getTime(), true);
    x.onreadystatechange = function () {
      if (x.readyState !== 4 || x.status !== 200) return;
      try { var st = parseCell(x.responseText), t = Date.parse(st.updated_at) || 0; if (t > shown) { shown = t; draw(st); } } catch (e) {}
    };
    x.send();
  }
  window.AGE_BOARD_DRAW = draw;
  pull(); setInterval(pull, 5 * 60 * 1000);
})();
