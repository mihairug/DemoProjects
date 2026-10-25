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
from constante import (
    CULOARE_BARE, CULOARE_TEXT_DESCHIS, CULOARE_TEXT_INCHIS, CULORI, ETICHETE, FORMAT_ZI, FORMAT_ZI_SCURT,
    FORMAT_ZI_UI, PRAGURI, TIPURI_CU_BUGET, ZILE, ZILE_SCURT, Cat, Col, Ing, Sesiune, Setare, Tip,
)
from stocare import Baza

DIR = Path(__file__).parent
BAZA = Path(os.environ.get("CHELTUIELI_DB", DIR / "date" / "cheltuieli.db"))
OPTIUNI_CATEGORIE = list(categorii.CATEGORII)

st.set_page_config(page_title="Cheltuieli", layout="wide")
# textul din grafice trebuie să se vadă și pe tema închisă
CULOARE_TEXT = CULOARE_TEXT_INCHIS if st.context.theme.type == "dark" else CULOARE_TEXT_DESCHIS


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
procesate = st.session_state.setdefault(Sesiune.PROCESATE, set())
noi = [f for f in incarcate or [] if (f.name, f.size) not in procesate]
if noi:
    importa_fisiere([(f.name, f.getvalue()) for f in noi])
    procesate.update((f.name, f.size) for f in noi)

folder = db.setare(Setare.FOLDER_DESCARCARI) or str(Path.home() / "Downloads")
with st.sidebar.expander("Import din folderul de descărcări"):
    folder_nou = st.text_input("Folder", folder)
    if folder_nou != folder:
        db.seteaza(Setare.FOLDER_DESCARCARI, folder_nou)
        folder = folder_nou
    if st.button(f"Caută fișiere {Ing.FISIERE}"):
        gasite = sorted(Path(folder).glob(Ing.FISIERE))
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
        st.session_state.pop(Sesiune.ZIUA, None)
        st.session_state[Sesiune.MESAJ_STERGERE] = f"Am șters {n} tranzacții. Copie de siguranță: {copie.name}"
        st.rerun()
    st.caption("Înainte de ștergere se face automat o copie a bazei de date în folderul `date`.")
if Sesiune.MESAJ_STERGERE in st.session_state:
    st.sidebar.success(st.session_state.pop(Sesiune.MESAJ_STERGERE))

toate = db.tranzactii()
if toate.empty:
    st.title("Cheltuieli zilnice")
    st.info(
        "Încă nu ai date. Descarcă din ING Home'Bank lista de tranzacții în format CSV "
        "și încarc-o din bara din stânga."
    )
    st.stop()

prima, ultima = toate[Col.DATA].min().date(), toate[Col.DATA].max().date()
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
                                     format=FORMAT_ZI_UI)
    de_la, pana_la = (interval if len(interval) == 2 else (interval[0], interval[0]))
else:
    de_la, pana_la = optiuni[alegere]
de_la = max(de_la, prima)
df = r.in_perioada(toate, de_la, pana_la)

# --- sus: cifrele principale -------------------------------------------------------

st.title("Cheltuieli zilnice")
st.caption(f"{de_la:{FORMAT_ZI}} – {pana_la:{FORMAT_ZI}} · {len(df)} tranzacții · ziua = data plății (autorizării)")

chelt = r.cheltuieli(df)
zile = (pana_la - de_la).days + 1
exceptionale = df[df[Col.TIP] == Tip.EXCEPTIONAL][Col.DEBIT].sum()
necunoscute = chelt[chelt[Col.CATEGORIE] == Cat.NECUNOSCUT]
venit = df[df[Col.TIP] == Tip.VENIT][Col.CREDIT].sum()

k = st.columns(4)
k[0].metric("Cheltuieli", r.lei(chelt[Col.SUMA].sum()),
            help="Toate plățile, inclusiv cele excepționale. Fără transferurile în conturile tale și încasări.")
k[1].metric("Medie pe zi (variabile)", r.lei(chelt[chelt[Col.TIP] == Tip.VARIABIL][Col.SUMA].sum() / zile),
            help="Fără costuri fixe și numerar.")
