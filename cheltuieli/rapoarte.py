"""Calculele din spatele ecranelor. Primesc DataFrame-ul din stocare.Baza.tranzactii()."""

from __future__ import annotations

import re

import pandas as pd

TIPURI_CHELTUIELI = ("variabil", "fix", "numerar")
LUNI = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august",
        "septembrie", "octombrie", "noiembrie", "decembrie"]


def lei(x: float, zecimale: int = 0) -> str:
    """1234.5 -> „1.234 lei” (format românesc)."""
    s = f"{x:,.{zecimale}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} lei"


def nume_grup(comerciant: str) -> str:
    """Grupează locațiile aceluiași lanț: „MEGAIMAGE 0261 CRANGS25SG” -> „MEGAIMAGE”,
    „AMAZON PRIME*0H78N87G3” -> „AMAZON PRIME”."""
    s = re.sub(r"\*[A-Z0-9]{8,}$", "", comerciant.strip())
    s = re.sub(r"\s+\S*\d\S*.*$", "", s)
    return s.strip() or comerciant


def cheltuieli(df: pd.DataFrame, cu_exceptionale: bool = False) -> pd.DataFrame:
    """Doar ce e cheltuială, cu coloana `suma` pozitivă (rambursările scad din ea)."""
    tipuri = TIPURI_CHELTUIELI + (("exceptional",) if cu_exceptionale else ())
    c = df[df["tip"].isin(tipuri)].copy()
    c["suma"] = (c["debit"] - c["credit"]).round(2)
    return c


def in_perioada(df: pd.DataFrame, de_la, pana_la) -> pd.DataFrame:
    return df[(df["data"] >= pd.Timestamp(de_la)) & (df["data"] <= pd.Timestamp(pana_la))]


def pe_zile(df: pd.DataFrame, de_la, pana_la) -> pd.DataFrame:
    """Cheltuielile variabile pe fiecare zi din perioadă, inclusiv zilele fără plăți."""
    c = cheltuieli(df)
    c = c[c["tip"] == "variabil"]
    zile = pd.date_range(de_la, pana_la, freq="D")
    g = c.groupby("data")["suma"].agg(["sum", "count"]).reindex(zile, fill_value=0)
    rez = pd.DataFrame({"data": zile, "suma": g["sum"].round(2).values, "plati": g["count"].values})
    rez["zi_sapt"] = rez["data"].dt.day_of_week              # 0 = luni
    rez["saptamana"] = rez["data"] - pd.to_timedelta(rez["zi_sapt"], unit="D")
    return rez


def pe_categorii(df: pd.DataFrame) -> pd.DataFrame:
    c = cheltuieli(df)
    g = c.groupby("categorie")["suma"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    total = g["sum"].sum()
    return pd.DataFrame({
        "categorie": g.index, "suma": g["sum"].round(2).values, "plati": g["count"].values,
        "procent": (g["sum"] / total * 100).round(1).values if total else 0,
    })


def pe_luni(df: pd.DataFrame) -> pd.DataFrame:
    """Tabel lună x categorie."""
    c = cheltuieli(df)
    c["luna"] = c["data"].dt.to_period("M")
    t = c.pivot_table(index="categorie", columns="luna", values="suma", aggfunc="sum", fill_value=0)
    t = t.loc[t.sum(axis=1).sort_values(ascending=False).index]
    t.columns = [f"{LUNI[p.month - 1].capitalize()} {p.year}" for p in t.columns]
    return t.round(0)


def top_comercianti(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    c = cheltuieli(df)
    c = c[c["tip"] == "variabil"].assign(grup=lambda x: x["comerciant"].map(nume_grup))
    g = c.groupby("grup").agg(suma=("suma", "sum"), plati=("suma", "size"), categorie=("categorie", "first"))
    g = g.sort_values("suma", ascending=False).head(n).reset_index()
    return g.rename(columns={"grup": "comerciant"})


def costuri_fixe(df: pd.DataFrame) -> pd.DataFrame:
    """Costurile fixe, cu ultima plată și media lunară pe perioada analizată."""
    c = cheltuieli(df)
    c = c[c["tip"] == "fix"].assign(grup=lambda x: x["comerciant"].map(nume_grup))
    if c.empty:
        return pd.DataFrame(columns=["ce", "categorie", "ultima_plata", "ultima_suma", "pe_luna"])
    luni = max((df["data"].max() - df["data"].min()).days / 30.44, 1)
    rez = []
    for grup, g in c.groupby("grup"):
        ultima = g.sort_values("data").iloc[-1]
        rez.append((grup, ultima["categorie"], ultima["data"].date(), ultima["suma"], g["suma"].sum() / luni))
    out = pd.DataFrame(rez, columns=["ce", "categorie", "ultima_plata", "ultima_suma", "pe_luna"])
    return out.sort_values("pe_luna", ascending=False).round(2)


def comercianti(df: pd.DataFrame) -> pd.DataFrame:
    """Toți comercianții plăților cu cardul și transferurilor, cu categoria lor curentă."""
    c = cheltuieli(df)
    c = c[c["sursa_categorie"] != "tranzactie"]
    g = c.groupby("comerciant").agg(
        categorie=("categorie", "first"), sursa=("sursa_categorie", "first"),
        plati=("suma", "size"), total=("suma", "sum"), medie=("suma", "mean"),
        ultima=("data", "max"),
    ).reset_index()
    g["de_identificat"] = g["categorie"] == "De identificat"
    g[["total", "medie"]] = g[["total", "medie"]].round(2)
    return g.sort_values(["de_identificat", "total"], ascending=[False, False])


def buget(df: pd.DataFrame, bugete: dict[str, float], luna: pd.Period) -> pd.DataFrame:
    c = cheltuieli(df)
    c = c[c["data"].dt.to_period("M") == luna]
    cheltuit = c.groupby("categorie")["suma"].sum()
    rez = [(cat, b, round(float(cheltuit.get(cat, 0)), 2)) for cat, b in bugete.items()]
    out = pd.DataFrame(rez, columns=["categorie", "buget", "cheltuit"])
    out["ramas"] = out["buget"] - out["cheltuit"]
    out["procent"] = (out["cheltuit"] / out["buget"] * 100).round(0)
    return out.sort_values("procent", ascending=False)
