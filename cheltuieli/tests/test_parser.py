from datetime import date
from pathlib import Path

import pytest

import parser_ing

EXEMPLU = Path(__file__).parent / "date" / "extras_exemplu.csv"


@pytest.fixture
def extras():
    return parser_ing.citeste(EXEMPLU.read_bytes())


def test_citeste_toate_tranzactiile_peste_pagini(extras):
    assert len(extras.tranzactii) == 9
    assert extras.titular == "Ion Popescu"


def test_ziua_este_data_autorizarii(extras):
    t = extras.tranzactii[0]
    assert t.data == date(2026, 10, 20)
    assert t.data_decontare == date(2026, 10, 22)


def test_fara_autorizare_ziua_este_decontarea(extras):
    rata = extras.tranzactii[-1]
    assert rata.tip_operatiune == "Rata Credit"
    assert rata.data == date(2026, 10, 15)


def test_sume_cu_separator_de_mii(extras):
    assert extras.tranzactii[1].debit == 1086.51
    assert extras.tranzactii[4].debit == 10000.0
    assert extras.tranzactii[6].credit == 5000.0
    assert extras.tranzactii[6].suma == 5000.0
    assert extras.tranzactii[0].suma == -21.18


def test_comerciant_si_detalii(extras):
    assert extras.tranzactii[0].comerciant == "PROFI BUCURESTI 13"
    assert extras.tranzactii[3].detalii["Suma"] == "13,99  EUR"
    assert extras.tranzactii[4].comerciant == "Popescu Ion"
    assert extras.tranzactii[6].comerciant == "ANGAJATOR SA"


def test_semnaturile_nu_intra_in_detalii(extras):
    atm = extras.tranzactii[2]
    assert set(atm.detalii) == {"Data finalizarii (decontarii)", "Numar card", "Tranzactie la",
                                "Data autorizarii", "Numar autorizare"}


def test_id_stabil_si_unic(extras):
    din_nou = parser_ing.citeste(EXEMPLU.read_text(encoding="utf-8"))
    assert [t.id for t in extras.tranzactii] == [t.id for t in din_nou.tranzactii]
    assert len({t.id for t in extras.tranzactii}) == len(extras.tranzactii)


def test_cnp_si_adresa_nu_sunt_pastrate(extras):
    text = repr(extras)
    assert "1990101123456" not in text
    assert "Exemplu" not in text


def test_localitate():
    assert parser_ing.localitate("MEGAIMAGE 0261 CRANGS25SG  RO  BUCURESTI") == "BUCURESTI"
    assert parser_ing.localitate("FARA ORAS") == ""
