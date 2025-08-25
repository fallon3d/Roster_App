# Youth Football Rotation Builder — Coach UI (Streamlit)

A full Python 3.11+ / Streamlit rebuild of the single-file HTML/JS app. This repository preserves the original flow and logic while introducing a robust, testable architecture:

- **4 Stages + Game**:
  1) Import roster (CSV) & live edit  
  2) Choose segment (Offense / Defense) + Defense formation (5–3 / 4–4)  
  3) Set Role & Energy  
  4) 1st Lineup editor (Series 1), lock

  **Game Mode**: Start Game, Current/Next series with “Change” picker, category-fairness hints, End Series, End Game, Review, Export played rotations CSV, real-time stats.

- **Core architecture**: `rotation_core` package (constants/models/engine/game), Streamlit UI in `app.py`, and tests in `tests/`.

---

## Install & Run

```bash
# from the repo root (rotation_builder/)
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