k[2].metric("Numerar retras", r.lei(chelt[chelt[Col.TIP] == Tip.NUMERAR][Col.SUMA].sum()))
k[3].metric("De identificat", r.lei(necunoscute[Col.SUMA].sum()),
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
        if Col.CATEGORIE in valori:
            salveaza(tabel.iloc[int(rand)][coloana_id], valori[Col.CATEGORIE])
            schimbat = True
    if schimbat:
        st.session_state.pop(cheie, None)
        st.rerun()


# --- Pe zile -----------------------------------------------------------------------

with tab_zile:
    z = r.pe_zile(df, de_la, pana_la)
    z["eticheta"] = z[Col.SUMA].map(lambda s: r.lei(s, 2))
    z["ziua"] = z[Col.DATA].dt.strftime(FORMAT_ZI)
    z["sapt"] = z["saptamana"].dt.strftime(FORMAT_ZI_SCURT)
    selectie = alt.selection_point(fields=["ziua"], name=Sesiune.SELECTIE_ZI)
    calendar = (
        alt.Chart(z)
        .mark_rect(cornerRadius=4, stroke="white", strokeWidth=2)
        .encode(
            x=alt.X("sapt:O", title="săptămâna care începe pe", sort=list(z["sapt"].unique()),
                    axis=alt.Axis(labelAngle=0, labelOverlap=True)),
            y=alt.Y("zi_sapt:O", title=None,
                    axis=alt.Axis(labelExpr=f"{ZILE_SCURT}[datum.value]", labelOverlap=False)),
            color=alt.Color(f"{Col.SUMA}:Q", title="lei / zi",
                            scale=alt.Scale(type="threshold", domain=PRAGURI, range=CULORI),
                            legend=None),
            opacity=alt.condition(selectie, alt.value(1), alt.value(0.35)),
            tooltip=[alt.Tooltip("ziua:N", title="Ziua"), alt.Tooltip("eticheta:N", title="Cheltuit"),
                     alt.Tooltip("plati:Q", title="Plăți")],
        )
        .add_params(selectie)
        .properties(height=alt.Step(30))
    )
    ev = st.altair_chart(calendar, use_container_width=True, on_select="rerun", key=Sesiune.CALENDAR)
    st.markdown(
        " &nbsp; ".join(f'<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
                        f'background:{c};vertical-align:middle"></span> {t}' for c, t in zip(CULORI, ETICHETE)),
        unsafe_allow_html=True,
    )
    st.caption("Apasă pe o zi. În calendar intră toate plățile: variabile, fixe, numerar și excepționale. "
               "Nu intră transferurile în conturile tale și încasările.")

    puncte = (ev or {}).get("selection", {}).get(Sesiune.SELECTIE_ZI) or []
    ales = puncte[0].get("ziua") if puncte else None
    zi_maxima = z.loc[z[Col.SUMA].idxmax(), Col.DATA].date() if z[Col.SUMA].any() else pana_la
    # un clic nou în calendar alege ziua; altfel rămâne cea din câmpul „Ziua”
    if ales and ales != st.session_state.get(Sesiune.CLIC_CALENDAR):
        st.session_state[Sesiune.ZIUA] = pd.to_datetime(ales, format=FORMAT_ZI).date()
    st.session_state[Sesiune.CLIC_CALENDAR] = ales
    ziua = st.session_state.get(Sesiune.ZIUA)
    if ziua is None or not de_la <= ziua <= pana_la:  # ziua aleasă înainte nu e în perioada nouă
        st.session_state[Sesiune.ZIUA] = zi_maxima
    zi = st.date_input("Ziua", key=Sesiune.ZIUA, min_value=de_la, max_value=pana_la, format=FORMAT_ZI_UI)

    in_zi = df[df[Col.DATA] == pd.Timestamp(zi)]
    din_zi = r.cheltuieli(in_zi)
    st.subheader(f"{ZILE[zi.weekday()]}, {zi:{FORMAT_ZI}}")
    if din_zi.empty:
        st.write("Nicio plată în ziua asta.")
    else:
        variabile = din_zi[din_zi[Col.TIP] == Tip.VARIABIL]
        altele = din_zi[din_zi[Col.TIP] != Tip.VARIABIL]
        text = f"**{r.lei(din_zi[Col.SUMA].sum(), 2)}** în {len(din_zi)} plăți"
        if not altele.empty and not variabile.empty:
            text += (f" · din care {r.lei(variabile[Col.SUMA].sum(), 2)} variabile și "
                     f"{r.lei(altele[Col.SUMA].sum(), 2)} fixe, numerar sau excepționale")
        st.write(text)
        for cheie, titlu, parte in [(Sesiune.EDITOR_ZI, "Cheltuieli variabile", variabile),
                                    (Sesiune.EDITOR_ZI_ALTELE, "Costuri fixe, numerar și excepționale", altele)]:
            if parte.empty:
                continue
            if not altele.empty and not variabile.empty:
                st.markdown(f"**{titlu}** · {r.lei(parte[Col.SUMA].sum(), 2)}")
            vizibile = [Col.COMERCIANT, Col.CATEGORIE, Col.SUMA, Col.VALUTA, Col.TIP_OPERATIUNE]
            tabel = parte[[Col.ID, *vizibile]].reset_index(drop=True)
            st.data_editor(
                tabel, key=cheie, hide_index=True, use_container_width=True,
                disabled=[c for c in vizibile if c != Col.CATEGORIE],
                column_order=vizibile,
                column_config={
                    Col.COMERCIANT: "Comerciant",
                    Col.CATEGORIE: st.column_config.SelectboxColumn("Categorie", options=OPTIUNI_CATEGORIE,
                                                                    required=True),
                    Col.SUMA: st.column_config.NumberColumn("Lei", format="%.2f"),
                    Col.VALUTA: "În valută",
                    Col.TIP_OPERATIUNE: "Operațiune",
                },
            )
            salveaza_editari(cheie, tabel, Col.ID, db.alege_pentru_tranzactie)
        st.caption("Schimbarea categoriei aici se aplică doar acestei plăți. "
                   "Pentru toate plățile la un comerciant, folosește tabul „Comercianți”.")

# --- Rapoarte ------------------------------------------------------------------------

with tab_rap:
    st.subheader("Pe categorii")
    pc = r.pe_categorii(df)
    pc["eticheta"] = pc[Col.SUMA].map(r.lei)
    bare = alt.Chart(pc).encode(
        y=alt.Y(f"{Col.CATEGORIE}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
        x=alt.X(f"{Col.SUMA}:Q", title=None, axis=alt.Axis(grid=False, labels=False, ticks=False, domain=False)),
        tooltip=[alt.Tooltip(f"{Col.CATEGORIE}:N", title="Categorie"), alt.Tooltip("eticheta:N", title="Total"),
                 alt.Tooltip("procent:Q", title="% din total"), alt.Tooltip("plati:Q", title="Plăți")],
    )
    st.altair_chart(
        bare.mark_bar(color=CULOARE_BARE, cornerRadiusEnd=4, height=14)
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
            Col.COMERCIANT: "Comerciant", Col.CATEGORIE: "Categorie", "plati": "Plăți",
            Col.SUMA: st.column_config.NumberColumn("Total (lei)", format="%.0f"),
        })
    with c2:
        st.subheader("Costuri fixe și abonamente")
        cf = r.costuri_fixe(df)
        st.dataframe(cf, hide_index=True, use_container_width=True, column_config={
            "ce": "Ce", Col.CATEGORIE: "Categorie",
            "ultima_plata": st.column_config.DateColumn("Ultima plată", format=FORMAT_ZI_UI),
            "ultima_suma": st.column_config.NumberColumn("Ultima sumă", format="%.2f"),
            "pe_luna": st.column_config.NumberColumn("≈ pe lună", format="%.0f"),
        })
        st.caption(f"Total ≈ {r.lei(cf['pe_luna'].sum())} pe lună (media pe perioada aleasă).")

    with st.expander("Toate tranzacțiile din perioadă"):
        export = df.drop(columns=[Col.DETALII, Col.ID, Col.SURSA]).sort_values(Col.DATA, ascending=False)
        st.dataframe(export, hide_index=True, use_container_width=True)
        st.download_button("Descarcă CSV", export.to_csv(index=False).encode("utf-8-sig"),
                           f"cheltuieli_{de_la}_{pana_la}.csv", "text/csv")

# --- Comercianți ---------------------------------------------------------------------

with tab_com:
    st.write(
        "Alege categoria o singură dată pentru fiecare comerciant; se aplică automat și la importurile viitoare. "
        f"Cei „{Cat.NECUNOSCUT}” sunt primii în listă."
    )
    cautare = st.text_input("Caută comerciant", placeholder="ex. mega image, emag, marina",
                            help="Caută în tot istoricul, după o parte din nume. Literele mari, spațiile "
                                 "și diacriticele nu contează.").strip()
    doar_necunoscuti = st.toggle("Doar cei de identificat", value=not necunoscute.empty, disabled=bool(cautare))
    com = r.comercianti(toate)  # pe tot istoricul, nu doar în perioada aleasă
    if cautare:
        com = com[com[Col.COMERCIANT].map(lambda c: r.potriveste(c, cautare))]
    elif doar_necunoscuti:
        com = com[com["de_identificat"]]
    oras = toate.set_index(Col.COMERCIANT)[Col.DETALII].map(
        lambda d: parser_ing.localitate(d.get(Ing.TRANZACTIE_LA, "")))
    oras = oras[~oras.index.duplicated()]
    com = com.assign(cauta=[
        "https://www.google.com/search?q=" + quote_plus(f"{c} {oras.get(c, '')}") for c in com[Col.COMERCIANT]
    ]).reset_index(drop=True)
    cheie_editor = f"{Sesiune.EDITOR_COMERCIANTI}{cautare}"  # altă căutare, alt tabel: modificările nu se amestecă
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
            column_order=[Col.COMERCIANT, Col.CATEGORIE, "plati", "medie", "total", "ultima", "sursa", "cauta"],
            disabled=[Col.COMERCIANT, "plati", "medie", "total", "ultima", "sursa", "cauta"],
            column_config={
                Col.COMERCIANT: "Comerciant (cum apare în extras)",
                Col.CATEGORIE: st.column_config.SelectboxColumn("Categorie", options=OPTIUNI_CATEGORIE,
                                                                required=True),
                "plati": "Plăți",
                "medie": st.column_config.NumberColumn("Medie", format="%.2f"),
                "total": st.column_config.NumberColumn("Total", format="%.2f"),
                "ultima": st.column_config.DateColumn("Ultima dată", format=FORMAT_ZI_UI),
                "sursa": st.column_config.TextColumn("Stabilită", help="automat = după reguli; comerciant = aleasă de tine"),
                "cauta": st.column_config.LinkColumn("Caută online", display_text="caută"),
            },
        )
        salveaza_editari(cheie_editor, com, Col.COMERCIANT, db.alege_pentru_comerciant)

        if cautare:
            st.subheader("Plățile găsite")
            plati = r.cheltuieli(toate)
            plati = plati[plati[Col.COMERCIANT].isin(com[Col.COMERCIANT])].sort_values(Col.DATA, ascending=False)
            st.dataframe(
                plati[[Col.DATA, Col.COMERCIANT, Col.CATEGORIE, Col.SUMA, Col.VALUTA]], hide_index=True,
                use_container_width=True,
                column_config={
                    Col.DATA: st.column_config.DateColumn("Ziua", format=FORMAT_ZI_UI),
                    Col.COMERCIANT: "Comerciant", Col.CATEGORIE: "Categorie",
                    Col.SUMA: st.column_config.NumberColumn("Lei", format="%.2f"), Col.VALUTA: "În valută",
                },
            )
            pe_luna = plati.groupby(plati[Col.DATA].dt.to_period("M"))[Col.SUMA].sum()
            st.caption("Pe luni: " + " · ".join(f"{r.nume_luna(p)} {r.lei(v)}" for p, v in pe_luna.items()))

