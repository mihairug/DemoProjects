"""Valorile cu înțeles în cod, folosite în mai multe fișiere.

Textele afișate pe ecran (titluri, etichete, mesaje) nu sunt aici: stau lângă
locul unde apar. Aici sunt doar valorile după care codul decide ceva sau care
trebuie să fie identice în mai multe locuri: un nume greșit aici ar strica
potriviri, filtre sau date salvate.
"""

from __future__ import annotations

LUNI = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august",
        "septembrie", "octombrie", "noiembrie", "decembrie"]
ZILE = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]
ZILE_SCURT = ["L", "Ma", "Mi", "J", "V", "S", "D"]


class Tip:
    """Tipul unei categorii, folosit de rapoarte."""
    VARIABIL = "variabil"         # cheltuieli de zi cu zi
    FIX = "fix"                   # rate, utilități, abonamente
    NUMERAR = "numerar"           # retrageri de la ATM (nu știm pe ce s-au dus)
    EXCEPTIONAL = "exceptional"   # sume mari, o singură dată (ex. rambursare anticipată)
    INTERN = "intern"             # mutări între conturile tale; nu sunt cheltuieli
    VENIT = "venit"               # încasări


# ce intră în totaluri, calendar și rapoarte
TIPURI_CHELTUIELI = (Tip.VARIABIL, Tip.FIX, Tip.NUMERAR, Tip.EXCEPTIONAL)
# ce poate avea buget
TIPURI_CU_BUGET = (Tip.VARIABIL, Tip.FIX, Tip.EXCEPTIONAL)


class Cat:
    """Numele categoriilor. Sunt salvate în baza de date (alegerile tale și bugetele),
    deci o redenumire aici face ca alegerile vechi pe numele vechi să devină „De identificat”."""
    ALIMENTE = "Alimente"
    RESTAURANTE = "Restaurante & baruri"
    CAFEA = "Cafea & gustări"
    TRANSPORT = "Transport"
    MASINA = "Mașină"
    PARCARE = "Parcare"
    ANIMALE = "Animale"
    SANATATE = "Sănătate"
    ONLINE = "Cumpărături online"
    HAINE_SPORT = "Haine & sport"
    COPII = "Copii & distracție"
    CASA = "Casă & electronice"
    FITNESS = "Fitness"
    VACANTE = "Vacanțe & timp liber"
    SERVICII = "Servicii"
    CADOURI = "Cadouri & flori"
    DONATII = "Donații"
    TUTUN = "Tutun"
    CATRE_PERSOANE = "Transferuri către persoane"
    ALTELE = "Altele"
    NECUNOSCUT = "De identificat"
    UTILITATI = "Utilități & telecom"
    ABONAMENTE = "Abonamente digitale"
    CREDIT = "Credit & asigurare"
    NUMERAR = "Numerar (ATM)"
    EXCEPTIONALE = "Excepționale"
    CONT_PROPRIU = "Transfer în cont propriu"
    INCASARI = "Încasări"


class Sursa:
    """De unde vine categoria unei tranzacții."""
    AUTOMAT = "automat"          # regulile din categorii.py
    COMERCIANT = "comerciant"    # aleasă de tine pentru comerciant
    TRANZACTIE = "tranzactie"    # aleasă de tine pentru o singură plată


class Col:
    """Coloanele tabelului de tranzacții întors de stocare.Baza.tranzactii()."""
    ID = "id"
    DATA = "data"
    DATA_DECONTARE = "data_decontare"
    TIP_OPERATIUNE = "tip_operatiune"
    DEBIT = "debit"
    CREDIT = "credit"
    SOLD = "sold"
    COMERCIANT = "comerciant"
    DETALII = "detalii"
    VALUTA = "valuta"
    CATEGORIE = "categorie"
    SURSA = "sursa_categorie"
    TIP = "tip"
    SUMA = "suma"                # adăugată de rapoarte.cheltuieli(): debit - credit


class Ing:
    """Textele din exportul CSV ING Home'Bank după care îl citim."""
    TITULAR = "Titular cont:"
    ANTET = "Data"               # prima celulă a rândului de antet
    COL_DETALII = "Detalii tranzactie"
    COL_DEBIT = "Debit"
    COL_CREDIT = "Credit"
    COL_SOLD = "Balanta"
    # cheile rândurilor de detalii „Cheie:valoare”
    TRANZACTIE_LA = "Tranzactie la"
    DATA_AUTORIZARII = "Data autorizarii"
    NUMAR_AUTORIZARE = "Numar autorizare"
    REFERINTA = "Referinta"
    BENEFICIAR = "Beneficiar"
    ORDONATOR = "Ordonator"
    SUMA_VALUTA = "Suma"
    # începutul tipului de operațiune (litere mici)
    OP_RETRAGERE = "retragere"
    OP_RECALCULARI = "recalculari"
    OP_ANULARE_RNPM = "anulare a inregistrarii"
    OP_CREDIT = "credit"
    OP_ASIGURARE = "asigurare"
    OP_TRANSFER = "transfer"
    FISIERE = "Tranzactii_*.csv"


class Setare:
    """Cheile din tabelul `setari`."""
    TITULAR = "titular"
    FOLDER_DESCARCARI = "folder_descarcari"


class Sesiune:
    """Cheile din st.session_state și cheile widget-urilor Streamlit."""
    PROCESATE = "procesate"
    ZIUA = "ziua"
    CLIC_CALENDAR = "clic_calendar"
    MESAJ_STERGERE = "mesaj_stergere"
    CALENDAR = "calendar"
    SELECTIE_ZI = "zi"
    EDITOR_ZI = "editor_zi"
    EDITOR_ZI_ALTELE = "editor_zi_altele"
    EDITOR_COMERCIANTI = "editor_com_"   # + textul căutat
    EDITOR_BUGET = "editor_buget"


# formate de dată: pentru strftime și pentru widget-urile Streamlit
FORMAT_ZI = "%d.%m.%Y"
FORMAT_ZI_SCURT = "%d.%m"
FORMAT_ZI_UI = "DD.MM.YYYY"

# calendar: zi fără plăți, sub 100, 100–300, 300–1000, peste 1000 lei
PRAGURI = [0.01, 100, 300, 1000]
CULORI = ["#e1e0d9", "#a8c97f", "#f4a960", "#de5b4f", "#b9a2c8"]
ETICHETE = ["0", "sub 100", "100–300", "300–1000", "peste 1000 lei"]
CULOARE_BARE = "#2a78d6"
CULOARE_TEXT_INCHIS = "#f0efec"   # pe tema închisă
CULOARE_TEXT_DESCHIS = "#31333f"  # pe tema deschisă
