#!/usr/bin/env python3
"""
Screener horaire - univers Futures MoonX (etage 1 de l'entonnoir).

Role : scanner les ~138 cryptos chaque heure, sans Claude, et sortir
un top N de candidats pour l'analyse SMC complete (etage 2, Claude + MoonX).

Donnees : API publique Binance (data-api.binance.vision, sans cle, sans
blocage geographique), repli OKX pour les symboles absents. Prix spot,
suffisant pour du screening ; l'execution se fait sur MoonX.

Usage :  python3 screener.py [--top 5] [--out resultats]
Dependances : aucune (bibliotheque standard Python 3.9+).
"""
import argparse, json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

BINANCE = "https://data-api.binance.vision/api/v3/klines?symbol={s}USDT&interval={i}&limit={n}"
OKX = "https://www.okx.com/api/v5/market/history-candles?instId={s}-USDT-SWAP&bar={i}&limit={n}"
OKX_BAR = {"1h": "1H", "4h": "4H", "1d": "1Dutc"}

# Filtres (a ajuster apres 2 semaines de donnees)
MIN_VOL_24H_USD = 1_000_000   # liquidite minimale (volume spot, plus bas que futures)
MAX_ATR4H_PCT = 6.0           # au-dela : trop volatil pour 17 USDT
MAX_LEVERAGE = 10
NON_CRYPTO = {"XAU", "PAXG"}  # or : correle a autre chose, signale


