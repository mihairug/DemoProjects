"""Citește exportul CSV de tranzacții din ING Home'Bank.

Formatul ING pune o tranzacție pe mai multe rânduri: un rând principal
(data decontării, tipul operațiunii, debit/credit, sold) urmat de rânduri cu
detalii de forma „Cheie:valoare” în coloana a patra. Antetul cu datele
titularului (nume, CNP, adresă) și semnăturile se repetă pe fiecare pagină;
din antet păstrăm doar numele titularului, ca să recunoaștem transferurile
în conturile proprii. CNP-ul și adresa nu sunt păstrate.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date

LUNI = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6,
    "iulie": 7, "august": 8, "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
}
_RAND_PRINCIPAL = re.compile(r"^(\d{1,2}) ([a-zăâîșț]+) (\d{4})$", re.I)
_DATA_SCURTA = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")


@dataclass
class Tranzactie:
    id: str
    data: date              # ziua plății: data autorizării, sau a decontării dacă lipsește
    data_decontare: date
    tip_operatiune: str     # ex. „Cumparare POS”, „Rata Credit”
    debit: float
    credit: float
    sold: float | None
    comerciant: str         # numele comerciantului / beneficiarului, curățat
    detalii: dict[str, str] = field(default_factory=dict)

    @property
    def suma(self) -> float:
        """Suma cu semn: negativ pentru plăți, pozitiv pentru încasări."""
        return round(self.credit - self.debit, 2)


@dataclass
class Extras:
    titular: str | None
    tranzactii: list[Tranzactie]


def numar(text: str) -> float:
    """„1.609,12” -> 1609.12"""
    text = text.strip()
    if not text:
        return 0.0
    return float(text.replace(".", "").replace(",", "."))


def _data_lunga(text: str) -> date | None:
    m = _RAND_PRINCIPAL.match(text.strip())
    if not m or m.group(2).lower() not in LUNI:
        return None
    return date(int(m.group(3)), LUNI[m.group(2).lower()], int(m.group(1)))


def _data_scurta(text: str) -> date | None:
    m = _DATA_SCURTA.match(text.strip())
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _decodeaza(continut: bytes) -> str:
    for enc in ("utf-8-sig", "cp1250"):
        try:
            return continut.decode(enc)
        except UnicodeDecodeError:
            pass
    return continut.decode("latin-1")


def nume_comerciant(tranzactie_la: str) -> str:
    """„MEGAIMAGE 0261 CRANGS25SG  RO  BUCURESTI” -> „MEGAIMAGE 0261 CRANGS25SG”.

    ING separă numele de țară și oraș prin două sau mai multe spații.
    """
    return re.split(r"\s{2,}", tranzactie_la.strip())[0].strip()


def localitate(tranzactie_la: str) -> str:
    """„MEGAIMAGE 0261 CRANGS25SG  RO  BUCURESTI” -> „BUCURESTI”."""
    parti = re.split(r"\s{2,}", tranzactie_la.strip())
    return parti[-1] if len(parti) > 1 else ""


# Pozițiile coloanelor din exporturile vechi, folosite până la primul rând de antet.
# ING a mutat coloanele între exporturi (ex. fără „Balanta”, cu „Debit” mutat la dreapta),
# așa că le căutăm după titlu în fiecare antet „Data,,,Detalii tranzactie,...”.
COLOANE_IMPLICITE = {"Detalii tranzactie": 3, "Debit": 4, "Credit": 6, "Balanta": 7}
_COLOANE_OBLIGATORII = ("Detalii tranzactie", "Debit", "Credit")


def _coloane(antet: list[str]) -> dict[str, int]:
    col = {}
    for i, titlu in enumerate(antet):
        titlu = titlu.strip()
        if titlu in COLOANE_IMPLICITE and titlu not in col:
            col[titlu] = i
    lipsa = [c for c in _COLOANE_OBLIGATORII if c not in col]
    if lipsa:
        raise ValueError(f"antetul extrasului nu are coloanele: {', '.join(lipsa)}")
    return col


def citeste(continut: bytes | str) -> Extras:
    text = _decodeaza(continut) if isinstance(continut, bytes) else continut
    titular = None
    brute: list[dict] = []
    curenta: dict | None = None
    col = dict(COLOANE_IMPLICITE)

    for rand in csv.reader(io.StringIO(text)):
        rand = rand + [""] * max(0, max(col.values()) + 1 - len(rand))
        prima = rand[0].strip()
        if prima.startswith("Titular cont:"):
            titular = re.sub(r"^(DL|DNA|D-NA|D-L)\.?\s+", "", prima.split(":", 1)[1].strip(), flags=re.I)
            curenta = None
            continue
        if prima == "Data":
            col = _coloane(rand)
            curenta = None
            continue
        data = _data_lunga(prima)
        if data:
            sold = rand[col["Balanta"]].strip() if "Balanta" in col else ""
            curenta = {
                "decontare": data, "tip": rand[col["Detalii tranzactie"]].strip(),
                "debit": numar(rand[col["Debit"]]), "credit": numar(rand[col["Credit"]]),
                "sold": numar(sold) if sold else None, "detalii": {},
            }
            brute.append(curenta)
        elif (curenta is not None and not prima and not rand[1].strip()
              and rand[col["Detalii tranzactie"]].strip()):
            cheie, _, valoare = rand[col["Detalii tranzactie"]].strip().partition(":")
            curenta["detalii"][cheie.strip()] = valoare.strip()
        else:
            # semnături, antet de tabel etc. închid tranzacția curentă
            curenta = None

    tranzactii = []
    aparitii: dict[str, int] = {}
    for b in brute:
        d = b["detalii"]
        data = _data_scurta(d.get("Data autorizarii", "")) or b["decontare"]
        comerciant = (
            nume_comerciant(d["Tranzactie la"]) if d.get("Tranzactie la")
            else d.get("Beneficiar") or d.get("Ordonator") or b["tip"]
        )
        baza = _cheie(b, d, data, comerciant)
        # două tranzacții identice fără referință în același fișier rămân distincte
        aparitii[baza] = aparitii.get(baza, 0) + 1
        id_ = hashlib.sha1(f"{baza}#{aparitii[baza]}".encode()).hexdigest()[:16]
        tranzactii.append(Tranzactie(
            id=id_, data=data, data_decontare=b["decontare"], tip_operatiune=b["tip"],
            debit=b["debit"], credit=b["credit"], sold=b["sold"], comerciant=comerciant, detalii=d,
        ))
    return Extras(titular=titular, tranzactii=tranzactii)


def _cheie(b: dict, d: dict, data: date, comerciant: str) -> str:
    """Cheie stabilă între exporturi, ca reimportul unei perioade să nu dubleze nimic.

    Soldul nu intră în cheie: depinde de ordinea decontărilor din aceeași zi.
    """
    suma = f"{b['debit']:.2f}/{b['credit']:.2f}"
    if d.get("Numar autorizare"):
        return f"aut|{d['Numar autorizare']}|{data}|{suma}|{comerciant}"
    if d.get("Referinta"):
        return f"ref|{d['Referinta']}|{suma}"
    return f"alt|{b['decontare']}|{b['tip']}|{suma}|{sorted(d.items())}"
