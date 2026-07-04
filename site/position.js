window.setupPosition = function setupPosition(dashboard, analogs) {
  const buy = document.getElementById("buy-price");
  const amount = document.getElementById("amount-sol");
  const horizon = document.getElementById("position-horizon");
  const out = document.getElementById("position-output");
  buy.value = localStorage.getItem("buyPrice") || "";
  amount.value = localStorage.getItem("amountSol") || "";
  horizon.value = localStorage.getItem("positionHorizon") || "7";
  function update() {
    localStorage.setItem("buyPrice", buy.value);
    localStorage.setItem("amountSol", amount.value);
    localStorage.setItem("positionHorizon", horizon.value);
    const b = Number(buy.value);
    const a = Number(amount.value);
    if (!b || !a) {
      out.textContent = "Vul je aankoopkoers en aantal SOL in. De gegevens blijven alleen in deze browser.";
      return;
    }
    const price = dashboard.current.sol_price;
    const invested = b * a;
    const value = price * a;
    const result = value - invested;
    const needed = b / price - 1;
    const col = `return_${horizon.value}d`;
    const paths = analogs.map((r) => r[col]).filter((x) => Number.isFinite(x));
    if (horizon.value === "90" && paths.length < 20) {
      out.textContent = "Voor 90 dagen is de onderbouwing nog onvoldoende.";
      return;
    }
    const reached = paths.filter((x) => x >= needed).length;
    const freq = paths.length ? reached / paths.length : null;
    out.textContent = `Huidige waarde $${value.toFixed(2)}. Inleg $${invested.toFixed(2)}. Ongerealiseerd resultaat $${result.toFixed(2)} (${(result / invested * 100).toFixed(1)}%). Benodigde stijging tot break-even: ${(needed * 100).toFixed(1)}%. In deze vergelijkingsgroep haalde ${freq === null ? "n.v.t." : (freq * 100).toFixed(1) + "%"} die eindwaarde.`;
  }
  [buy, amount, horizon].forEach((el) => el.addEventListener("input", update));
  update();
};

