from pathlib import Path

from sol_reality_check.pipeline import (
    SIGNAL_RESEARCH_PATH,
    build_predictive_power,
    read_signal_research_history,
)
from sol_reality_check.utils import iso_z, utc_now, write_json


def main() -> None:
    generated = iso_z(utc_now())
    frame = read_signal_research_history()
    cutoff = (
        str(frame["data_cutoff_utc"].dropna().max())
        if not frame.empty and "data_cutoff_utc" in frame
        else generated
    )
    method = (
        str(frame["method_version"].dropna().iloc[-1])
        if not frame.empty
        and "method_version" in frame
        and not frame["method_version"].dropna().empty
        else None
    )
    payload = build_predictive_power(
        frame,
        generated=generated,
        cutoff=cutoff,
        method_version=method,
        persisted=SIGNAL_RESEARCH_PATH.exists(),
    )
    write_json(Path("site/data/predictive_power.json"), payload)


if __name__ == "__main__":
    main()
