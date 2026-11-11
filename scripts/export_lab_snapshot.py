from sol_reality_check.lab_snapshot import export_lab_snapshot

if __name__ == "__main__":
    snapshot = export_lab_snapshot()
    print(f"Lab snapshot: {len(snapshot['queries']['history']['rows'])} oorspronkelijke datadagen")
