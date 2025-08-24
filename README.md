# README.md
# Youth Football Rotation Generator (Streamlit)

A coach-first web app that enforces fair, balanced playing time while still optimizing for the strongest feasible lineups.

## Features
- **Fairness first** (minimum guarantee, evenness cap ±1)
- **Win strength second** (maximize lineup StrengthIndex)
- **Balance third** (pair strong/weak with position preference weights)
- **Coach picks Series 1 starters**, solver smart-fills blanks
- Varsity minutes reduce target slots slightly
- Inline roster editing; CSV import/export
- Configurable formations via `assets/formations.yaml`
- ILP solver (PuLP) with **heuristic fallback**
- Rotation Board, Fairness Dashboard, and CSV/PDF export

## Install & Run
```bash
python -m venv .venv
# Windows:
. .venv/Scripts/Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
