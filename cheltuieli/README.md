# Cheltuieli zilnice

Aplicație locală care citește extrasele CSV din ING Home'Bank și îți arată pe ce
s-au dus banii, zi cu zi. Rulează doar pe PC-ul tău; datele nu pleacă nicăieri.

## Pornire (Windows)

1. Descarcă proiectul (sau `git clone`) într-un folder, de exemplu `C:\cheltuieli`.
2. Dublu-clic pe **`porneste.bat`**. Prima dată instalează ce îi trebuie (un minut),
   apoi se deschide aplicația în browser, la http://localhost:8501.
3. Închizi aplicația închizând fereastra neagră.

Manual, din PowerShell:

```powershell
cd C:\cheltuieli\cheltuieli
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Cum o folosești

1. Din ING Home'Bank exporți lista de tranzacții în format CSV (fișierul
   `Tranzactii_<data>.csv`), pentru perioada dorită.
2. În aplicație, bara din stânga: **Upload** și alegi fișierul. Sau deschizi
   „Import din folderul de descărcări” și apeși butonul: ia toate fișierele
   `Tranzactii_*.csv` din folderul de descărcări.
   Poți importa de câte ori vrei perioade care se suprapun: tranzacțiile deja
   existente nu se dublează.
3. Tabul **Comercianți**: alegi o dată categoria pentru cei „De identificat”.
   Linkul „caută” deschide o căutare Google cu numele și orașul din extras.
   Alegerea se aplică și la importurile viitoare.

### Ecrane

- **Pe zile**: calendar colorat după cât ai cheltuit în fiecare zi. Apeși pe o zi
  și vezi plățile. Poți schimba categoria unei singure plăți (de ex. o comandă
  eMAG care a fost de fapt un cadou).
- **Rapoarte**: pe categorii, pe luni, top comercianți, costuri fixe și abonamente,
  plus exportul tuturor tranzacțiilor din perioadă.
- **Comercianți**: lista tuturor comercianților și categoria lor.
- **Bugete** (opțional): o limită lunară pe categorie, cu media ta de până acum
  ca reper.

### Ce intră în „Cheltuieli”

| Tip | Exemple | În total și în calendar? | În media pe zi? |
|---|---|---|---|
| variabil | alimente, restaurante, transport | da | da |
| fix | rate, utilități, abonamente | da | nu |
| numerar | retrageri ATM | da | nu |
| excepțional | rambursare anticipată, alte sume mari unice | da (și afișat separat) | nu |
| intern | transferuri în conturile tale | nu | nu |
| venit | încasări | nu (afișat separat) | nu |

Totalul de sus, calendarul și rapoartele numără aceleași plăți, deci sumele se leagă.

Ziua unei plăți este **data autorizării** (când ai plătit), nu data decontării,
care poate fi cu 1–3 zile mai târziu.

Orice plată poate fi mutată în categoria „Excepționale” ca să nu strice media pe zi
(de ex. o reparație mare la mașină).

## Date și confidențialitate

- Baza de date este `date/cheltuieli.db` (SQLite), lângă aplicație. Pentru
  backup, copiezi fișierul ăsta.
- Din antetul extrasului se păstrează doar numele titularului (ca să recunoască
  transferurile în conturile proprii). CNP-ul și adresa nu se salvează.
- Folderul `date/` și fișierele `.csv` sunt excluse din git.

## Structura codului

| Fișier | Ce face |
|---|---|
| `app.py` | interfața (Streamlit) |
| `parser_ing.py` | citește formatul CSV ING (o tranzacție pe mai multe rânduri) |
| `categorii.py` | lista de categorii și regulile automate după numele comerciantului |
| `stocare.py` | baza de date SQLite și alegerile tale de categorii |
| `rapoarte.py` | calculele pentru rapoarte |

Regulile automate sunt în `categorii.py` (`REGULI`): o expresie regulată pe
numele comerciantului și categoria. Categoriile noi se adaugă în `CATEGORII`.

Teste: `pip install -r requirements-dev.txt`, apoi `pytest`.