# --- Bugete --------------------------------------------------------------------------

with tab_buget:
    st.write("Opțional: pune o limită lunară pe categoriile pe care vrei să le ții sub control. "
             "Lasă gol unde nu vrei buget.")
    bugete = db.bugete()
    cat_buget = [c for c, t in categorii.CATEGORII.items() if t in TIPURI_CU_BUGET and c != Cat.NECUNOSCUT]
    luna_curenta = pd.Timestamp(ultima).to_period("M")
    istoric = r.cheltuieli(toate).assign(luna=lambda x: x[Col.DATA].dt.to_period("M"))
    # doar lunile încheiate și acoperite complet de extrase
    prima_luna = pd.Timestamp(prima).to_period("M") + (0 if prima.day == 1 else 1)
    istoric = istoric[(istoric["luna"] < luna_curenta) & (istoric["luna"] >= prima_luna)]
    media = istoric.groupby([Col.CATEGORIE, "luna"])[Col.SUMA].sum().groupby(Col.CATEGORIE).mean()
    tabel_b = pd.DataFrame({
        Col.CATEGORIE: cat_buget,
        "media": [round(float(media.get(c, 0))) for c in cat_buget],
        "buget": [bugete.get(c, float("nan")) for c in cat_buget],
    })
    rez = st.data_editor(
        tabel_b, key=Sesiune.EDITOR_BUGET, hide_index=True, use_container_width=True,
        disabled=[Col.CATEGORIE, "media"],
        column_config={
            Col.CATEGORIE: "Categorie",
            "media": st.column_config.NumberColumn("Media lunară până acum", format="%d lei",
                                                   help="Media lunilor încheiate din istoric."),
            "buget": st.column_config.NumberColumn("Buget lunar (lei)", min_value=0, step=50),
        },
    )
    if st.button("Salvează bugetele"):
        for _, rand in rez.iterrows():
            db.seteaza_buget(rand[Col.CATEGORIE], None if pd.isna(rand["buget"]) else float(rand["buget"]))
        st.rerun()

    if bugete:
        luni = sorted(toate[Col.DATA].dt.to_period("M").unique(), reverse=True)
        luna = st.selectbox("Luna", luni, format_func=r.nume_luna)
        for _, b in r.buget(toate, bugete, luna).iterrows():
            depasit = b["cheltuit"] > b["buget"]
            text = (f"**{b[Col.CATEGORIE]}**: {r.lei(b['cheltuit'])} din {r.lei(b['buget'])}"
                    + (f" · ⚠️ depășit cu {r.lei(-b['ramas'])}" if depasit else f" · rămân {r.lei(b['ramas'])}"))
            st.progress(min(b["procent"] / 100, 1.0), text=text)
