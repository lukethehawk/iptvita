import re
import sys
import urllib.request
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

SRC_M3U = "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/it.m3u"
REF_M3U = "https://raw.githubusercontent.com/maginetweb-arch/TVITALIA/refs/heads/main/iptvit.m3u"

# LCN "classica" nazionale (puoi ampliarli quando vuoi)
LCN_OVERRIDES = {
    "rai 1": 1,
    "rai 2": 2,
    "rai 3": 3,
    "rete 4": 4,
    "canale 5": 5,
    "italia 1": 6,
    "la7": 7,
    "tv8": 8,
    "nove": 9,
    "20 mediaset": 20,
    "rai 4": 21,
    "iris": 22,
    "rai 5": 23,
    "rai movie": 24,
    "rai premium": 25,
    "cielo": 26,
    "twentyseven": 27,
    "tv2000": 28,
    "la7d": 29,
    "la5": 30,
    "real time": 31,
    "dmax": 52,
    "rai yoyo": 43,
    "rai gulp": 42,
    "rai news 24": 48,
    "rai storia": 54,
    "rai scuola": 57,
    "sportitalia": 60,
    "tgcom 24": 51,
    "top crime": 39,
    "cine 34": 34,
}

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def norm_name(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("’", "'")
    return s

@dataclass
class Entry:
    extinf: str
    url: str
    name: str
    tvg_id: str = ""
    tvg_logo: str = ""
    tvg_chno: str = ""
    group: str = ""

def parse_extinf(line: str) -> Dict[str, str]:
    # Estrae attributi tipo tvg-id="", tvg-logo="", tvg-chno="", group-title=""
    attrs = {}
    for k in ["tvg-id", "tvg-logo", "tvg-chno", "group-title"]:
        m = re.search(rf'{k}="([^"]*)"', line)
        if m:
            attrs[k] = m.group(1).strip()
    return attrs

def parse_m3u(text: str) -> List[Entry]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() != ""]
    out: List[Entry] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("#EXTINF:"):
            extinf = ln
            url = ""
            if i + 1 < len(lines) and not lines[i+1].startswith("#"):
                url = lines[i+1].strip()
                i += 1
            # Nome dopo l'ultima virgola
            name = extinf.split(",")[-1].strip()
            attrs = parse_extinf(extinf)
            out.append(Entry(
                extinf=extinf,
                url=url,
                name=name,
                tvg_id=attrs.get("tvg-id", ""),
                tvg_logo=attrs.get("tvg-logo", ""),
                tvg_chno=attrs.get("tvg-chno", ""),
                group=attrs.get("group-title", ""),
            ))
        i += 1
    return out

def set_attr(extinf: str, key: str, value: str) -> str:
    if value is None:
        return extinf
    if re.search(rf'{key}="[^"]*"', extinf):
        return re.sub(rf'{key}="[^"]*"', f'{key}="{value}"', extinf)
    # inserisce dopo #EXTINF:-1
    return extinf.replace("#EXTINF:-1", f'#EXTINF:-1 {key}="{value}"', 1)

def quality_score(url: str) -> int:
    # euristica: preferisci https, preferisci m3u8, evita roba palesemente "strana"
    score = 0
    if url.startswith("https://"):
        score += 50
    if ".m3u8" in url:
        score += 20
    if "akamaized" in url or "cloudfront" in url:
        score += 5
    if "stucazz" in url:
        score -= 999
    return score

def build_ref_maps(ref_entries: List[Entry]) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    # mappe per name_norm -> logo/chno/tvg-id (se presente)
    logo_map: Dict[str, str] = {}
    chno_map: Dict[str, str] = {}
    id_map: Dict[str, str] = {}

    for e in ref_entries:
        n = norm_name(e.name)
        if e.tvg_logo and n not in logo_map:
            logo_map[n] = e.tvg_logo
        if e.tvg_chno and n not in chno_map:
            chno_map[n] = e.tvg_chno
        if e.tvg_id and n not in id_map:
            id_map[n] = e.tvg_id
    return logo_map, chno_map, id_map

def pick_best(entries: List[Entry]) -> List[Entry]:
    # deduplica per "nome normalizzato" tenendo la url migliore
    best: Dict[str, Entry] = {}
    for e in entries:
        n = norm_name(e.name)
        if n not in best:
            best[n] = e
        else:
            if quality_score(e.url) > quality_score(best[n].url):
                best[n] = e
    return list(best.values())

def compute_lcn(e: Entry, ref_chno: Dict[str, str]) -> Optional[int]:
    n = norm_name(e.name)
    # 1) override manuale
    if n in LCN_OVERRIDES:
        return LCN_OVERRIDES[n]
    # 2) se nel tuo già c'è tvg-chno
    if e.tvg_chno.isdigit():
        return int(e.tvg_chno)
    # 3) dal reference (maginetweb)
    ch = ref_chno.get(n, "")
    if ch.isdigit():
        return int(ch)
    return None

def main():
    src = fetch(SRC_M3U)
    ref = fetch(REF_M3U)

    src_entries = parse_m3u(src)
    ref_entries = parse_m3u(ref)

    logo_map, chno_map, id_map = build_ref_maps(ref_entries)

    src_entries = pick_best(src_entries)

    # arricchisci con logo/chno (solo se mancanti) e tvg-id (se mancante)
    enriched: List[Tuple[int, str, Entry]] = []
    no_lcn: List[Entry] = []

    for e in src_entries:
        n = norm_name(e.name)

        if not e.tvg_logo and n in logo_map:
            e.extinf = set_attr(e.extinf, "tvg-logo", logo_map[n])
            e.tvg_logo = logo_map[n]

        lcn = compute_lcn(e, chno_map)
        if lcn is not None:
            e.extinf = set_attr(e.extinf, "tvg-chno", str(lcn))
            e.tvg_chno = str(lcn)

        if not e.tvg_id and n in id_map:
            e.extinf = set_attr(e.extinf, "tvg-id", id_map[n])
            e.tvg_id = id_map[n]

        if lcn is None:
            no_lcn.append(e)
        else:
            enriched.append((lcn, n, e))

    # ordina: prima LCN, poi nome; poi quelli senza LCN in coda alfabetici
    enriched.sort(key=lambda t: (t[0], t[1]))
    no_lcn.sort(key=lambda e: norm_name(e.name))

    out_lines = ["#EXTM3U"]
    for _, _, e in enriched:
        out_lines.append(e.extinf)
        out_lines.append(e.url)
    for e in no_lcn:
        out_lines.append(e.extinf)
        out_lines.append(e.url)

    sys.stdout.write("\n".join(out_lines) + "\n")

if __name__ == "__main__":
    main()
