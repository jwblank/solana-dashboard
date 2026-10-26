from __future__ import annotations

from sol_reality_check.predictive_monitor import generate_predictive_monitor

if __name__ == "__main__":
    payload = generate_predictive_monitor()
    status = payload["status"]
    print(
        "Voorspelmonitor bijgewerkt: "
        f"{len(payload['events'])} events, status {status['label']}."
    )
