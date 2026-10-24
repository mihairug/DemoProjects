"""Baza de date locală (SQLite): tranzacțiile importate și alegerile tale.

Categoria automată nu se salvează: se recalculează la fiecare încărcare,
ca o regulă nouă să se aplice și tranzacțiilor vechi. Se salvează doar
ce ai ales tu, pe comerciant sau pe tranzacție.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd

import categorii
from parser_ing import Extras, Tranzactie

SCHEMA = """
CREATE TABLE IF NOT EXISTS tranzactii (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    data_decontare TEXT NOT NULL,
    tip_operatiune TEXT NOT NULL,
    debit REAL NOT NULL,
    credit REAL NOT NULL,
    sold REAL,
    comerciant TEXT NOT NULL,
    detalii TEXT NOT NULL,
    importat_la TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categorie_comerciant (
    comerciant TEXT PRIMARY KEY,
    categorie TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categorie_tranzactie (
    id TEXT PRIMARY KEY,
    categorie TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bugete (
    categorie TEXT PRIMARY KEY,
    suma REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS setari (
    cheie TEXT PRIMARY KEY,
    valoare TEXT
);
"""

COLOANE = [
    "id", "data", "data_decontare", "tip_operatiune", "debit", "credit", "sold", "comerciant",
    "detalii", "valuta", "categorie", "sursa_categorie", "tip",
]


class Baza:
    def __init__(self, cale: str | Path):
        Path(cale).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(cale), check_same_thread=False)
        self.con.executescript(SCHEMA)

    # --- import ---------------------------------------------------------------

    def importa(self, extras: Extras) -> tuple[int, int]:
        """Adaugă tranzacțiile noi. Întoarce (noi, deja existente)."""
        if extras.titular:
            self.seteaza("titular", extras.titular)
        acum = datetime.now().isoformat(timespec="seconds")
        noi = 0
        with self.con:
            for t in extras.tranzactii:
                cur = self.con.execute(
                    "INSERT OR IGNORE INTO tranzactii VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (t.id, t.data.isoformat(), t.data_decontare.isoformat(), t.tip_operatiune,
                     t.debit, t.credit, t.sold, t.comerciant,
                     json.dumps(t.detalii, ensure_ascii=False), acum),
                )
                noi += cur.rowcount
        return noi, len(extras.tranzactii) - noi

    # --- setări și alegeri ----------------------------------------------------

    def seteaza(self, cheie: str, valoare: str | None) -> None:
        with self.con:
            self.con.execute("INSERT OR REPLACE INTO setari VALUES (?,?)", (cheie, valoare))

    def setare(self, cheie: str) -> str | None:
        r = self.con.execute("SELECT valoare FROM setari WHERE cheie=?", (cheie,)).fetchone()
        return r[0] if r else None

    def alege_pentru_comerciant(self, comerciant: str, categorie: str | None) -> None:
        with self.con:
            if categorie:
                self.con.execute("INSERT OR REPLACE INTO categorie_comerciant VALUES (?,?)",
                                 (comerciant, categorie))
            else:
                self.con.execute("DELETE FROM categorie_comerciant WHERE comerciant=?", (comerciant,))

    def alege_pentru_tranzactie(self, id_: str, categorie: str | None) -> None:
        with self.con:
            if categorie:
                self.con.execute("INSERT OR REPLACE INTO categorie_tranzactie VALUES (?,?)", (id_, categorie))
            else:
                self.con.execute("DELETE FROM categorie_tranzactie WHERE id=?", (id_,))

    def alegeri_comercianti(self) -> dict[str, str]:
        return dict(self.con.execute("SELECT comerciant, categorie FROM categorie_comerciant"))

    def bugete(self) -> dict[str, float]:
        return dict(self.con.execute("SELECT categorie, suma FROM bugete"))

    def seteaza_buget(self, categorie: str, suma: float | None) -> None:
        with self.con:
            if suma:
                self.con.execute("INSERT OR REPLACE INTO bugete VALUES (?,?)", (categorie, suma))
            else:
                self.con.execute("DELETE FROM bugete WHERE categorie=?", (categorie,))

    # --- citire ---------------------------------------------------------------

    def tranzactii(self) -> pd.DataFrame:
        titular = self.setare("titular")
        pe_comerciant = self.alegeri_comercianti()
        pe_tranzactie = dict(self.con.execute("SELECT id, categorie FROM categorie_tranzactie"))
        randuri = []
        for (id_, data, decontare, tip_op, debit, credit, sold, comerciant, detalii, _) in self.con.execute(
            "SELECT * FROM tranzactii ORDER BY data, data_decontare"
        ):
            detalii = json.loads(detalii)
            t = Tranzactie(id_, date.fromisoformat(data), date.fromisoformat(decontare), tip_op,
                           debit, credit, sold, comerciant, detalii)
            if id_ in pe_tranzactie:
                cat, sursa = pe_tranzactie[id_], "tranzactie"
            elif comerciant in pe_comerciant:
                cat, sursa = pe_comerciant[comerciant], "comerciant"
            else:
                cat, sursa = categorii.categorie_automata(t, titular), "automat"
            if cat not in categorii.CATEGORII:  # o categorie redenumită între timp
                cat = categorii.NECUNOSCUT
            valuta = " ".join(detalii.get("Suma", "").split())
            randuri.append((id_, pd.Timestamp(data), pd.Timestamp(decontare), tip_op, debit, credit, sold,
                            comerciant, detalii, valuta, cat, sursa, categorii.CATEGORII[cat]))
        return pd.DataFrame(randuri, columns=COLOANE)
