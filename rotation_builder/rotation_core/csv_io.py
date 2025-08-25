from __future__ import annotations
import io
import hashlib
from typing import List, Dict, Tuple, Iterable
import pandas as pd
from .constants import CSV_HEADERS, HEADER_ALIASES, normalize_name, normalize_pos
from .models import Player

def _header_map(cols: Iterable[str]) -> Dict[str, str]:
    """
    Build a mapping from provided column -> canonical header.
    Case-insensitive, uses HEADER_ALIASES, leaves unknown columns untouched.
    """
    canon = {c.lower(): c for c in CSV_HEADERS}
    out = {}
    for c in cols:
        lc = c.strip().lower()
        if lc in canon:
            out[c] = canon[lc]
            continue
        mapped = None
        for k, aliases in HEADER_ALIASES.items():
            if lc == k.lower() or lc in aliases:
                mapped = k
                break
        out[c] = mapped if mapped else c
    return out

def _row_to_player(row: Dict, id_counts: Dict[str, int]) -> Player:
    name = normalize_name(str(row.get("Name", "") or ""))
    # derive deterministic short id by name hash; avoid collisions with suffix counter
    base = hashlib.md5(name.lower().encode()).hexdigest()[:8] if name else hashlib.md5(str(row).encode()).hexdigest()[:8]
    n = id_counts.get(base, 0)
    id_counts[base] = n + 1
    pid = f"{base}" if n == 0 else f"{base}-{n}"

    def g(k): 
        return normalize_pos(str(row.get(k, "") or ""))

    return Player(
        id=pid, Name=name,
        Off1=g("Off1"), Off2=g("Off2"), Off3=g("Off3"), Off4=g("Off4"),
        Def1=g("Def1"), Def2=g("Def2"), Def3=g("Def3"), Def4=g("Def4"),
    )

def parse_roster_csv(file) -> List[Player]:
    """
    Parse uploaded CSV (bytes or file-like).
    Applies header aliasing and returns a list[Player].
    """
    if isinstance(file, (bytes, bytearray)):
        buf = io.BytesIO(file)
        df = pd.read_csv(buf)
    else:
        df = pd.read_csv(file)

    # normalize columns
    hmap = _header_map(df.columns)
    df = df.rename(columns=hmap)

    # ensure required columns exist
    for k in CSV_HEADERS:
        if k not in df.columns:
            df[k] = ""

    # filter only needed
    df = df[CSV_HEADERS].copy()

    id_counts: Dict[str, int] = {}
    players: List[Player] = []
    for _, r in df.iterrows():
        if str(r.get("Name", "")).strip() == "":
            continue
        p = _row_to_player(r.to_dict(), id_counts)
        players.append(p)
    return players

def build_template_csv() -> bytes:
    example = (
        "Name,Off1,Off2,Off3,Off4,Def1,Def2,Def3,Def4\n"
        "Alex Quinn,QB,WR,Slot,TE,RC,S,LC,RLB\n"
    )
    return example.encode("utf-8")

def roster_to_dataframe(players: List[Player]) -> pd.DataFrame:
    rows = []
    for p in players:
        rows.append({
            "id": p.id,
            "Name": p.Name,
            "Off1": p.Off1, "Off2": p.Off2, "Off3": p.Off3, "Off4": p.Off4,
            "Def1": p.Def1, "Def2": p.Def2, "Def3": p.Def3, "Def4": p.Def4,
            "RoleToday": p.RoleToday, "EnergyToday": p.EnergyToday,
        })
    df = pd.DataFrame(rows)
    return df

def dataframe_to_roster(df: pd.DataFrame) -> List[Player]:
    players: List[Player] = []
    for _, r in df.iterrows():
        if str(r.get("Name","")).strip() == "":
            continue
        players.append(Player(
            id=str(r.get("id", "")) or hashlib.md5(str(r).encode()).hexdigest()[:8],
            Name=normalize_name(str(r.get("Name",""))),
            Off1=normalize_pos(str(r.get("Off1",""))),
            Off2=normalize_pos(str(r.get("Off2",""))),
            Off3=normalize_pos(str(r.get("Off3",""))),
            Off4=normalize_pos(str(r.get("Off4",""))),
            Def1=normalize_pos(str(r.get("Def1",""))),
            Def2=normalize_pos(str(r.get("Def2",""))),
            Def3=normalize_pos(str(r.get("Def3",""))),
            Def4=normalize_pos(str(r.get("Def4",""))),
            RoleToday=str(r.get("RoleToday","Connector")),
            EnergyToday=str(r.get("EnergyToday","Medium")),
        ))
    return players
