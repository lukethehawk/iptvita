import re
import sys
from pathlib import Path

UPSTREAM_URL = "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/it.m3u"

OUTFILE = Path("streams/it.m3u")  # nel tuo repo

# Ordine preferito (modificalo come vuoi)
# Metti qui le etichette come appaiono in #EXTINF dopo la virgola.
PREFERRED = [
    "Rai 1", "Rai Uno",
    "Rai 2", "Rai Due",
    "Rai 3", "Rai Tre",
    "Rete 4",
    "Canale 5",
    "Italia 1",
    "La7",
    "TV8",
    "Nove", "NOVE",
    "Rai News 24", "RaiNews24",
    "TGCOM24", "Tgcom24",
    "Sky TG24", "SkyTG24",
]

def norm(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

preferred_map = {norm(n): i for i, n in enumerate(PREFERRED)}

def parse_m3u(lines):
    header = []
    entries = []

    i = 0
    # header fino al primo EXTINF
    while i < len(lines) and not lines[i].startswith("#EXTINF"):
        if lines[i].strip():
            header.append(lines[i])
        i += 1

    # entries (EXTINF + url)
    while i < len(lines):
        if not lines[i].startswith("#EXTINF"):
            i += 1
            continue
        extinf = lines[i]
        url = lines[i+1] if i + 1 < len(lines) else ""
        name = extinf.split(",", 1)[1].strip() if "," in extinf else ""
        key = norm(name)
        prio = preferred_map.get(key, 9999)
        entries.append((prio, norm(name), extinf, url))
        i += 2

    if not header:
        header = ["#EXTM3U"]
    return header, entries

def sort_entries(entries):
    # prima i preferiti, poi alfabetico
    entries.sort(key=lambda x: (x[0], x[1]))
    return entries

def main():
    # legge da stdin (così la Action può fare curl | python)
    raw = sys.stdin.read()
    lines = raw.splitlines()

    header, entries = parse_m3u(lines)
    entries = sort_entries(entries)

    out = []
    out.extend(header)
    for _, _, extinf, url in entries:
        out.append(extinf)
        out.append(url)

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    OUTFILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Written: {OUTFILE}")

if __name__ == "__main__":
    main()
