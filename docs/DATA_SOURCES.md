# Data Sources

De prijslaag gebruikt in productie primair een CCXT multi-exchange consensus voor SOL en BTC
dagcandles. De pipeline haalt candles op bij de geconfigureerde exchanges, berekent per dag de
mediane close en negeert exchange-candles die te ver van de consensus liggen. Er zijn minimaal twee
bruikbare bronnen nodig voor een consensusdag.

Coinbase Exchange blijft beschikbaar als fallback wanneer de CCXT-consensus niet genoeg bruikbare
bronnen oplevert. CoinGecko levert actuele prijscontrole en ecosysteembreedte. DeFiLlama levert TVL,
stablecoins, DEX-volume en fees. Solana RPC levert compacte actuele netwerkcontext die niet als
historisch gevalideerd signaal wordt gebruikt.

Productiemodus gebruikt geen fixtures. Bij bronuitval, prijsreparaties of exchange-afwijkingen moet
de data-audit dit zichtbaar maken en moet de bewijskwaliteit conservatief blijven.
