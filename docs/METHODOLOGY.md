# Methodology

Rendement is `prijs_t / prijs_t-n - 1`. Relatieve sterkte is SOL-rendement min BTC-rendement. Volatiliteit gebruikt log-rendementen over 30 dagen. Drawdown is de afstand tot de hoogste koers in 90 dagen.

Normalisatie gebruikt uitsluitend eerdere data: `0.6745 * (waarde - rolling mediaan) / MAD`, geclipt op `[-4, 4]`. Indicatoren worden naar 0-100 vertaald met `50 + 12.5 * z`.

Analogieën gebruiken een gewogen Euclidische afstand op robuust genormaliseerde features. Similarity is `100 * exp(-0.5 * afstand^2)`.

Bewijskwaliteit combineert datakwaliteit, steekproefomvang, out-of-sample kwaliteit, stabiliteit en analogie-overeenkomst. Caps voorkomen te stellige conclusies bij zwakke onderbouwing.

