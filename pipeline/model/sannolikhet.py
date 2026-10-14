"""Chans per häst. Rena funktioner utan databas.

Grunden är V85-strecken: miljontals kronor fördelade över hästarna, en bra men inte perfekt bedömning.
Kända skevheter är att folket överspelar stora favoriter och kändiskuskar och underspelar
tillägg och dåliga spår, eller tvärtom – vilket som gäller avgörs av historiken, inte av antaganden.

Modellen är en villkorad logit (softmax per lopp):
    chans_i = exp(Σ_j w_j · x_ij) / Σ_k exp(Σ_j w_j · x_kj)
där x är egenskaper per häst (se EGENSKAPER). Med bara log(streck) och w = 1 blir chansen exakt
strecken; vikterna skattas på avgjorda lopp med Newtons metod.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

MIN_STRECK = 0.002      # en häst med 0 % streck kan ändå vinna


def normalisera(v: Sequence[float]) -> List[float]:
    s = sum(v)
    return [x / s for x in v] if s > 0 else [1 / len(v)] * len(v)


def softmax(poang: Sequence[float]) -> List[float]:
    m = max(poang)
    e = [math.exp(p - m) for p in poang]
    s = sum(e)
    return [x / s for x in e]


# ---------- egenskaper ----------

def _log_streck(h, lopp) -> float:
    return math.log(max(h["streck"], MIN_STRECK))


def _odds_mot_streck(h, lopp) -> float:
    """Hur mycket vinnarpoolen tror mer på hästen än V85-spelarna gör (0 om odds saknas)."""
    if not h.get("oddschans"):
        return 0.0
    return math.log(max(h["oddschans"], MIN_STRECK)) - math.log(max(h["streck"], MIN_STRECK))


def _bakspar(h, lopp) -> float:
    """Autostart: spår 9 och uppåt startar i andra ledet."""
    return 1.0 if lopp.get("startmetod") == "auto" and (h.get("spar") or 0) >= 9 else 0.0


def _tillagg(h, lopp) -> float:
    """Tillägg i 20-metersenheter (voltstart)."""
    if not h.get("distans") or not lopp.get("distans"):
        return 0.0
    return max(0, h["distans"] - lopp["distans"]) / 20


def _kusk(h, lopp) -> float:
    """Kuskens segerprocent i år, centrerad kring 12 %."""
    return (h["kusk_segerproc"] - 0.12) if h.get("kusk_segerproc") is not None else 0.0


def _form(h, lopp) -> float:
    """Hästens segerandel i karriären, krympt mot 10 % för hästar med få starter."""
    s = h.get("livs_starter") or 0
    return ((h.get("livs_segrar") or 0) + 0.5) / (s + 5) - 0.1


EGENSKAPER = {
    "log_streck": _log_streck,
    "odds_mot_streck": _odds_mot_streck,
    "bakspar": _bakspar,
    "tillagg": _tillagg,
    "kusk": _kusk,
    "form": _form,
}


def egenskaper(lopp: dict, namn: Sequence[str]) -> List[List[float]]:
    """Egenskapsmatris för loppets hästar. lopp = {startmetod, distans, hastar: [{streck, ...}]}."""
    hastar = lopp["hastar"]
    streck = normalisera([max(h.get("streck") or 0, 0) for h in hastar])
    odds = [h.get("vinnarodds") for h in hastar]
    # ATG visar inga odds över 99,99. Har de flesta hästarna odds räknas de övriga som 100.
    if sum(1 for o in odds if o) >= len(odds) / 2:
        oddschans = normalisera([1 / (o or 100) for o in odds])
    else:
        oddschans = [None] * len(hastar)
    rader = []
    for h, s, oc in zip(hastar, streck, oddschans):
        hh = {**h, "streck": s, "oddschans": oc}
        rader.append([EGENSKAPER[n](hh, lopp) for n in namn])
    return rader


def chanser(lopp: dict, vikter: Dict[str, float]) -> List[float]:
    namn = list(vikter)
    x = egenskaper(lopp, namn)
    return softmax([sum(vikter[n] * xi for n, xi in zip(namn, rad)) for rad in x])


# ---------- skattning ----------

def _los(A: List[List[float]], b: List[float]) -> List[float]:
    """Lös A x = b (liten, symmetrisk positivt definit) med Gauss-elimination."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            raise ValueError("singulär matris")
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def skatta(lopp: List[dict], namn: Sequence[str], l2: float = 1.0, start: Optional[Dict[str, float]] = None,
           iterationer: int = 25) -> Dict[str, float]:
    """Maximum likelihood för den villkorade logiten (Newton). Varje lopp: {..., hastar, vinnare: [nr]}.

    L2-straffet drar vikterna mot startvärdet (log_streck = 1, övriga = 0), alltså mot "strecken har rätt".
    """
    namn = list(namn)
    prior = [1.0 if n == "log_streck" else 0.0 for n in namn]
    w = [start.get(n, p) for n, p in zip(namn, prior)] if start else prior[:]
    data = []
    for l in lopp:
        x = egenskaper(l, namn)
        vinn = [i for i, h in enumerate(l["hastar"]) if h["nr"] in l["vinnare"]]
        if vinn:
            data.append((x, vinn))
    d = len(namn)
    for _ in range(iterationer):
        g = [-l2 * (wi - pi) for wi, pi in zip(w, prior)]
        H = [[(l2 if i == j else 0.0) for j in range(d)] for i in range(d)]
        for x, vinn in data:
            p = softmax([sum(wi * xi for wi, xi in zip(w, rad)) for rad in x])
            snitt = [sum(p[k] * x[k][j] for k in range(len(x))) for j in range(d)]
            andel = 1 / len(vinn)           # dött lopp: vinsten delas
            for v in vinn:
                for j in range(d):
                    g[j] += andel * (x[v][j] - snitt[j])
            for i in range(d):
                for j in range(i, d):
                    c = sum(p[k] * (x[k][i] - snitt[i]) * (x[k][j] - snitt[j]) for k in range(len(x)))
                    H[i][j] += c
                    if i != j:
                        H[j][i] += c
        steg = _los(H, g)
        w = [wi + si for wi, si in zip(w, steg)]
        if max(abs(s) for s in steg) < 1e-7:
            break
    return dict(zip(namn, w))


def logloss(lopp: List[dict], vikter: Dict[str, float]) -> List[float]:
    """−log(chans för vinnaren) per lopp (lägre är bättre)."""
    ut = []
    for l in lopp:
        p = chanser(l, vikter)
        vinn = [p[i] for i, h in enumerate(l["hastar"]) if h["nr"] in l["vinnare"]]
        if vinn:
            ut.append(-math.log(max(sum(vinn) / len(vinn), 1e-9)))
    return ut
