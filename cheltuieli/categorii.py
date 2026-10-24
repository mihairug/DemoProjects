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

from parser_ing import Tranzactie

# Fiecare categorie are un tip, folosit de rapoarte:
#   variabil    – cheltuieli de zi cu zi (intră în calendar)
#   fix         – rate, utilități, abonamente
#   numerar     – retrageri de la ATM (nu știm pe ce s-au dus)
#   exceptional – sume mari, o singură dată (ex. rambursare anticipată)
#   intern      – mutări între conturile tale; nu sunt cheltuieli
#   venit       – încasări
CATEGORII: dict[str, str] = {
    "Alimente": "variabil",
    "Restaurante & baruri": "variabil",
    "Cafea & gustări": "variabil",
    "Transport": "variabil",
    "Mașină": "variabil",
    "Parcare": "variabil",
    "Animale": "variabil",
    "Sănătate": "variabil",
    "Cumpărături online": "variabil",
    "Haine & sport": "variabil",
    "Copii & distracție": "variabil",
    "Casă & electronice": "variabil",
    "Fitness": "variabil",
    "Vacanțe & timp liber": "variabil",
    "Servicii": "variabil",
    "Cadouri & flori": "variabil",
    "Donații": "variabil",
    "Tutun": "variabil",
    "Transferuri către persoane": "variabil",
    "Altele": "variabil",
    "De identificat": "variabil",
    "Utilități & telecom": "fix",
    "Abonamente digitale": "fix",
    "Credit & asigurare": "fix",
    "Numerar (ATM)": "numerar",
    "Excepționale": "exceptional",
    "Transfer în cont propriu": "intern",
    "Încasări": "venit",
}
NECUNOSCUT = "De identificat"

# (expresie regulată pe numele comerciantului, categorie)
# Prima regulă care se potrivește câștigă, deci cele specifice stau înaintea celor generale.
REGULI: list[tuple[str, str]] = [
    (r"MEGA ?IMAGE|LIDL|PROFI|KAUFLAND|CARREFOUR|\bCORA\b|AUCHAN|PENNY|^FROO|METRO IACOB|"
     r"MINIMARKET|\bMARKET\b|MAGAZIN MIXT|PANINAT|BAKING DREAMS|MEGA PAN|ASOPUS SWEETS|"
     r"VANILLA|LUCA PROMENADA|MAIA E FARINA|BRUTARIE", "Alimente"),
    (r"METROREX|\bSTB\b|\bBOLT\b|UBER|ZEGAS TOUR|CFR CALATORI", "Transport"),
    (r"^MOL |LUKOIL|PETROM|\bOMV\b|ROMPETROL|AUTOSERV|AUTOPARTS|\bITP\b|VULCANIZARE", "Mașină"),
    (r"AMPARCAT|TPARK|PARCARE|-PARC$", "Parcare"),
    (r"\bVET\b|PET STUFF|PET PRODUCT|MUSPET|ANIMAX|ZOOMANIA", "Animale"),
    (r"PPC|ENEL|ENGIE|E\.ON|DIGI|ORANGE|VODAFONE|TELEKOM|APA NOVA|TERMOENERGETICA", "Utilități & telecom"),
    (r"NETFLIX|GOOGLE ONE|YOUTUBE|GOOGLE PLAY|AUDIBLE|AMAZON PRIME|KINDLE|SPOTIFY|HBO|DISNEY|"
     r"APPLE\.COM", "Abonamente digitale"),
    (r"FARM|PHARM|MEDICOVER|REGINA MARIA|SYNEVO|CLINICA|CATENA|SENSIBLU|DR\.? MAX|HELP NET", "Sănătate"),
    (r"EMAG|FASHIONDAYS|LIBRIS|LITERA|EASYBOX|ALTEX|CEL\.RO|AMAZON\.", "Cumpărături online"),
    (r"DECATHLON|H&M|PEEK & CLOPPENBURG|PANTOFIORI|ZARA|RESERVED|PEPCO|SINSAY", "Haine & sport"),
    (r"BEBETEI|KINDER GAMES|YOULAN CIRCUS|DINO LIFE|NORIEL|SMYK", "Copii & distracție"),
    (r"LEROY|BRICO|DEDEMAN|HORNBACH|IKEA|JYSK|KITCHEN SHOP|FLANCO|ELECTRO|SECOND DECORATION|"
     r"MEDIA PAPER", "Casă & electronice"),
    (r"GYM|SWIMMING|WORLD CLASS|STAY FIT", "Fitness"),
    (r"BOOKING|AIRBNB|IABILET|ANTIPA|CNM ASTRA|CASA SCRIITORILOR|APARTHOTEL|HOTEL|CASA VECHE|"
     r"CARAIMAN|CINEMA", "Vacanțe & timp liber"),
    (r"IGEI ACTIV", "Servicii"),
    (r"FUNDATIA|ASOCIATIA", "Donații"),
    (r"FLOR\b|FLORARIE", "Cadouri & flori"),
    (r"TABAC", "Tutun"),
    (r"RESTAURANT|\bBAR\b|TERASA|TAVERNA|RUSTIC|DONER|BURTARIE|\bMCD\b|MCDONALD|KFC|PIZZA|"
     r"FRESH FOOD|LA PAUNI|BREWERY|\bPUB\b|SOCIAL BACKYARD|TRADITIONAL SIB|VAYA|LA ROSTA|GLOVO|"
     r"TAZZ|WOLT", "Restaurante & baruri"),
    (r"CAFFE|COFFEE|CAFENEA|1MINUTE|MARIDO|TINY CUP|TED S|EVERGREEN|STARBUCKS|5 TO GO", "Cafea & gustări"),
]
_REGULI = [(re.compile(rx, re.I), cat) for rx, cat in REGULI]


def _acelasi_nume(a: str, b: str) -> bool:
    """„Rugina Mihail” și „Mihail Rugina” sunt aceeași persoană."""
    def cuvinte(s: str) -> set[str]:
        return {c for c in re.split(r"[^\w]+", s.lower()) if len(c) > 1}
    return bool(a and b) and cuvinte(a) == cuvinte(b)


def dupa_operatiune(t: Tranzactie, titular: str | None) -> str | None:
    tip = t.tip_operatiune.lower()
    if t.credit > 0 and t.debit == 0 and "Tranzactie la" not in t.detalii:
        # o rambursare de la un comerciant rămâne în categoria comerciantului
        return "Încasări"
    if tip.startswith("retragere"):
        return "Numerar (ATM)"
    if tip.startswith("recalculari") or "anulare a inregistrarii" in tip:
        return "Excepționale"
    if "credit" in tip or "asigurare" in tip:
        return "Credit & asigurare"
    if tip.startswith("transfer") or "beneficiar" in {k.lower() for k in t.detalii}:
        beneficiar = t.detalii.get("Beneficiar", "")
        if titular and _acelasi_nume(beneficiar, titular):
            return "Transfer în cont propriu"
        if dupa_nume(beneficiar):
            return dupa_nume(beneficiar)
        return "Transferuri către persoane"
    return None


def dupa_nume(comerciant: str) -> str | None:
    for rx, cat in _REGULI:
        if rx.search(comerciant):
            return cat
    return None


def categorie_automata(t: Tranzactie, titular: str | None) -> str:
    return dupa_operatiune(t, titular) or dupa_nume(t.comerciant) or NECUNOSCUT
