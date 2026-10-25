"""Cheltuieli zilnice din extrasele ING. Pornire: streamlit run app.py"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
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
ETICHETE = ["0", "sub 100", "100–300", "300–1000", "peste 1000 lei"]

st.set_page_config(page_title="Cheltuieli", layout="wide")
# textul din grafice trebuie să se vadă și pe tema închisă
CULOARE_TEXT = "#f0efec" if st.context.theme.type == "dark" else "#31333f"


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

with st.sidebar.expander("Șterge datele"):
    st.write("Șterge toate tranzacțiile din baza de date, de exemplu ca să reimporți extrasele de la zero.")
    si_alegerile = st.checkbox("Șterge și categoriile alese de mine și bugetele")
    sigur = st.checkbox("Da, vreau să șterg tot")
    if st.button("Șterge tot", type="primary", disabled=not sigur):
        copie = BAZA.with_name(f"{BAZA.stem}_inainte_de_stergere_{datetime.now():%Y-%m-%d_%H-%M-%S}.db")
        db.backup(copie)
        n = db.sterge_tot(si_alegerile)
        st.session_state.pop("ziua", None)
        st.session_state["mesaj_stergere"] = f"Am șters {n} tranzacții. Copie de siguranță: {copie.name}"
        st.rerun()
    st.caption("Înainte de ștergere se face automat o copie a bazei de date în folderul `date`.")
if "mesaj_stergere" in st.session_state:
    st.sidebar.success(st.session_state.pop("mesaj_stergere"))

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
            help="Toate plățile, inclusiv cele excepționale. Fără transferurile în conturile tale și încasări.")
k[1].metric("Medie pe zi (variabile)", r.lei(chelt[chelt["tip"] == "variabil"]["suma"].sum() / zile),
            help="Fără costuri fixe și numerar.")
k[2].metric("Numerar retras", r.lei(chelt[chelt["tip"] == "numerar"]["suma"].sum()))
k[3].metric("De identificat", r.lei(necunoscute["suma"].sum()),
            help="Plăți pe care nu le-am putut încadra. Le rezolvi în tabul „Comercianți”.")
note = []
if exceptionale:
    note.append(f"Din care excepționale: {r.lei(exceptionale)}")
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
                            legend=None),
            opacity=alt.condition(selectie, alt.value(1), alt.value(0.35)),
            tooltip=[alt.Tooltip("ziua:N", title="Ziua"), alt.Tooltip("eticheta:N", title="Cheltuit"),
                     alt.Tooltip("plati:Q", title="Plăți")],
        )
        .add_params(selectie)
        .properties(height=alt.Step(30))
    )
    ev = st.altair_chart(calendar, use_container_width=True, on_select="rerun", key="calendar")
    st.markdown(
        " &nbsp; ".join(f'<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
                        f'background:{c};vertical-align:middle"></span> {t}' for c, t in zip(CULORI, ETICHETE)),
        unsafe_allow_html=True,
    )
    st.caption("Apasă pe o zi. În calendar intră toate plățile: variabile, fixe, numerar și excepționale. "
               "Nu intră transferurile în conturile tale și încasările.")

    puncte = (ev or {}).get("selection", {}).get("zi") or []
    ales = puncte[0].get("ziua") if puncte else None
    zi_maxima = z.loc[z["suma"].idxmax(), "data"].date() if z["suma"].any() else pana_la
    # un clic nou în calendar alege ziua; altfel rămâne cea din câmpul „Ziua”
    if ales and ales != st.session_state.get("clic_calendar"):
        st.session_state["ziua"] = pd.to_datetime(ales, format="%d.%m.%Y").date()
    st.session_state["clic_calendar"] = ales
    ziua = st.session_state.get("ziua")
    if ziua is None or not de_la <= ziua <= pana_la:  # ziua aleasă înainte nu e în perioada nouă
        st.session_state["ziua"] = zi_maxima
    zi = st.date_input("Ziua", key="ziua", min_value=de_la, max_value=pana_la, format="DD.MM.YYYY")

    in_zi = df[df["data"] == pd.Timestamp(zi)]
    din_zi = r.cheltuieli(in_zi)
    st.subheader(f"{ZILE[zi.weekday()]}, {zi:%d.%m.%Y}")
    if din_zi.empty:
        st.write("Nicio plată în ziua asta.")
    else:
        variabile = din_zi[din_zi["tip"] == "variabil"]
        altele = din_zi[din_zi["tip"] != "variabil"]
        text = f"**{r.lei(din_zi['suma'].sum(), 2)}** în {len(din_zi)} plăți"
        if not altele.empty and not variabile.empty:
            text += (f" · din care {r.lei(variabile['suma'].sum(), 2)} variabile și "
                     f"{r.lei(altele['suma'].sum(), 2)} fixe, numerar sau excepționale")
        st.write(text)
        for cheie, titlu, parte in [("editor_zi", "Cheltuieli variabile", variabile),
                                    ("editor_zi_altele", "Costuri fixe, numerar și excepționale", altele)]:
            if parte.empty:
                continue
            if not altele.empty and not variabile.empty:
                st.markdown(f"**{titlu}** · {r.lei(parte['suma'].sum(), 2)}")
            tabel = parte[["id", "comerciant", "categorie", "suma", "valuta", "tip_operatiune"]].reset_index(drop=True)
            st.data_editor(
                tabel, key=cheie, hide_index=True, use_container_width=True,
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
            salveaza_editari(cheie, tabel, "id", db.alege_pentru_tranzactie)
        st.caption("Schimbarea categoriei aici se aplică doar acestei plăți. "
                   "Pentru toate plățile la un comerciant, folosește tabul „Comercianți”.")

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
        + bare.mark_text(align="left", dx=6, color=CULOARE_TEXT).encode(text="eticheta:N"),
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
    cautare = st.text_input("Caută comerciant", placeholder="ex. mega image, emag, marina",
                            help="Caută în tot istoricul, după o parte din nume. Literele mari, spațiile "
                                 "și diacriticele nu contează.").strip()
    doar_necunoscuti = st.toggle("Doar cei de identificat", value=not necunoscute.empty, disabled=bool(cautare))
    com = r.comercianti(toate)  # pe tot istoricul, nu doar în perioada aleasă
    if cautare:
        com = com[com["comerciant"].map(lambda c: r.potriveste(c, cautare))]
    elif doar_necunoscuti:
        com = com[com["de_identificat"]]
    oras = toate.set_index("comerciant")["detalii"].map(lambda d: parser_ing.localitate(d.get("Tranzactie la", "")))
    oras = oras[~oras.index.duplicated()]
    com = com.assign(cauta=[
        "https://www.google.com/search?q=" + quote_plus(f"{c} {oras.get(c, '')}") for c in com["comerciant"]
    ]).reset_index(drop=True)
    cheie_editor = f"editor_com_{cautare}"  # altă căutare, alt tabel: modificările nu se amestecă
    if com.empty:
        if cautare:
            st.info(f"Niciun comerciant nu se potrivește cu „{cautare}”.")
        else:
            st.success("Toți comercianții au o categorie.")
    else:
        if cautare:
            gasiti = "un comerciant găsit" if len(com) == 1 else f"{len(com)} comercianți găsiți"
            st.caption(f"{gasiti} · {r.lei(com['total'].sum(), 2)} în {com['plati'].sum()} plăți")
        st.data_editor(
            com, key=cheie_editor, hide_index=True, use_container_width=True, height=600,
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
        salveaza_editari(cheie_editor, com, "comerciant", db.alege_pentru_comerciant)

        if cautare:
            st.subheader("Plățile găsite")
            plati = r.cheltuieli(toate)
            plati = plati[plati["comerciant"].isin(com["comerciant"])].sort_values("data", ascending=False)
            st.dataframe(
                plati[["data", "comerciant", "categorie", "suma", "valuta"]], hide_index=True,
                use_container_width=True,
                column_config={
                    "data": st.column_config.DateColumn("Ziua", format="DD.MM.YYYY"),
                    "comerciant": "Comerciant", "categorie": "Categorie",
                    "suma": st.column_config.NumberColumn("Lei", format="%.2f"), "valuta": "În valută",
                },
            )
            pe_luna = plati.groupby(plati["data"].dt.to_period("M"))["suma"].sum()
            st.caption("Pe luni: " + " · ".join(
                f"{r.LUNI[p.month - 1]} {r.lei(v)}" for p, v in pe_luna.items()))

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
