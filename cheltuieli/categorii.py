"""Încadrarea tranzacțiilor pe categorii.

Ordinea în care se decide categoria unei tranzacții:
1. alegerea ta pentru tranzacția respectivă (din ecranul „Pe zile”);
2. alegerea ta pentru comerciant (din ecranul „Comercianți”);
3. tipul operațiunii bancare (numerar, rată, transfer etc.);
4. regulile de mai jos, după numele comerciantului;
5. altfel, „De identificat”.
"""

from __future__ import annotations

import re

from constante import Cat, Ing, Tip
from parser_ing import Tranzactie

# Fiecare categorie are un tip (vezi constante.Tip), folosit de rapoarte.
CATEGORII: dict[str, str] = {
    Cat.ALIMENTE: Tip.VARIABIL,
    Cat.RESTAURANTE: Tip.VARIABIL,
    Cat.CAFEA: Tip.VARIABIL,
    Cat.TRANSPORT: Tip.VARIABIL,
    Cat.MASINA: Tip.VARIABIL,
    Cat.PARCARE: Tip.VARIABIL,
    Cat.ANIMALE: Tip.VARIABIL,
    Cat.SANATATE: Tip.VARIABIL,
    Cat.ONLINE: Tip.VARIABIL,
    Cat.HAINE_SPORT: Tip.VARIABIL,
    Cat.COPII: Tip.VARIABIL,
    Cat.CASA: Tip.VARIABIL,
    Cat.FITNESS: Tip.VARIABIL,
    Cat.VACANTE: Tip.VARIABIL,
    Cat.SERVICII: Tip.VARIABIL,
    Cat.CADOURI: Tip.VARIABIL,
    Cat.DONATII: Tip.VARIABIL,
    Cat.TUTUN: Tip.VARIABIL,
    Cat.CATRE_PERSOANE: Tip.VARIABIL,
    Cat.ALTELE: Tip.VARIABIL,
    Cat.NECUNOSCUT: Tip.VARIABIL,
    Cat.UTILITATI: Tip.FIX,
    Cat.ABONAMENTE: Tip.FIX,
    Cat.CREDIT: Tip.FIX,
    Cat.NUMERAR: Tip.NUMERAR,
    Cat.EXCEPTIONALE: Tip.EXCEPTIONAL,
    Cat.CONT_PROPRIU: Tip.INTERN,
    Cat.INCASARI: Tip.VENIT,
}

