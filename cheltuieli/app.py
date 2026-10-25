"""Cheltuieli zilnice din extrasele ING. Pornire: streamlit run app.py"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

import altair as alt
import pandas as pd
import streamlit as st

import categorii
import parser_ing
import rapoarte as r
from stocare import Baza

DIR = Path(__file__).parent
BAZA = Path(os.environ.get("CHELTUIELI_DB", DIR / "date" / "cheltuieli.db"))
ZILE = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]
ZILE_SCURT = ["L", "Ma", "Mi", "J", "V", "S", "D"]
# culori pentru calendar, de la „puțin” la „mult”
# zi fără plăți, sub 100, 100–300, peste 300, peste 1000 lei
PRAGURI = [0.01, 100, 300, 1000]
CULORI = ["#e1e0d9", "#a8c97f", "#f4a960", "#de5b4f", "#b9a2c8"]

st.set_page_config(page_title="Cheltuieli", layout="wide")


@st.cache_resource
def baza() -> Baza:
    return Baza(BAZA)


db = baza()


def importa_fisiere(fisiere: list[tuple[str, bytes]]) -> None:
    for nume, continut in fisiere:
        try:
            extras = parser_ing.citeste(continut)
        except Exception as e:  # fișier stricat sau alt format
            st.sidebar.error(f"{nume}: nu l-am putut citi ({e})")
            continue
        if not extras.tranzactii:
            st.sidebar.warning(f"{nume}: nu conține tranzacții în formatul ING")
            continue
        if all(t.debit == 0 and t.credit == 0 for t in extras.tranzactii):
            st.sidebar.error(f"{nume}: toate sumele au ieșit 0 lei, probabil ING a schimbat formatul. "
                             "Nu l-am importat.")
            continue
        noi, vechi = db.importa(extras)
        st.sidebar.success(f"{nume}: {noi} tranzacții noi" + (f", {vechi} existau deja" if vechi else ""))


# --- bara laterală: import și perioadă ------------------------------------------

st.sidebar.header("Import extras")
incarcate = st.sidebar.file_uploader("Fișiere CSV din ING Home'Bank", type="csv", accept_multiple_files=True)
procesate = st.session_state.setdefault("procesate", set())
noi = [f for f in incarcate or [] if (f.name, f.size) not in procesate]
if noi:
    importa_fisiere([(f.name, f.getvalue()) for f in noi])
    procesate.update((f.name, f.size) for f in noi)

folder = db.setare("folder_descarcari") or str(Path.home() / "Downloads")
with st.sidebar.expander("Import din folderul de descărcări"):
    folder_nou = st.text_input("Folder", folder)
    if folder_nou != folder:
        db.seteaza("folder_descarcari", folder_nou)
        folder = folder_nou
    if st.button("Caută fișiere Tranzactii_*.csv"):
        gasite = sorted(Path(folder).glob("Tranzactii_*.csv"))
        if not gasite:
            st.warning("Nu am găsit niciun fișier.")
        importa_fisiere([(p.name, p.read_bytes()) for p in gasite])
    st.caption("Poți importa același fișier de mai multe ori: tranzacțiile existente nu se dublează.")

toate = db.tranzactii()
if toate.empty:
    st.title("Cheltuieli zilnice")
    st.info(
        "Încă nu ai date. Descarcă din ING Home'Bank lista de tranzacții în format CSV "
        "și încarc-o din bara din stânga."
    )
    st.stop()

prima, ultima = toate["data"].min().date(), toate["data"].max().date()
st.sidebar.header("Perioadă")
inceput_luna = ultima.replace(day=1)
luna_trecuta = (inceput_luna - timedelta(days=1)).replace(day=1)
optiuni = {
    "Ultimele 30 de zile": (ultima - timedelta(days=29), ultima),
    "Luna aceasta": (inceput_luna, ultima),
    "Luna trecută": (luna_trecuta, inceput_luna - timedelta(days=1)),
    "Ultimele 3 luni": ((pd.Timestamp(ultima) - pd.DateOffset(months=3)).date() + timedelta(days=1), ultima),
    "Tot istoricul": (prima, ultima),
}
alegere = st.sidebar.radio("Arată", [*optiuni, "Alte date"], index=3, label_visibility="collapsed")
if alegere == "Alte date":
    interval = st.sidebar.date_input("Interval", (prima, ultima), min_value=prima, max_value=ultima,
                                     format="DD.MM.YYYY")
    de_la, pana_la = (interval if len(interval) == 2 else (interval[0], interval[0]))
else:
    de_la, pana_la = optiuni[alegere]
de_la = max(de_la, prima)
df = r.in_perioada(toate, de_la, pana_la)

# --- sus: cifrele principale -------------------------------------------------------

st.title("Cheltuieli zilnice")
st.caption(f"{de_la:%d.%m.%Y} – {pana_la:%d.%m.%Y} · {len(df)} tranzacții · ziua = data plății (autorizării)")

chelt = r.cheltuieli(df)
zile = (pana_la - de_la).days + 1
exceptionale = df[df["tip"] == "exceptional"]["debit"].sum()
necunoscute = chelt[chelt["categorie"] == categorii.NECUNOSCUT]
venit = df[df["tip"] == "venit"]["credit"].sum()

k = st.columns(4)
k[0].metric("Cheltuieli", r.lei(chelt["suma"].sum()),
            help="Fără transferurile în conturile tale și fără cheltuielile excepționale.")
k[1].metric("Medie pe zi (variabile)", r.lei(chelt[chelt["tip"] == "variabil"]["suma"].sum() / zile),
            help="Fără costuri fixe și numerar.")
k[2].metric("Numerar retras", r.lei(chelt[chelt["tip"] == "numerar"]["suma"].sum()))
k[3].metric("De identificat", r.lei(necunoscute["suma"].sum()),
            help="Plăți pe care nu le-am putut încadra. Le rezolvi în tabul „Comercianți”.")
note = []
if exceptionale:
    note.append(f"Excepționale (nu intră în total): {r.lei(exceptionale)}")
if venit:
    note.append(f"Încasări: {r.lei(venit)}")
if note:
    st.caption(" · ".join(note))

tab_zile, tab_rap, tab_com, tab_buget = st.tabs(["Pe zile", "Rapoarte", "Comercianți", "Bugete"])


def salveaza_editari(cheie: str, tabel: pd.DataFrame, coloana_id: str, salveaza) -> None:
    """Citește modificările dintr-un st.data_editor și le salvează."""
    modificari = st.session_state.get(cheie, {}).get("edited_rows", {})
    schimbat = False
    for rand, valori in modificari.items():
        if "categorie" in valori:
            salveaza(tabel.iloc[int(rand)][coloana_id], valori["categorie"])
            schimbat = True
    if schimbat:
        st.session_state.pop(cheie, None)
        st.rerun()


# --- Pe zile -----------------------------------------------------------------------

with tab_zile:
    z = r.pe_zile(df, de_la, pana_la)
    z["eticheta"] = z["suma"].map(lambda s: r.lei(s, 2))
    z["ziua"] = z["data"].dt.strftime("%d.%m.%Y")
    z["sapt"] = z["saptamana"].dt.strftime("%d.%m")
    selectie = alt.selection_point(fields=["ziua"], name="zi")
    calendar = (
        alt.Chart(z)
        .mark_rect(cornerRadius=4, stroke="white", strokeWidth=2)
        .encode(
            x=alt.X("sapt:O", title="săptămâna care începe pe", sort=list(z["sapt"].unique()),
                    axis=alt.Axis(labelAngle=0, labelOverlap=True)),
            y=alt.Y("zi_sapt:O", title=None, axis=alt.Axis(labelExpr=f"{ZILE_SCURT}[datum.value]", labelOverlap=False)),
            color=alt.Color("suma:Q", title="lei / zi",
                            scale=alt.Scale(type="threshold", domain=PRAGURI, range=CULORI),
                            legend=alt.Legend(orient="bottom")),
            opacity=alt.condition(selectie, alt.value(1), alt.value(0.35)),
            tooltip=[alt.Tooltip("ziua:N", title="Ziua"), alt.Tooltip("eticheta:N", title="Cheltuit"),
                     alt.Tooltip("plati:Q", title="Plăți")],
        )
        .add_params(selectie)
        .properties(height=alt.Step(30))
    )
    ev = st.altair_chart(calendar, use_container_width=True, on_select="rerun", key="calendar")
    st.caption("Apasă pe o zi. În calendar intră doar cheltuielile variabile (fără rate, abonamente, numerar).")

    puncte = (ev or {}).get("selection", {}).get("zi") or []
    ales = puncte[0].get("ziua") if puncte else None
    if ales:
        zi = pd.to_datetime(ales, format="%d.%m.%Y").date()
    else:
        zi_maxima = z.loc[z["suma"].idxmax(), "data"].date() if z["suma"].any() else pana_la
        zi = st.session_state.get("zi", zi_maxima)
    zi = st.date_input("Ziua", zi, min_value=de_la, max_value=pana_la, format="DD.MM.YYYY")
    st.session_state["zi"] = zi

    din_zi = df[(df["data"] == pd.Timestamp(zi)) & (df["tip"] != "intern")].copy()
    st.subheader(f"{ZILE[zi.weekday()]}, {zi:%d.%m.%Y}")
    if din_zi.empty:
        st.write("Nicio plată în ziua asta.")
    else:
        din_zi["suma"] = din_zi["debit"] - din_zi["credit"]
        st.write(f"**{r.lei(din_zi['suma'].sum(), 2)}** în {len(din_zi)} plăți")
        tabel = din_zi[["id", "comerciant", "categorie", "suma", "valuta", "tip_operatiune"]].reset_index(drop=True)
        st.data_editor(
            tabel, key="editor_zi", hide_index=True, use_container_width=True,
            disabled=["comerciant", "suma", "valuta", "tip_operatiune"],
            column_order=["comerciant", "categorie", "suma", "valuta", "tip_operatiune"],
            column_config={
                "comerciant": "Comerciant",
                "categorie": st.column_config.SelectboxColumn("Categorie", options=list(categorii.CATEGORII),
                                                              required=True),
                "suma": st.column_config.NumberColumn("Lei", format="%.2f"),
                "valuta": "În valută",
                "tip_operatiune": "Operațiune",
            },
        )
        st.caption("Schimbarea categoriei aici se aplică doar acestei plăți. "
                   "Pentru toate plățile la un comerciant, folosește tabul „Comercianți”.")
        salveaza_editari("editor_zi", tabel, "id", db.alege_pentru_tranzactie)

# --- Rapoarte ------------------------------------------------------------------------

with tab_rap:
    st.subheader("Pe categorii")
    pc = r.pe_categorii(df)
    pc["eticheta"] = pc["suma"].map(r.lei)
    bare = alt.Chart(pc).encode(
        y=alt.Y("categorie:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
        x=alt.X("suma:Q", title=None, axis=alt.Axis(grid=False, labels=False, ticks=False, domain=False)),
        tooltip=[alt.Tooltip("categorie:N", title="Categorie"), alt.Tooltip("eticheta:N", title="Total"),
                 alt.Tooltip("procent:Q", title="% din total"), alt.Tooltip("plati:Q", title="Plăți")],
    )
    st.altair_chart(
        bare.mark_bar(color="#2a78d6", cornerRadiusEnd=4, height=14)
        + bare.mark_text(align="left", dx=6).encode(text="eticheta:N"),
        use_container_width=True,
    )

    st.subheader("Pe luni")
    pl = r.pe_luni(df)
    st.dataframe(pl, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="%d") for c in pl.columns})

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top comercianți")
        st.dataframe(r.top_comercianti(df), hide_index=True, use_container_width=True, column_config={
            "comerciant": "Comerciant", "categorie": "Categorie", "plati": "Plăți",
            "suma": st.column_config.NumberColumn("Total (lei)", format="%.0f"),
        })
    with c2:
        st.subheader("Costuri fixe și abonamente")
        cf = r.costuri_fixe(df)
        st.dataframe(cf, hide_index=True, use_container_width=True, column_config={
            "ce": "Ce", "categorie": "Categorie",
            "ultima_plata": st.column_config.DateColumn("Ultima plată", format="DD.MM.YYYY"),
            "ultima_suma": st.column_config.NumberColumn("Ultima sumă", format="%.2f"),
            "pe_luna": st.column_config.NumberColumn("≈ pe lună", format="%.0f"),
        })
        st.caption(f"Total ≈ {r.lei(cf['pe_luna'].sum())} pe lună (media pe perioada aleasă).")

    with st.expander("Toate tranzacțiile din perioadă"):
        export = df.drop(columns=["detalii", "id", "sursa_categorie"]).sort_values("data", ascending=False)
        st.dataframe(export, hide_index=True, use_container_width=True)
        st.download_button("Descarcă CSV", export.to_csv(index=False).encode("utf-8-sig"),
                           f"cheltuieli_{de_la}_{pana_la}.csv", "text/csv")

# --- Comercianți ---------------------------------------------------------------------

with tab_com:
    st.write(
        "Alege categoria o singură dată pentru fiecare comerciant; se aplică automat și la importurile viitoare. "
        "Cei „De identificat” sunt primii în listă."
    )
    doar_necunoscuti = st.toggle("Doar cei de identificat", value=not necunoscute.empty)
    com = r.comercianti(toate)  # pe tot istoricul, nu doar în perioada aleasă
    if doar_necunoscuti:
        com = com[com["de_identificat"]]
    oras = toate.set_index("comerciant")["detalii"].map(lambda d: parser_ing.localitate(d.get("Tranzactie la", "")))
    oras = oras[~oras.index.duplicated()]
    com = com.assign(cauta=[
        "https://www.google.com/search?q=" + quote_plus(f"{c} {oras.get(c, '')}") for c in com["comerciant"]
    ]).reset_index(drop=True)
    if com.empty:
        st.success("Toți comercianții au o categorie.")
    else:
        st.data_editor(
            com, key="editor_com", hide_index=True, use_container_width=True, height=600,
            column_order=["comerciant", "categorie", "plati", "medie", "total", "ultima", "sursa", "cauta"],
            disabled=["comerciant", "plati", "medie", "total", "ultima", "sursa", "cauta"],
            column_config={
                "comerciant": "Comerciant (cum apare în extras)",
                "categorie": st.column_config.SelectboxColumn("Categorie", options=list(categorii.CATEGORII),
                                                              required=True),
                "plati": "Plăți",
                "medie": st.column_config.NumberColumn("Medie", format="%.2f"),
                "total": st.column_config.NumberColumn("Total", format="%.2f"),
                "ultima": st.column_config.DateColumn("Ultima dată", format="DD.MM.YYYY"),
                "sursa": st.column_config.TextColumn("Stabilită", help="automat = după reguli; comerciant = aleasă de tine"),
                "cauta": st.column_config.LinkColumn("Caută online", display_text="caută"),
            },
        )
        salveaza_editari("editor_com", com, "comerciant", db.alege_pentru_comerciant)

# --- Bugete --------------------------------------------------------------------------

with tab_buget:
    st.write("Opțional: pune o limită lunară pe categoriile pe care vrei să le ții sub control. "
             "Lasă gol unde nu vrei buget.")
    bugete = db.bugete()
    cat_buget = [c for c, t in categorii.CATEGORII.items() if t in ("variabil", "fix") and c != categorii.NECUNOSCUT]
    luna_curenta = pd.Timestamp(ultima).to_period("M")
    istoric = r.cheltuieli(toate).assign(luna=lambda x: x["data"].dt.to_period("M"))
    # doar lunile încheiate și acoperite complet de extrase
    prima_luna = pd.Timestamp(prima).to_period("M") + (0 if prima.day == 1 else 1)
    istoric = istoric[(istoric["luna"] < luna_curenta) & (istoric["luna"] >= prima_luna)]
    media = istoric.groupby(["categorie", "luna"])["suma"].sum().groupby("categorie").mean()
    tabel_b = pd.DataFrame({
        "categorie": cat_buget,
        "media": [round(float(media.get(c, 0))) for c in cat_buget],
        "buget": [bugete.get(c, float("nan")) for c in cat_buget],
    })
    rez = st.data_editor(
        tabel_b, key="editor_buget", hide_index=True, use_container_width=True, disabled=["categorie", "media"],
        column_config={
            "categorie": "Categorie",
            "media": st.column_config.NumberColumn("Media lunară până acum", format="%d lei",
                                                   help="Media lunilor încheiate din istoric."),
            "buget": st.column_config.NumberColumn("Buget lunar (lei)", min_value=0, step=50),
        },
    )
    if st.button("Salvează bugetele"):
        for _, rand in rez.iterrows():
            db.seteaza_buget(rand["categorie"], None if pd.isna(rand["buget"]) else float(rand["buget"]))
        st.rerun()

    if bugete:
        luni = sorted(toate["data"].dt.to_period("M").unique(), reverse=True)
        luna = st.selectbox("Luna", luni, format_func=lambda p: f"{r.LUNI[p.month - 1].capitalize()} {p.year}")
        for _, b in r.buget(toate, bugete, luna).iterrows():
            depasit = b["cheltuit"] > b["buget"]
            text = (f"**{b['categorie']}**: {r.lei(b['cheltuit'])} din {r.lei(b['buget'])}"
                    + (f" · ⚠️ depășit cu {r.lei(-b['ramas'])}" if depasit else f" · rămân {r.lei(b['ramas'])}"))
            st.progress(min(b["procent"] / 100, 1.0), text=text)
