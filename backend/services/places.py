"""Small Jaipur gazetteer so the assistant can turn "Malviya Nagar" or "the airport" into coordinates."""
import difflib, re

PLACES = [("C-Scheme", 26.9124, 75.7873, ["c scheme", "cscheme"]), ("Jaipur Airport", 26.8242, 75.8122, ["airport", "jaipur airport", "sanganer airport", "jai airport"]),
          ("Malviya Nagar", 26.8540, 75.8243, ["malviya", "malviya nagar"]), ("Vaishali Nagar", 26.9126, 75.7442, ["vaishali", "vaishali nagar"]),
          ("Mansarovar", 26.8505, 75.7628, ["mansarovar", "mansarover"]), ("Jagatpura", 26.8399, 75.8322, ["jagatpura", "jnu", "jaipur national university"]),
          ("Raja Park", 26.8942, 75.8210, ["raja park", "rajapark"]), ("Bani Park", 26.9322, 75.7933, ["bani park", "banipark"]),
          ("Tonk Road", 26.8735, 75.7950, ["tonk road", "tonk rd"]), ("Amer Fort", 26.9855, 75.8513, ["amer", "amber", "amer fort", "amber fort"]),
          ("Sitapura Industrial Area", 26.7751, 75.8514, ["sitapura", "sitapura industrial area"]), ("Jhotwara", 26.9540, 75.7420, ["jhotwara"]),
          ("Civil Lines", 26.9064, 75.7790, ["civil lines"]), ("Sindhi Camp", 26.9227, 75.7994, ["sindhi camp", "bus stand", "sindhi camp bus stand"]),
          ("World Trade Park", 26.8530, 75.8056, ["wtp", "world trade park", "world trade centre"]), ("Railway Station", 26.9196, 75.7881, ["railway station", "jaipur junction", "station", "jaipur railway station"])]
_ALIASES = [(a, p) for p in PLACES for a in [p[0].lower()] + p[3]]
_STOP = re.compile(r"\b(the|near|at|in|my|to|from|jaipur(?! airport| national| junction| railway)|please)\b")


def _norm(t):
    t = re.sub(r"[^a-z0-9\- ]", " ", (t or "").lower().replace("-", " "))
    return re.sub(r"\s+", " ", _STOP.sub(" ", t)).strip()


def resolve(text):
    """-> (name, lat, lng) or None."""
    q = _norm(text)
    if not q:
        return None
    best = None
    for a, p in _ALIASES:
        an = _norm(a)
        if q == an:
            return p[:3]
        if (an in q or q in an) and len(min(an, q, key=len)) >= 4:
            if best is None or len(an) > best[0]:
                best = (len(an), p)
    if best:
        return best[1][:3]
    m = difflib.get_close_matches(q, [_norm(a) for a, _ in _ALIASES], n=1, cutoff=0.78)
    if m:
        for a, p in _ALIASES:
            if _norm(a) == m[0]:
                return p[:3]
    return None


def find_all(text):
    """Every known place mentioned in free text, in order of appearance -> [(name, lat, lng)]."""
    t = " " + re.sub(r"[^a-z0-9\- ]", " ", (text or "").lower()) + " "
    hits = []
    for a, p in _ALIASES:
        i = t.find(" " + a.replace("-", " ") + " ") if "-" not in a else t.find(" " + a + " ")
        if i < 0 and "-" in a:
            i = t.find(" " + a.replace("-", " ") + " ")
        if i >= 0:
            hits.append((i, len(a), p[:3]))
    out, seen = [], set()
    for i, _, p in sorted(hits, key=lambda h: (h[0], -h[1])):
        if p[0] not in seen:
            seen.add(p[0]); out.append(p)
    return out


def examples(n=4):
    return ", ".join(p[0] for p in PLACES[:n])
