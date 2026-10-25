from datetime import date
from pathlib import Path

import pytest

import categorii
import parser_ing
import rapoarte as r
from stocare import Baza

EXEMPLU = Path(__file__).parent / "date" / "extras_exemplu.csv"


@pytest.fixture
def db(tmp_path):
    b = Baza(tmp_path / "test.db")
    b.importa(parser_ing.citeste(EXEMPLU.read_bytes()))
    return b


def cat(df, comerciant):
    return df[df["comerciant"] == comerciant]["categorie"].iloc[0]


def test_categorii_automate(db):
    df = db.tranzactii()
    assert cat(df, "PROFI BUCURESTI 13") == "Alimente"
    assert cat(df, "FIRMA NECUNOSCUTA SRL") == categorii.NECUNOSCUT
    assert cat(df, "5506/OFFICE 13 SEPTEMBRIE") == "Numerar (ATM)"
    assert cat(df, "Netflix.com") == "Abonamente digitale"
    assert cat(df, "Popescu Ion") == "Transfer în cont propriu"  # nume inversat față de titular
    assert cat(df, "Maria Ionescu") == "Transferuri către persoane"
    assert cat(df, "ANGAJATOR SA") == "Încasări"
    assert cat(df, "PayU*eMAG.ro") == "Cumpărături online"  # rambursare, rămâne la comerciant
    assert cat(df, "Rata Credit") == "Credit & asigurare"


def test_reimportul_nu_dubleaza(db):
    noi, vechi = db.importa(parser_ing.citeste(EXEMPLU.read_bytes()))
    assert (noi, vechi) == (0, 9)
    assert len(db.tranzactii()) == 9


def test_alegerile_tale_au_prioritate(db):
    db.alege_pentru_comerciant("FIRMA NECUNOSCUTA SRL", "Restaurante & baruri")
    df = db.tranzactii()
    assert cat(df, "FIRMA NECUNOSCUTA SRL") == "Restaurante & baruri"
    id_profi = df[df["comerciant"] == "PROFI BUCURESTI 13"]["id"].iloc[0]
    db.alege_pentru_comerciant("PROFI BUCURESTI 13", "Altele")
    db.alege_pentru_tranzactie(id_profi, "Cadouri & flori")
    assert cat(db.tranzactii(), "PROFI BUCURESTI 13") == "Cadouri & flori"
    db.alege_pentru_tranzactie(id_profi, None)
    assert cat(db.tranzactii(), "PROFI BUCURESTI 13") == "Altele"


def test_cheltuieli_exclud_transferuri_proprii_si_incasari(db):
    c = r.cheltuieli(db.tranzactii())
    # 21,18 + 1086,51 + 900 + 74,05 + 140 - 50 (rambursare) + 1721,89
    assert round(c["suma"].sum(), 2) == 3893.63
    assert "Transfer în cont propriu" not in set(c["categorie"])
    assert "Încasări" not in set(c["categorie"])


def test_pe_zile_completeaza_zilele_goale(db):
    z = r.pe_zile(db.tranzactii(), date(2026, 10, 14), date(2026, 10, 20))
    assert len(z) == 7
    assert z.set_index("data").loc["2026-10-20", "suma"] == round(21.18 + 1086.51, 2)
    assert z.set_index("data").loc["2026-10-15", "suma"] == 0  # rata e cost fix, nu variabil
    assert z.set_index("data").loc["2026-10-16", "suma"] == -50  # rambursarea eMAG


def test_nume_grup():
    assert r.nume_grup("MEGAIMAGE 0261 CRANGS25SG") == "MEGAIMAGE"
    assert r.nume_grup("AMAZON PRIME*0H78N87G3") == "AMAZON PRIME"
    assert r.nume_grup("PayU*eMAG.ro") == "PayU*eMAG.ro"
    assert r.nume_grup("MOL 91358 Bucuresti") == "MOL"


def test_lei():
    assert r.lei(1234.5) == "1.234 lei"
    assert r.lei(1234.5, 2) == "1.234,50 lei"


def test_buget(db):
    import pandas as pd
    b = r.buget(db.tranzactii(), {"Alimente": 10}, pd.Period("2026-10", "M"))
    rand = b.iloc[0]
    assert rand["cheltuit"] == 21.18 and rand["ramas"] < 0


def test_pe_luni_are_totalul_pe_primul_rand(db):
    t = r.pe_luni(db.tranzactii())
    assert t.index[0] == "Total"
    assert t.iloc[0].sum() == t.iloc[1:].sum().sum()
