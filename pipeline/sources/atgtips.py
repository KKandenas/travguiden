"""Experternas system (V85/V75) från ATG:s tipsartiklar (t.ex. "Fem tippar V85", Fernlund, Olsson).

Artiklarna ligger i ATG:s CMS (Contentful). Nyckeln är den som atg.se själv skickar till alla besökare
(clientConfig.contentful i sidans HTML). Den läses vid varje körning och sparas aldrig i repot, så ett
nyckelbyte hos ATG hanteras automatiskt. Systemen är vanliga ATG-kuponger som hämtas från ATG:s publika
kupong-API. Kupongerna raderas efter loppet – därför sparar pipelinen dem när de hittas.

Tolkningsfunktionerna (tolka_*) är rena och testas mot sparade svar i tests/fixtures.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

import requests

from .. import config
from ..http import HamtningsFel, hamta_json, session
from ..modeller import Expertsystem, ValideringsFel
from .atg import ANTAL_AVD

log = logging.getLogger(__name__)

TIPSSIDA = "https://www.atg.se/"          # clientConfig finns på alla sidor
KUPONG_API = "https://api.atg.se/horse-coupons/api-public/v1/coupons"
KALLA_FEM = "Fem tippar"
KALLA_OVRIGA = "ATG:s experter"
_UUID = re.compile(r"couponId=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_SPEL = re.compile(r"\b((?:V85|V75)_\d{4}-\d{2}-\d{2}_\d+_\d+)\b")
# Titlar som inte säger vem som tippat ("Kupong 1 Fem tippar", "Stora systemet", en ren länk …)
_ALLMAN_TITEL = re.compile(r"^(kupong\b|https?:|stora systemet|lilla systemet|system\b|v85\b)", re.I)

_KUPONGER = """{ couponCollection(limit: 100, order: sys_publishedAt_DESC) { items { sys { id } title url
  linkedFrom { entryCollection(limit: 5) { items { __typename ... on Article { sys { id } title slug gameTagId lead } } } } } } }"""
_ARTIKEL = """query($id: String!) { article(id: $id) { body { json } } }"""


# ---------- hämtning ----------

def hamta_nyckel() -> Tuple[str, str]:
    """(apiUrl, deliveryToken) ur clientConfig i atg.se:s HTML."""
    try:
        r = session().get(TIPSSIDA, timeout=config.HTTP_TIMEOUT)
    except requests.RequestException as e:
        raise HamtningsFel(f"Nätverksfel mot {TIPSSIDA}: {e}") from e
    if r.status_code != 200:
        raise HamtningsFel(f"{TIPSSIDA} svarade {r.status_code}")
    return tolka_nyckel(r.text)


def _graphql(url: str, nyckel: str, query: str, variabler: Optional[dict] = None) -> dict:
    try:
        r = session().post(url, json={"query": query, "variables": variabler or {}},
                           headers={"Authorization": f"Bearer {nyckel}"}, timeout=config.HTTP_TIMEOUT)
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        raise HamtningsFel(f"ATG:s CMS svarade inte: {e}") from e
    if r.status_code != 200 or data.get("errors"):
        raise HamtningsFel(f"ATG:s CMS svarade {r.status_code}: {str(data.get('errors'))[:200]}")
    return data["data"]


def hamta_expertsystem(spel_ids: List[str]) -> Tuple[List[Expertsystem], List[str]]:
    """Expertsystem för de angivna omgångarna. Returnerar (system, varningar)."""
    url, nyckel = hamta_nyckel()
    poster = _graphql(url, nyckel, _KUPONGER)["couponCollection"]["items"]
    kandidater = tolka_kupongposter(poster, set(spel_ids))
    namn_per_post: Dict[str, str] = {}
    for artikel_id in {k["artikel_id"] for k in kandidater if k["artikel_id"]}:
        body = (_graphql(url, nyckel, _ARTIKEL, {"id": artikel_id}).get("article") or {}).get("body") or {}
        namn_per_post.update(namn_ur_artikel(body.get("json") or {}))
    system, varningar = [], []
    for k in kandidater:
        data, _ = hamta_json(f"{KUPONG_API}/{k['kupong_id']}", tillat_404=True)
        if data is None:
            varningar.append(f"kupongen {k['kupong_id']} ({k['titel']}) finns inte längre")
            continue
        try:
            system.append(tolka_kupong(data, k, namn_per_post.get(k["post_id"])))
        except ValideringsFel as e:
            varningar.append(str(e))
    return system, varningar


# ---------- tolkning ----------

def tolka_nyckel(html: str) -> Tuple[str, str]:
    i = html.find("clientConfig")
    if i < 0:
        raise HamtningsFel("clientConfig saknas i atg.se:s HTML")
    try:
        cfg, _ = json.JSONDecoder().raw_decode(html[html.index("{", i):])
        cf = cfg["contentful"]
        return cf["apiUrl"], cf["deliveryToken"]
    except (ValueError, KeyError, TypeError) as e:
        raise HamtningsFel(f"Kunde inte läsa CMS-nyckeln ur atg.se: {e}") from e


def tolka_kupongposter(poster: List[dict], spel_ids: set) -> List[dict]:
    """CMS-poster som är kuponger för våra omgångar. Harry Boy (ATG:s slumpsystem) räknas inte."""
    ut = []
    for p in poster:
        url, titel = p.get("url") or "", (p.get("title") or "").strip()
        spel, uuid = _SPEL.search(url), _UUID.search(url)
        if not spel or not uuid or spel.group(1) not in spel_ids or re.search("harry", titel, re.I):
            continue
        artiklar = [a for a in ((p.get("linkedFrom") or {}).get("entryCollection") or {}).get("items") or []
                    if a and a.get("__typename") == "Article"]
        # ATG återanvänder kupongposter mellan veckor, så en post kan sitta i flera artiklar. Ta den som gäller
        # omgången (gameTagId), annars den första.
        a = next((x for x in artiklar if spel.group(1) in (x.get("gameTagId") or [])), artiklar[0] if artiklar else {})
        ut.append({
            "post_id": (p.get("sys") or {}).get("id"), "kupong_id": uuid.group(1), "spel_id": spel.group(1),
            "titel": titel, "artikel_id": (a.get("sys") or {}).get("id"), "artikel": a.get("title"),
            "avsandare": _avsandare(a.get("lead")),
            "kalla": KALLA_FEM if (a.get("slug") or "").startswith("fem-tippar") else KALLA_OVRIGA,
        })
    return ut


def _avsandare(ingress: Optional[str]) -> Optional[str]:
    """"TR Medias tips till lördagens V85®…" -> "TR Media"."""
    m = re.match(r"\s*([A-ZÅÄÖ][\w .&-]{1,30}?)s tips\b", ingress or "")
    return m.group(1).strip() if m else None


def _text(nod: dict) -> str:
    return "".join(t.get("value", "") if t.get("nodeType") == "text" else _text(t) for t in nod.get("content") or [])


def namn_ur_artikel(dokument: dict) -> Dict[str, str]:
    """{CMS-post-id för kupongen: tipparens namn}. Namnet står på första raden i stycket närmast före
    kupongen ("Mats E Djuse\\nGävle"). Långa stycken är analystext och rubriker i versaler är inga namn."""
    ut, senaste = {}, None
    for nod in dokument.get("content") or []:
        typ = nod.get("nodeType")
        if typ == "paragraph":
            text = _text(nod).strip()
            if text:
                forsta = text.split("\n")[0].strip()
                # Inte rubriker i versaler, och inte rader med siffror eller kolon ("Ranking A: 10,4 B: 7,12")
                ar_namn = (len(forsta) <= 40 and len(text) <= 120 and not forsta.isupper()
                           and not re.search(r"[\d:]", forsta))
                senaste = forsta if ar_namn else None
        elif typ == "embedded-entry-block":
            post = ((nod.get("data") or {}).get("target") or {}).get("sys", {}).get("id")
            if post and senaste:
                ut[post] = senaste
                senaste = None          # namnet gäller bara kupongen direkt efter
    return ut


def tolka_kupong(data: dict, post: dict, namn: Optional[str]) -> Expertsystem:
    """Kupongen från ATG:s kupong-API. `post` kommer från tolka_kupongposter."""
    spel = (data.get("game") or {}).get("id")
    if spel != post["spel_id"]:
        raise ValideringsFel(f"kupongen {post['kupong_id']} gäller {spel}, väntade {post['spel_id']}")
    val = {}
    for r in data.get("races") or []:
        nr = sorted({b["number"] for b in r.get("bets") or [] if isinstance(b.get("number"), int)})
        if r.get("id") and nr:
            val[r["id"]] = nr
    antal = ANTAL_AVD.get(spel.split("_")[0])
    if len(val) != antal:
        raise ValideringsFel(f"kupongen {post['kupong_id']} har val i {len(val)} avdelningar, väntade {antal}")
    # Kupongens egen titel går först ("Patrik Fernlund stora systemförslag"), sedan namnet ur artikeln (Fem tippar,
    # där kupongerna bara heter "Kupong 3 Fem tippar"), avsändaren ur ingressen och sist artikelns titel.
    if post["titel"] and not _ALLMAN_TITEL.search(post["titel"]):
        namn = post["titel"]
    elif not namn:
        if post.get("avsandare"):
            namn = post["avsandare"] + (f" ({post['titel'].strip().lower()})" if post["titel"] and not post["titel"].startswith("http") else "")
        else:
            namn = post["artikel"] or "ATG"
    return Expertsystem(id=post["kupong_id"], omgang_id=spel, kalla=post["kalla"], namn=namn,
                        artikel=post["artikel"], rader=data.get("rows"), val=val)
