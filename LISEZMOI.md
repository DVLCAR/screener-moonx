# Screener MoonX (étage 1)

Scanne les 138 cryptos du Futures MoonX en ~20 s, sans Claude et sans clé API.
Sortie : `resultats/dernier_scan.json` (top N + exclus avec raison).

## Lancer
    python3 screener.py --top 5

## Brancher sur la passe horaire (Claude Code)
Début du prompt de la tâche planifiée :
1. Lancer `python3 screener.py --top 5`.
2. Lire `resultats/dernier_scan.json`.
3. Analyse SMC complète avec les outils MoonX uniquement sur le top 5.
4. Respecter `levier_max` et `sl_guide_pct` du screener. Une position ouverte max.

## Filtres (en haut du script)
- Volume 24h < 1 M$ : exclu (volume spot Binance, plus bas que le futures).
- ATR 4h > 6 % : exclu.
- Levier max : liquidation au moins 2x plus loin que le SL, plafond 10x.
- XAU et PAXG : signalés « or tokenisé ».
- Sans données publiques : KAS, STBL, XMR (analyse MoonX directe si besoin).
