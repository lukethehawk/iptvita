import re
import sys
import socket
import urllib.request
import urllib.parse
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

SRC_M3U = "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/it.m3u"
REF_M3U = "https://raw.githubusercontent.com/maginetweb-arch/TVITALIA/refs/heads/main/iptvit.m3u"

MAX_ALTS = 4          # quante alternative tenere per canale
HTTP_TIMEOUT = 8      # timeout check URL
UA = "Mozilla/5.0"

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

# Fallback Mediaset: dominio alternativo + pattern channel(...)
# (codici canale come li trovi nelle URL mediaset: i1, C5, r4, lb, ki, lt, b6, ka, i2, kf, kq, ...)
MEDIASET_FALLBACK_HOSTS = [
    # spesso risolve anche quando alcuni "liveX-mediaset-it.akamaized.net" no
    "https://live2.msf.cdn.mediaset.net",
    "https://live3.msf.cdn.mediaset.net",
]

MEDIASET_CHANNEL_CODES = {
    "rete 4": "r4",
    "canale 5": "C5",
    "italia 1": "i1",
    "20 mediaset": "lb",
    "iris": "ki",
    "top crime": "lt",
    "cine 34": "b6",
    "la5": "ka",
    "italia 2": "i2",
    "tgcom 24": "kf",
    "mediaset extra": "kq",
}

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def norm_name(s: str) -> str:
    s = s.strip().lower()
    s = s.replace("’", "'")

    # rimuove tag tra parentesi e quadre: (720p), [Geo-blocked], ecc.
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)

    # rimuove suffix comuni tipo "hd", "fhd", "uhd"
    s = re.sub(r"\b(uhd|fhd|hd|sd)\b", " ", s)

    # pulizia spazi
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # normalizzazioni “furbe”
    s = s.replace("la 7", "la7")
    s = s.replace("rai yo yo", "rai yoyo")
    s = s.replace("twenty seven", "twentyseven")
    s = s.replace("20 mediaset", "20 mediaset")  # lascio coerente con overrides

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
    attrs = {}
    for k in ["tvg-id", "tvg-logo", "tvg-chno", "group-title"]:
        m = re.search(rf'{k}="([^"]*)"', line)
        if m:
            attrs[k] = m.group(1).strip()
    return attrs

def parse_m3u(text: str) -> List[Entry]:
    lines = [ln.rstrip("\n") for ln in text.splitlines() if ln.strip() != ""]
    out: List[Entry] = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("#EXTINF:"):
            extinf = lines[i].strip()
            url = ""
            # prendi la prima riga non-comment subito dopo (attenzione: ci possono essere #EXTVLCOPT in mezzo)
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("#") and not lines[j].strip().startswith("#EXTINF:"):
                j += 1
            if j < len(lines) and not lines[j].strip().startswith("#"):
                url = lines[j].strip()
                i = j
            name = extinf.split(",")[-1].strip()  # display name dopo ultima virgola
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
    return extinf.replace("#EXTINF:-1", f'#EXTINF:-1 {key}="{value}"', 1)

def quality_score(url: str) -> int:
    score = 0
    if not url:
        return -999999
    if url.startswith("https://"):
        score += 50
    if ".m3u8" in url:
        score += 20
    if "akamaized" in url or "cloudfront" in url:
        score += 5
    # penalità per cose palesemente “non live” o strane
    if "relinkerServlet.htm" in url:
        score -= 5
    return score

def host_resolves(url: str) -> bool:
    try:
        u = urllib.parse.urlparse(url)
        host = u.hostname
        if not host:
            return False
        socket.getaddrinfo(host, None)
        return True
    except Exception:
        return False

def url_responds(url: str) -> bool:
    # HEAD spesso è bloccato; facciamo GET leggero (Range) con timeout corto
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Range": "bytes=0-2047"
        })
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            code = getattr(r, "status", 200)
            return 200 <= code < 500  # 403/404 = comunque “risponde”, almeno DNS+server ok
    except Exception:
        return False

def mediaset_fallbacks_for(name: str) -> List[str]:
    n = norm_name(name)
    code = MEDIASET_CHANNEL_CODES.get(n)
    if not code:
        return []
    # pattern visto nelle tue URL: /content/hls_h0_clr_vos/live/channel(<code>)/index.m3u8
    # (metto anche variant Content/ content e clr/cls per robustezza)
    paths = [
        f"/content/hls_h0_clr_vos/live/channel({code})/index.m3u8",
        f"/Content/hls_h0_clr_vos/live/channel({code})/index.m3u8",
        f"/content/hls_h0_cls_vos/live/channel({code})/index.m3u8",
        f"/Content/hls_h0_cls_vos/live/channel({code})/index.m3u8",
    ]
    out = []
    for host in MEDIASET_FALLBACK_HOSTS:
        for p in paths:
            out.append(host.rstrip("/") + p)
    return out

def build_ref_maps(ref_entries: List[Entry]) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
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

def compute_lcn(e: Entry, ref_chno: Dict[str, str]) -> Optional[int]:
    n = norm_name(e.name)
    if n in LCN_OVERRIDES:
        return LCN_OVERRIDES[n]
    if e.tvg_chno.isdigit():
        return int(e.tvg_chno)
    ch = ref_chno.get(n, "")
    if ch.isdigit():
        return int(ch)
    return None

def choose_working(entries: List[Entry]) -> List[Entry]:
    """
    Per ogni nome normalizzato:
    - raccoglie candidate (incluse fallback mediaset)
    - ordina per quality_score (desc)
    - sceglie la prima che risolve e risponde
    """
    grouped: Dict[str, List[Entry]] = {}
    for e in entries:
        n = norm_name(e.name)
        grouped.setdefault(n, []).append(e)

    chosen: List[Entry] = []
    for n, lst in grouped.items():
        # aggiungi fallback mediaset come "Entry" extra (solo URL, extinf copiato dal primo)
        base = lst[0]
        for fb in mediaset_fallbacks_for(base.name):
            lst.append(Entry(extinf=base.extinf, url=fb, name=base.name,
                             tvg_id=base.tvg_id, tvg_logo=base.tvg_logo,
                             tvg_chno=base.tvg_chno, group=base.group))

        # ordina e limita alternative
        lst_sorted = sorted(lst, key=lambda x: quality_score(x.url), reverse=True)[:MAX_ALTS]

        best = lst_sorted[0]
        for cand in lst_sorted:
            if cand.url and host_resolves(cand.url) and url_responds(cand.url):
                best = cand
                break

        # IMPORTANT: mantieni METADATI del "base" ma URL del best selezionato
        base.url = best.url
        chosen.append(base)

    return chosen

def main():
    src = fetch(SRC_M3U)
    ref = fetch(REF_M3U)

    src_entries = parse_m3u(src)
    ref_entries = parse_m3u(ref)

    logo_map, chno_map, id_map = build_ref_maps(ref_entries)

    # scegli URL funzionanti (e integra fallback)
    src_entries = choose_working(src_entries)

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
