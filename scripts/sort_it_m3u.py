import re
import sys
from pathlib import Path

OUTFILE = Path("streams/it.m3u")

# Ordine stile “telecomando”
# (aggiungi qui se vuoi altri canali in alto)
PINNED_ORDER = [
    "Rai 1",
    "Rai 2",
    "Rai 3",
    "Rete 4",
    "Canale 5",
    "Italia 1",
    "La7",
    "TV8",
    "Nove",
    "Rai News 24",
    "TGCom 24",
    "Sky TG24",
]

def norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())

def normalize_base_name(display_name: str) -> str:
    """
    Prende il nome dopo la virgola di #EXTINF e lo riduce al 'nome base' del canale.
    Esempi:
      "Rai 1 (576p) [Geo-blocked]" -> "Rai 1"
      "Rai 1 HD (720p)"           -> "Rai 1"
      "LA7 HD"                    -> "La7"
      "TGCom 24 [Geo-blocked]"    -> "TGCom 24"
      "27 TwentySeven ..."        -> "27 TwentySeven" (non toccato)
    """
    s = display_name

    # Rimuove tag [ ... ]
    s = re.sub(r"\[[^\]]*\]", "", s)

    # Rimuove parentesi ( ... )
    s = re.sub(r"\([^)]*\)", "", s)

    # Normalizza spazi
    s = norm_spaces(s)

    # Uniforma alcuni nomi (case e varianti comuni)
    # LA7 / La7
    if s.upper().startswith("LA7"):
        s = "La7" + s[3:]
        s = norm_spaces(s)

    # NOVE / Nove
    if s.upper().startswith("NOVE"):
        s = "Nove" + s[4:]
        s = norm_spaces(s)

    # TGCom 24 varianti
    if s.lower().startswith("tgcom"):
        s = "TGCom 24" if "24" in s else "TGCom"
        # se era "TGCom 24" ok

    # RaiNews24 varianti
    if s.lower().replace(" ", "") in ("rainews24", "rainews"):
        s = "Rai News 24"

    # Rimuove suffissi tipo HD/UHD/4K/SD (solo se in fondo o come token)
    s = re.sub(r"\b(HD|UHD|4K|SD)\b", "", s, flags=re.IGNORECASE)
    s = norm_spaces(s)

    # Uniforma "Rai Uno/Due/Tre" se mai presenti
    s = re.sub(r"^Rai Uno$", "Rai 1", s, flags=re.IGNORECASE)
    s = re.sub(r"^Rai Due$", "Rai 2", s, flags=re.IGNORECASE)
    s = re.sub(r"^Rai Tre$", "Rai 3", s, flags=re.IGNORECASE)

    return s

def parse_m3u(lines):
    header = []
    entries = []

    i = 0
    while i < len(lines) and not lines[i].startswith("#EXTINF"):
        if lines[i].strip():
            header.append(lines[i])
        i += 1

    while i < len(lines):
        if not lines[i].startswith("#EXTINF"):
            i += 1
            continue
        extinf = lines[i]
        url = lines[i + 1] if i + 1 < len(lines) else ""
        name = extinf.split(",", 1)[1].strip() if "," in extinf else ""
        base = normalize_base_name(name)

        # punteggio pinned
        try:
            pinned_idx = PINNED_ORDER.index(base)
        except ValueError:
            pinned_idx = 9999

        # secondario: alfabetico sul base name
        entries.append((pinned_idx, base.lower(), name.lower(), extinf, url))
        i += 2

    if not header:
        header = ["#EXTM3U"]
    return header, entries

def main():
    raw = sys.stdin.read()
    lines = raw.splitlines()

    header, entries = parse_m3u(lines)

    # Ordine:
    # 1) pin
    # 2) base name
    # 3) nome completo (così varianti dello stesso canale stanno insieme)
    entries.sort(key=lambda x: (x[0], x[1], x[2]))

    out = []
    out.extend(header)
    for _, _, _, extinf, url in entries:
        out.append(extinf)
        out.append(url)

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    OUTFILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Written: {OUTFILE}")

if __name__ == "__main__":
    main()
