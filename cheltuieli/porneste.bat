@echo off
cd /d "%~dp0"
if not exist .venv\gata.txt (
    echo Prima pornire: instalez aplicatia, dureaza un minut...
    python -m venv .venv || (echo Nu gasesc Python. Instaleaza-l de pe python.org. & pause & exit /b 1)
    .venv\Scripts\python -m pip install -r requirements.txt || (echo Instalarea a esuat. & pause & exit /b 1)
    echo ok> .venv\gata.txt
)
.venv\Scripts\python -m streamlit run app.py
pause
