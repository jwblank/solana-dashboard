# Backtest

De backtest is walk-forward. Voor elke historische datum wordt alleen data gebruikt die op dat moment beschikbaar had kunnen zijn. Analoge dagen liggen vóór de voorspeldatum en toekomstige uitkomsten worden pas na de horizon beoordeeld.

Horizons: 1, 7 en 30 dagen. Benchmarks: altijd omhoog, historische baserate, eenvoudig momentum en relatief momentum. Overlappende horizons worden apart benoemd via niet-overlappende aantallen. De bootstrap is configureerbaar en reproduceerbaar met vaste seed.