# ---------- indicateurs (Wilder / EMA classiques) ----------
def ema(v, p):
    k, out = 2 / (p + 1), [v[0]]
    for x in v[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out

def rsi(c, p=14):
    g = [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
    l = [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ag, al = sum(g[:p]) / p, sum(l[:p]) / p
    for i in range(p, len(g)):
        ag, al = (ag * (p - 1) + g[i]) / p, (al * (p - 1) + l[i]) / p
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

def atr_adx(h, l, c, p=14):
    tr, pdm, mdm = [], [], []
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm.append(up if up > dn and up > 0 else 0)
        mdm.append(dn if dn > up and dn > 0 else 0)
    atr, sp, sm = sum(tr[:p]), sum(pdm[:p]), sum(mdm[:p])
    dxs = []
    for i in range(p, len(tr)):
        atr, sp, sm = atr - atr / p + tr[i], sp - sp / p + pdm[i], sm - sm / p + mdm[i]
        pdi, mdi = 100 * sp / atr, 100 * sm / atr
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0)
    adx = sum(dxs[:p]) / p
    for x in dxs[p:]:
        adx = (adx * (p - 1) + x) / p
    return atr / p, adx, pdi, mdi


# ---------- donnees ----------
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "screener/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def klines(sym, interval, n):
    base = sym[4:] if sym.startswith("1000") else sym
    try:
        rows = get(BINANCE.format(s=base, i=interval, n=n))
        # rejette les marches delistes (donnees figees) : derniere bougie < 1 jour
        if isinstance(rows, list) and rows and time.time() * 1000 - rows[-1][0] < 86_400_000:
            return [[float(x) for x in r[1:6]] + [float(r[7])] for r in rows], "binance"
    except Exception:
        pass
    try:
        d = get(OKX.format(s=base, i=OKX_BAR[interval], n=min(n, 100)))["data"]
        rows = [[float(x) for x in r[1:6]] + [float(r[7])] for r in reversed(d)]
        if rows and time.time() * 1000 - float(d[0][0]) < 86_400_000:
            return rows, "okx"
    except Exception:
        pass
    return None, None


# ---------- logique de score ----------
def equal_level_break(h1, side, tol=0.0015, lookback=48):
    """Cassure recente (3 dernieres bougies 1h) d'un niveau de bas/hauts egaux."""
    hist, recent, before = h1[-lookback:-3], h1[-3:], h1[-4]
    if side == "short":
        # niveau = plus bas du range recent qui tenait encore juste avant
        lvl = min(r[2] for r in hist)
        twins = [r for r in hist if (r[2] - lvl) / lvl < tol]
        if len(twins) >= 2 and before[3] > lvl and min(r[2] for r in recent) < lvl:
            return round(lvl, 6)
    else:
        lvl = max(r[1] for r in hist)
        twins = [r for r in hist if (lvl - r[1]) / lvl < tol]
        if len(twins) >= 2 and before[3] < lvl and max(r[1] for r in recent) > lvl:
            return round(lvl, 6)
    return None

def analyse(sym):
    k4, src = klines(sym, "4h", 300)
    kd, _ = klines(sym, "1d", 250)
    k1, _ = klines(sym, "1h", 60)
    if not k4 or not kd or not k1 or len(k4) < 60:
        return {"symbol": sym, "status": "pas de donnees"}
    o4, h4, l4, c4 = ([r[i] for r in k4] for i in range(4))
    cd = [r[3] for r in kd]
    price = c4[-1]
    vol24 = sum(r[5] for r in k1[-24:])
    atr, adx, pdi, mdi = atr_adx(h4, l4, c4)
    atr_pct = 100 * atr / price
    e20, e50, e200 = ema(c4, 20)[-1], ema(c4, 50)[-1], ema(c4, 200)[-1]
    d50 = ema(cd, 50)[-1]
    d200 = ema(cd, min(200, len(cd) - 1))[-1]
    r = rsi(c4)

    side = "short" if mdi > pdi else "long"
    daily_up = price > d50 and d50 > d200
    daily_dn = price < d50 and d50 < d200
    aligned = (side == "short" and daily_dn) or (side == "long" and daily_up)

    res = {"symbol": sym, "source": src, "price": price, "side": side,
           "adx4h": round(adx, 1), "rsi4h": round(r, 1), "atr4h_pct": round(atr_pct, 2),
           "vol24h_musd": round(vol24 / 1e6, 1), "ema20_4h": round(e20, 6),
           "aligne_daily": aligned, "status": "ok", "score": 0, "notes": []}

    if vol24 < MIN_VOL_24H_USD:
        res["status"] = "exclu: liquidite"; return res
    if atr_pct > MAX_ATR4H_PCT:
        res["status"] = "exclu: volatilite"; return res
    if sym in NON_CRYPTO:
        res["notes"].append("or tokenise")

    s = min(adx, 50) / 50 * 30                      # force de tendance 4h
    s += 25 if aligned else 0                        # alignement daily
    dist = abs(price - e20) / atr                    # proximite zone (EMA20 4h)
    in_premium = (side == "short" and price <= e20 * 1.002) or (side == "long" and price >= e20 * 0.998)
    s += max(0, 25 * (1 - dist / 1.5)) if in_premium else 0
    lvl = equal_level_break(k1, side)
    if lvl:
        s += 10; res["notes"].append(f"cassure niveau egal {lvl}")
    if (side == "short" and r < 30) or (side == "long" and r > 70):
        res["notes"].append("RSI extreme: attendre retracement")
    else:
        s += 10

    sl_pct = 1.2 * atr_pct                           # SL guide = 1,2 ATR 4h
    res.update(score=round(s, 1),
               sl_guide_pct=round(sl_pct, 2),
               levier_max=max(1, min(MAX_LEVERAGE, int(50 / sl_pct))),  # liquidation >= 2x SL
               zone_entree=round(e20, 6))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--universe", default=os.path.join(os.path.dirname(__file__), "universe.txt"))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "resultats"))
    a = ap.parse_args()

    syms = [x for x in open(a.universe).read().split() if x]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(analyse, syms))
    ok = sorted([r for r in res if r["status"] == "ok"], key=lambda r: -r["score"])

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    os.makedirs(a.out, exist_ok=True)
    payload = {"genere_utc": stamp, "duree_s": round(time.time() - t0, 1),
               "scannes": len(syms), "eligibles": len(ok),
               "top": ok[:a.top],
               "exclus": [{"symbol": r["symbol"], "raison": r["status"]} for r in res if r["status"] != "ok"]}
    for name in (f"scan_{stamp}.json", "dernier_scan.json"):
        with open(os.path.join(a.out, name), "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"{len(syms)} scannes, {len(ok)} eligibles, {payload['duree_s']}s")
    for r in ok[:a.top]:
        print(f"{r['symbol']:9} {r['side']:5} score {r['score']:5} | prix {r['price']} | ADX {r['adx4h']} "
              f"RSI {r['rsi4h']} ATR {r['atr4h_pct']}% | daily {'oui' if r['aligne_daily'] else 'non'} "
              f"| levier max {r['levier_max']}x | {'; '.join(r['notes'])}")


if __name__ == "__main__":
    sys.exit(main())
