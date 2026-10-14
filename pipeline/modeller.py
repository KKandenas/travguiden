"""Dataklasser som källorna returnerar och lagringen tar emot.

Källmoduler tolkar och validerar; de rör aldrig databasen. Lagringen (lagring.py) rör aldrig nätverket.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


class ValideringsFel(ValueError):
    """Data från en källa ser trasig ut och ska inte sparas."""


@dataclass
class Start:
    nr: int
    hast: str
    hast_id: Optional[int] = None
    alder: Optional[int] = None
    kon: Optional[str] = None
    kusk: Optional[str] = None
    tranare: Optional[str] = None
    spar: Optional[int] = None
    distans: Optional[int] = None
    struken: bool = False
    livs_starter: Optional[int] = None
    livs_segrar: Optional[int] = None
    livs_platser: Optional[int] = None
    ar_starter: Optional[int] = None
    ar_segrar: Optional[int] = None
    intjant: Optional[float] = None
    rekord: Optional[str] = None
    snittodds_5: Optional[float] = None
    kusk_segerproc: Optional[float] = None
    tranare_segerproc: Optional[float] = None
    streck: Optional[float] = None          # andel 0–1
    vinnarodds: Optional[float] = None
    placering: Optional[int] = None
    slutodds: Optional[float] = None
    km_tid: Optional[str] = None


@dataclass
class Avdelning:
    avd: int
    lopp_id: str
    loppnr: Optional[int]
    namn: Optional[str]
    distans: Optional[int]
    startmetod: Optional[str]
    starttid: Optional[str]                 # UTC
    starter: List[Start]
    vinnare: List[int] = field(default_factory=list)   # tom tills loppet är avgjort


@dataclass
class Omgang:
    id: str
    spelform: str
    datum: str
    bana: str
    spelstopp: str                          # UTC
    status: str
    omsattning: Optional[float]
    tidpunkt: str                           # UTC, när strecken/oddsen gällde
    avdelningar: List[Avdelning]
    utdelning: Dict[int, float] = field(default_factory=dict)   # antal rätt -> kr per rad
    vinnande_rader: Dict[int, int] = field(default_factory=dict)
    avgjord: bool = False
