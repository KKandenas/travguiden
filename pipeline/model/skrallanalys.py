"""Skrällanalys: vad hade de lågt streckade hästarna som vann gemensamt?

Att bara titta på vinnarna i lopp där tipset slog fel ger falska mönster. Därför jämförs alla skrällkandidater
(inte favorit, högst 15 % streck) med vad Oddsen räknade med: kvot = vinster / summan av Oddsens chans. 1,00 betyder
att egenskapen redan är inprisad; över 1 att sådana hästar vann oftare än Oddsen trodde. Experternas val och
Hästkollens bedömningar och faktorer kommer med för de omgångar där de finns (sedan oktober 2026).

    python -m pipeline skrallanalys [--fran 2026-10-17] [--min 100]

Testas många egenskaper blir någon "signifikant" av en slump. Ett mönster härifrån blir en kandidat i statistik.py
med ett startdatum (fran), och avgörs bara på nya lopp.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Dict, List, Tuple

from . import data, modeller

MAX_STRECK = 0.15


def _grupper(h: dict, l: dict, s: float, t0, faktor) -> List[str]:
    """Egenskaper som hästen har (namn på grupper den räknas in i)."""
    g = ["Alla skrällkandidater", f"  spelform {l['spelform']}",
         "streck 0–5 %" if s < .05 else "streck 5–10 %" if s < .10 else "streck 10–15 %"]
    if h.get("skor_andrad") and h.get("skor_fram") == 0 and h.get("skor_bak") == 0:
        g.append("barfota runt ny")
    ar_s, ar_v = h.get("ar_starter") or 0, h.get("ar_segrar") or 0
    if h.get("plac_senast") == 1 or (ar_s >= 5 and ar_v / ar_s >= .3):
        g.append("formfällan (vann senast eller ≥30 % i år)")
    if l.get("startmetod") == "auto" and h.get("spar"):
        g.append("autostart spår 1–3" if h["spar"] <= 3 else "autostart spår 9–" if h["spar"] >= 9 else "autostart spår 4–8")
    if t0:
        if t0["kusk"] and h.get("kusk") and t0["kusk"] != h["kusk"]:
            g.append("kuskbyte")
        dagar = (date.fromisoformat(l["datum"]) - date.fromisoformat(t0["datum"])).days
        g.append("vila > 60 dagar" if dagar > 60 else "start < 14 dagar sedan" if dagar < 14 else "14–60 dagar sedan")
        if t0["galopp"] or t0["diskad"]:
            g.append("galopp/diskad senast")
    if h.get("experter") is not None:
        n = h["experter"]
        g.append("ingen expert har med hästen" if n == 0 else "minst en expert har med hästen")
        if h.get("expertspik"):
            g.append("spik hos minst en expert")
    if h.get("hastkoll") is not None:
        g.append({1: "Hästkoll: bättre än resultaten", 0: "Hästkoll: som resultaten",
                  -1: "Hästkoll: sämre än resultaten"}[h["hastkoll"]])
    if faktor:
        for falt, varden in (("storning", ("instangd", "ingen_lucka", "galopp_storning", "galopp_egen")),
                             ("lage", ("dodens", "tredjespar", "langre_ut", "ledning")),
                             ("avslutning", ("stark", "svag")), ("tempo", ("gynnad", "missgynnad"))):
            if faktor[falt] in varden:
                g.append(f"senast: {falt} {faktor[falt]}")
    return g


def analysera(conn: sqlite3.Connection, fran: str = "") -> Dict[str, Tuple[int, float, int]]:
    """{grupp: (vinster, summa Oddsens chans, antal hästar)} för skrällkandidater i avgjorda lopp från `fran`."""
    lopp = data.lopp(conn, "o.datum >= ?", (fran or "0000",), bara_avgjorda=True)
    chans = {r[0]: r[1] for r in conn.execute("SELECT start_id, chans FROM prognoser WHERE modellversion = ?",
                                              (modeller.AKTIV,))}
    extra = {r["id"]: r for r in conn.execute("SELECT id, kusk, spar FROM starter")}
    t0 = {r["start_id"]: r for r in conn.execute("SELECT * FROM tidigare_starter WHERE nr = 1")}
    faktor = {}
    for r in conn.execute("""SELECT h.start_id, f.* FROM hastkoll h
                             JOIN hastkoll_historik hh ON hh.start_id = h.start_id AND hh.version = h.version
                             JOIN hastkoll_faktorer f ON f.historik_id = hh.id
                             JOIN tidigare_starter t ON t.start_id = h.start_id AND t.nr = 1 AND t.datum = f.start_datum"""):
        faktor[r["start_id"]] = r
    spik = {r[0] for r in conn.execute(
        """SELECT DISTINCT s.id FROM expertval v JOIN expertsystem e ON e.id = v.system_id
           JOIN avdelningar a ON a.omgang_id = e.omgang_id AND a.avd = v.avd
           JOIN starter s ON s.avdelning_id = a.id AND s.nr = v.nr
           WHERE (SELECT COUNT(*) FROM expertval v2 WHERE v2.system_id = v.system_id AND v2.avd = v.avd) = 1""")}
    ut: Dict[str, List] = defaultdict(lambda: [0, 0.0, 0])
    for l in lopp:
        hs = [h for h in l["hastar"] if h["start_id"] in chans]
        if len(hs) < 2:
            continue
        stot, ctot = sum(h["streck"] for h in hs), sum(chans[h["start_id"]] for h in hs)
        fav = max(hs, key=lambda h: h["streck"])
        for h in hs:
            s = h["streck"] / stot
            if h is fav or s > MAX_STRECK:
                continue
            h = {**h, "kusk": extra[h["start_id"]]["kusk"], "spar": extra[h["start_id"]]["spar"],
                 "expertspik": h["start_id"] in spik}
            vann = int(h["nr"] in l["vinnare"])
            for g in _grupper(h, l, s, t0.get(h["start_id"]), faktor.get(h["start_id"])):
                u = ut[g]
                u[0] += vann
                u[1] += chans[h["start_id"]] / ctot
                u[2] += 1
    return {k: tuple(v) for k, v in ut.items()}


def rapport(conn: sqlite3.Connection, fran: str = "", minsta: int = 100) -> str:
    grupper = analysera(conn, fran)
    rader = [f"Skrällkandidater (inte favorit, högst {MAX_STRECK:.0%} streck){f' från {fran}' if fran else ''}. "
             "Kvot = vinster / Oddsens chans; ◀ vann tydligt oftare, ▷ tydligt mer sällan (mer än 2 standardfel).",
             "", f"{'egenskap':46} {'hästar':>7} {'vann':>6} {'Oddsen':>7}  kvot"]
    for namn, (v, c, n) in sorted(grupper.items(), key=lambda x: (not x[0].startswith("Alla"), not x[0].startswith("  "),
                                                                  -(x[1][0] / x[1][1]) if x[1][1] else 0)):
        if n < minsta or not c:
            continue
        k, se = v / c, math.sqrt(max(v, 1)) / c
        mark = " ◀" if k - 1 > 2 * se else " ▷" if 1 - k > 2 * se else ""
        rader.append(f"{namn:46} {n:7} {v / n * 100:5.1f}% {c / n * 100:6.1f}%  {k:4.2f} ± {se:4.2f}{mark}")
    return "\n".join(rader)
