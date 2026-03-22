#!/usr/bin/env python3
"""Run all 6 experiments sequentially. Aggregate results."""
import json, os, time, importlib, sys

EXPERIMENTS = [
    "01_wrap_coding",
    "02_langchain_research",
    "03_track_customer",
    "04_crewai_team",
    "05_autogen_debate",
    "06_chaos_errors",
]

def main():
    os.makedirs("results", exist_ok=True)
    all_results = []
    total_start = time.time()

    for name in EXPERIMENTS:
        print(f"\n{'='*60}")
        print(f"  Running: {name}")
        print(f"{'='*60}\n")
        try:
            mod = importlib.import_module(name)
            result = mod.run()
            all_results.append(result)
        except Exception as e:
            print(f"  FAILED: {e}")
            all_results.append({"experiment": name, "error": str(e)})

    total_elapsed = time.time() - total_start
    summary = {
        "total_duration_s": round(total_elapsed, 1),
        "total_records": sum(r.get("records", 0) for r in all_results),
        "experiments": all_results,
    }

    with open("results/summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print(f"  ALL EXPERIMENTS COMPLETE")
    print(f"  Total: {summary['total_records']} records in {summary['total_duration_s']}s")
    print(f"  Results: results/summary.json")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
