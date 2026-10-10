# Étape 1 de chaque passe horaire : screener

À exécuter AVANT l'analyse décrite dans le plan de trading.

1. Lancer : `python3 screener.py --top 5`
2. Lire `resultats/dernier_scan.json`.
3. Si le script échoue (erreur 403 `host_not_allowed`, timeout, fichier absent) :
   - le signaler en une ligne en tête du compte rendu ;
   - analyser à la place BTC, ETH, SOL via les outils MoonX ;
   - ne pas modifier le script.
4. Étape 2 : analyse SMC complète avec les outils MoonX UNIQUEMENT sur les 5 cryptos du top.
   - Vérifier le prix MoonX (get_price) : le screener utilise des prix Binance.
   - Respecter `levier_max` et `sl_guide_pct` de chaque candidat. Jamais au-delà.
   - Une seule position ouverte à la fois.
   - Ignorer un candidat noté « RSI extreme » sauf retracement confirmé.
5. Ne jamais committer ni pousser `resultats/` ou toute modification du repo.

Compte rendu de fin de run : top 5 du screener (symbole, sens, score),
décision prise et pourquoi, ou raison de l'absence de trade.
