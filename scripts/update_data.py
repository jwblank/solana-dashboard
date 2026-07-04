from sol_reality_check.pipeline import build_outputs

if __name__ == "__main__":
    build_outputs(__import__("os").getenv("APP_MODE", "demo"))
