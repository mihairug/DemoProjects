"""Calculele din spatele ecranelor. Primesc DataFrame-ul din stocare.Baza.tranzactii().

Coloanele tabelelor întoarse de aici (ex. „plati”, „procent”) aparțin doar raportului
respectiv; coloanele tabelului de tranzacții sunt în constante.Col.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from constante import LUNI, TIPURI_CHELTUIELI, Cat, Col, Sursa, Tip


def lei(x: float, zecimale: int = 0) -> str:
    """1234.5 -> „1.234 lei” (format românesc)."""
    s = f"{x:,.{zecimale}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} lei"


def nume_luna(p: pd.Period) -> str:
    """Period('2026-10') -> „Octombrie 2026”."""
    return f"{LUNI[p.month - 1].capitalize()} {p.year}"


def nume_grup(comerciant: str) -> str:
    """Grupează locațiile aceluiași lanț: „MEGAIMAGE 0261 CRANGS25SG” -> „MEGAIMAGE”,
    „AMAZON PRIME*0H78N87G3” -> „AMAZON PRIME”."""
    s = re.sub(r"\*[A-Z0-9]{8,}$", "", comerciant.strip())
    s = re.sub(r"\s+\S*\d\S*.*$", "", s)
    return s.strip() or comerciant


def _simplu(text: str) -> str:
    """„Mega Image” și „MEGAIMAGE”, „cafea” și „CAFEA” arată la fel: fără diacritice, spații, semne."""
    fara_diacritice = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", fara_diacritice.lower())


def potriveste(nume: str, cautare: str) -> bool:
    """Toate cuvintele căutate apar în nume, oriunde, fără să conteze literele mari sau spațiile."""
    simplu = _simplu(nume)
    return all(_simplu(cuvant) in simplu for cuvant in cautare.split())


def cheltuieli(df: pd.DataFrame) -> pd.DataFrame:
    """Doar ce e cheltuială, cu coloana `suma` pozitivă (rambursările scad din ea)."""
    c = df[df[Col.TIP].isin(TIPURI_CHELTUIELI)].copy()
    c[Col.SUMA] = (c[Col.DEBIT] - c[Col.CREDIT]).round(2)
    return c


def in_perioada(df: pd.DataFrame, de_la, pana_la) -> pd.DataFrame:
    return df[(df[Col.DATA] >= pd.Timestamp(de_la)) & (df[Col.DATA] <= pd.Timestamp(pana_la))]


def pe_zile(df: pd.DataFrame, de_la, pana_la) -> pd.DataFrame:
    """Toate plățile (variabile, fixe, numerar, excepționale) pe fiecare zi din perioadă,
    inclusiv zilele fără plăți. Fără transferuri proprii și încasări."""
    c = cheltuieli(df)
    zile = pd.date_range(de_la, pana_la, freq="D")
    g = c.groupby(Col.DATA)[Col.SUMA].agg(["sum", "count"]).reindex(zile, fill_value=0)
    rez = pd.DataFrame({Col.DATA: zile, Col.SUMA: g["sum"].round(2).values, "plati": g["count"].values})
    rez["zi_sapt"] = rez[Col.DATA].dt.day_of_week              # 0 = luni
    rez["saptamana"] = rez[Col.DATA] - pd.to_timedelta(rez["zi_sapt"], unit="D")
    return rez


def pe_categorii(df: pd.DataFrame) -> pd.DataFrame:
    c = cheltuieli(df)
    g = c.groupby(Col.CATEGORIE)[Col.SUMA].agg(["sum", "count"]).sort_values("sum", ascending=False)
    total = g["sum"].sum()
    return pd.DataFrame({
        Col.CATEGORIE: g.index, Col.SUMA: g["sum"].round(2).values, "plati": g["count"].values,
        "procent": (g["sum"] / total * 100).round(1).values if total else 0,
    })


def pe_luni(df: pd.DataFrame) -> pd.DataFrame:
    """Tabel lună x categorie, cu totalul pe primul rând."""
    c = cheltuieli(df)
    c["luna"] = c[Col.DATA].dt.to_period("M")
    t = c.pivot_table(index=Col.CATEGORIE, columns="luna", values=Col.SUMA, aggfunc="sum", fill_value=0)
    t = t.loc[t.sum(axis=1).sort_values(ascending=False).index]
    t.columns = [nume_luna(p) for p in t.columns]
    total = t.sum().to_frame("Total").T
    return pd.concat([total, t]).round(0)


def top_comercianti(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    c = cheltuieli(df)
    c = c[c[Col.TIP] == Tip.VARIABIL].assign(grup=lambda x: x[Col.COMERCIANT].map(nume_grup))
    g = c.groupby("grup").agg(suma=(Col.SUMA, "sum"), plati=(Col.SUMA, "size"),
                              categorie=(Col.CATEGORIE, "first"))
    g = g.sort_values(Col.SUMA, ascending=False).head(n).reset_index()
    return g.rename(columns={"grup": Col.COMERCIANT})


def costuri_fixe(df: pd.DataFrame) -> pd.DataFrame:
    """Costurile fixe, cu ultima plată și media lunară pe perioada analizată."""
    coloane = ["ce", Col.CATEGORIE, "ultima_plata", "ultima_suma", "pe_luna"]
    c = cheltuieli(df)
    c = c[c[Col.TIP] == Tip.FIX].assign(grup=lambda x: x[Col.COMERCIANT].map(nume_grup))
    if c.empty:
        return pd.DataFrame(columns=coloane)
    luni = max((df[Col.DATA].max() - df[Col.DATA].min()).days / 30.44, 1)
    rez = []
    for grup, g in c.groupby("grup"):
        ultima = g.sort_values(Col.DATA).iloc[-1]
        rez.append((grup, ultima[Col.CATEGORIE], ultima[Col.DATA].date(), ultima[Col.SUMA],
                    g[Col.SUMA].sum() / luni))
    out = pd.DataFrame(rez, columns=coloane)
    return out.sort_values("pe_luna", ascending=False).round(2)


def comercianti(df: pd.DataFrame) -> pd.DataFrame:
    """Toți comercianții plăților cu cardul și transferurilor, cu categoria lor curentă."""
    c = cheltuieli(df)
    c = c[c[Col.SURSA] != Sursa.TRANZACTIE]
    g = c.groupby(Col.COMERCIANT).agg(
        categorie=(Col.CATEGORIE, "first"), sursa=(Col.SURSA, "first"),
        plati=(Col.SUMA, "size"), total=(Col.SUMA, "sum"), medie=(Col.SUMA, "mean"),
        ultima=(Col.DATA, "max"),
    ).reset_index()
    g["de_identificat"] = g[Col.CATEGORIE] == Cat.NECUNOSCUT
    g[["total", "medie"]] = g[["total", "medie"]].round(2)
    return g.sort_values(["de_identificat", "total"], ascending=[False, False])


def buget(df: pd.DataFrame, bugete: dict[str, float], luna: pd.Period) -> pd.DataFrame:
    c = cheltuieli(df)
    c = c[c[Col.DATA].dt.to_period("M") == luna]
    cheltuit = c.groupby(Col.CATEGORIE)[Col.SUMA].sum()
    rez = [(cat, b, round(float(cheltuit.get(cat, 0)), 2)) for cat, b in bugete.items()]
    out = pd.DataFrame(rez, columns=[Col.CATEGORIE, "buget", "cheltuit"])
    out["ramas"] = out["buget"] - out["cheltuit"]
    out["procent"] = (out["cheltuit"] / out["buget"] * 100).round(0)
    return out.sort_values("procent", ascending=False)
