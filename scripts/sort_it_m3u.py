import re
import sys
from pathlib import Path

OUTFILE = Path("streams/it.m3u")

# Ordine stile “telecomando” (LCN approssimativo)
PINNED_ORDER = {
    "Rai 1": 1, "Rai 2": 2, "Rai 3": 3, "Rai Yoyo": 4, "Rai Gulp": 5, "Rai Storia": 6,
    "Rete 4": 7, "Canale 5": 8, "Italia 1": 9, "La7": 10, "TV8": 18, "Nove": 19,
    "Rai News 24": 25, "TGCom 24": 50, "Sky TG24": 51,
    # Aggiungi altri con LCN basso per top
}

def norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())

def normalize_base_name(display_name: str) -> str:
    s = display_name

    # Rimuovi tag [ ] e ( )
    s = re.sub(r"\[.*?\]|\(.*?\)", "", s)
    s = norm_spaces(s)

    # Uniforma varianti comuni
    s = re.sub(r"^(LA7)", "La7", s, flags=re.I)
    s = re.sub(r"^(NOVE)", "Nove", s, flags=re.I)
    if re.match(r"^tgcom.*24", s, re.I): s = "TGCom 24"
    elif re.match(r"^tgcom", s, re.I): s = "TGCom"
    if re.search(r"rai\s*(news|news24)", s, re.I): s = "Rai News 24"
    s = re.sub(r"\b(HD|UHD|4K|SD)\b", "", s, flags=re.I)
    s = norm_spaces(s)
    s = re.sub(r"rai\s+(uno|1)", "Rai 1", s, flags=re.I)
    s = re.sub(r"rai\s+(due|2)", "Rai 2", s, flags=re.I)
    s = re.sub(r"rai\s+(tre|3)", "Rai 3", s, flags=re.I)

    return s

def get_lcn_priority(base: str) -> int:
    """Priorità LCN da PINNED_ORDER, altrimenti alfabetico"""
    return PINNED_ORDER.get(base, 9999 + ord(base[0].lower()) if base else 99999)

def parse_m3u(lines):
    header = []
    entries = []

    i = 0
    while i < len(lines) and not lines[i].startswith("#EXTINF:"):
        if lines[i].strip(): header.append(lines[i])
        i += 1

    while i < len(lines):
        if i + 1 >= len(lines) or not lines[i].startswith("#EXTINF:"):
            i += 1
            continue
        extinf = lines[i]
        url = lines[i + 1]
        name_match = re.split(r",(?=[^,]*$)", extinf, 1)
        name = name_match[1].strip() if len(name_match) > 1 else ""
        base = normalize_base_name(name)

        lcn_prio = get_lcn_priority(base)
        # Per Emby: aggiungi tvg-logo placeholder se assente, group LCN
        if "tvg-logo=" not in extinf:
            extinf += " tvg-logo=\"https://i.imgur.com/placeholder.png\""
        extinf = re.sub(r"tvg-group=", r' group-title="Italia LCN ' + str(lcn_prio) + r'", tvg-group=', extinf)

        entries.append((lcn_prio, base.lower(), name.lower(), extinf, url.strip()))
        i += 2

    if not header or "#EXTM3U" not in header[0]:
        header = ["#EXTM3U"]
    return header, entries

def main():
    raw = sys.stdin.read()
    lines = raw.splitlines()

    header, entries = parse_m3u(lines)
    entries.sort(key=lambda x: (x[0], x[1], x[2]))  # LCN > base > nome

    out = header[:]
    for _, _, _, extinf, url in entries:
        out.append(extinf)
        if url.strip(): out.append(url)

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    OUTFILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Written {len(entries)} entries: {OUTFILE}")

if __name__ == "__main__":
    main()