# (expresie regulată pe numele comerciantului, categorie)
# Prima regulă care se potrivește câștigă, deci cele specifice stau înaintea celor generale.
REGULI: list[tuple[str, str]] = [
    (r"MEGA ?IMAGE|LIDL|PROFI|KAUFLAND|CARREFOUR|\bCORA\b|AUCHAN|PENNY|^FROO|METRO IACOB|"
     r"MINIMARKET|\bMARKET\b|MAGAZIN MIXT|PANINAT|BAKING DREAMS|MEGA PAN|ASOPUS SWEETS|"
     r"VANILLA|LUCA PROMENADA|MAIA E FARINA|BRUTARIE", Cat.ALIMENTE),
    (r"METROREX|\bSTB\b|\bBOLT\b|UBER|ZEGAS TOUR|CFR CALATORI", Cat.TRANSPORT),
    (r"^MOL |LUKOIL|PETROM|\bOMV\b|ROMPETROL|AUTOSERV|AUTOPARTS|\bITP\b|VULCANIZARE", Cat.MASINA),
    (r"AMPARCAT|TPARK|PARCARE|-PARC$", Cat.PARCARE),
    (r"\bVET\b|PET STUFF|PET PRODUCT|MUSPET|ANIMAX|ZOOMANIA", Cat.ANIMALE),
    (r"PPC|ENEL|ENGIE|E\.ON|DIGI|ORANGE|VODAFONE|TELEKOM|APA NOVA|TERMOENERGETICA", Cat.UTILITATI),
    (r"NETFLIX|GOOGLE ONE|YOUTUBE|GOOGLE PLAY|AUDIBLE|AMAZON PRIME|KINDLE|SPOTIFY|HBO|DISNEY|"
     r"APPLE\.COM", Cat.ABONAMENTE),
    (r"FARM|PHARM|MEDICOVER|REGINA MARIA|SYNEVO|CLINICA|CATENA|SENSIBLU|DR\.? MAX|HELP NET", Cat.SANATATE),
    (r"EMAG|FASHIONDAYS|LIBRIS|LITERA|EASYBOX|ALTEX|CEL\.RO|AMAZON\.", Cat.ONLINE),
    (r"DECATHLON|H&M|PEEK & CLOPPENBURG|PANTOFIORI|ZARA|RESERVED|PEPCO|SINSAY", Cat.HAINE_SPORT),
    (r"BEBETEI|KINDER GAMES|YOULAN CIRCUS|DINO LIFE|NORIEL|SMYK", Cat.COPII),
    (r"LEROY|BRICO|DEDEMAN|HORNBACH|IKEA|JYSK|KITCHEN SHOP|FLANCO|ELECTRO|SECOND DECORATION|"
     r"MEDIA PAPER", Cat.CASA),
    (r"GYM|SWIMMING|WORLD CLASS|STAY FIT", Cat.FITNESS),
    (r"BOOKING|AIRBNB|IABILET|ANTIPA|CNM ASTRA|CASA SCRIITORILOR|APARTHOTEL|HOTEL|CASA VECHE|"
     r"CARAIMAN|CINEMA", Cat.VACANTE),
    (r"IGEI ACTIV", Cat.SERVICII),
    (r"FUNDATIA|ASOCIATIA", Cat.DONATII),
    (r"FLOR\b|FLORARIE", Cat.CADOURI),
    (r"TABAC", Cat.TUTUN),
    (r"RESTAURANT|\bBAR\b|TERASA|TAVERNA|RUSTIC|DONER|BURTARIE|\bMCD\b|MCDONALD|KFC|PIZZA|"
     r"FRESH FOOD|LA PAUNI|BREWERY|\bPUB\b|SOCIAL BACKYARD|TRADITIONAL SIB|VAYA|LA ROSTA|GLOVO|"
     r"TAZZ|WOLT", Cat.RESTAURANTE),
    (r"CAFFE|COFFEE|CAFENEA|1MINUTE|MARIDO|TINY CUP|TED S|EVERGREEN|STARBUCKS|5 TO GO", Cat.CAFEA),
]
_REGULI = [(re.compile(rx, re.I), cat) for rx, cat in REGULI]


def _acelasi_nume(a: str, b: str) -> bool:
    """„Rugina Mihail” și „Mihail Rugina” sunt aceeași persoană."""
    def cuvinte(s: str) -> set[str]:
        return {c for c in re.split(r"[^\w]+", s.lower()) if len(c) > 1}
    return bool(a and b) and cuvinte(a) == cuvinte(b)


def dupa_operatiune(t: Tranzactie, titular: str | None) -> str | None:
    tip = t.tip_operatiune.lower()
    if t.credit > 0 and t.debit == 0 and Ing.TRANZACTIE_LA not in t.detalii:
        # o rambursare de la un comerciant rămâne în categoria comerciantului
        return Cat.INCASARI
    if tip.startswith(Ing.OP_RETRAGERE):
        return Cat.NUMERAR
    if tip.startswith(Ing.OP_RECALCULARI) or Ing.OP_ANULARE_RNPM in tip:
        return Cat.EXCEPTIONALE
    if Ing.OP_CREDIT in tip or Ing.OP_ASIGURARE in tip:
        return Cat.CREDIT
    if tip.startswith(Ing.OP_TRANSFER) or Ing.BENEFICIAR.lower() in {k.lower() for k in t.detalii}:
        beneficiar = t.detalii.get(Ing.BENEFICIAR, "")
        if titular and _acelasi_nume(beneficiar, titular):
            return Cat.CONT_PROPRIU
        if dupa_nume(beneficiar):
            return dupa_nume(beneficiar)
        return Cat.CATRE_PERSOANE
    return None


def dupa_nume(comerciant: str) -> str | None:
    for rx, cat in _REGULI:
        if rx.search(comerciant):
            return cat
    return None


def categorie_automata(t: Tranzactie, titular: str | None) -> str:
    return dupa_operatiune(t, titular) or dupa_nume(t.comerciant) or Cat.NECUNOSCUT
