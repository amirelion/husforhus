# pipeline/run.py
"""Run pipeline steps in their declared order.

    uv run python -m pipeline.run                    # every step
    uv run python -m pipeline.run s03_tiles s04_base s07_labels   # just these, in declared order (never s03_tiles alone)
    uv run python -m pipeline.run --list
    uv run python -m pipeline.run s99_validate -- --release   # arguments after -- go to each step's main()
"""
import argparse
import importlib
import sys
import time

STEPS = ["s00_fetch_city", "s00_fetch_raa", "s00_fetch_raa_old", "s00_fetch_wikidata", "s00_fetch_osm", "s00_fetch_dem",
         "s00_fetch_plaques", "s00_fetch_stadsmuseet", "s01_load", "s08_landmarks", "s02_years", "s02_attributes",
         "s02_addresses", "s02_stadsmuseet", "s02_stadsmuseet_photos", "s02_terrain", "s06_wiki", "s00_fetch_laser", "s02_towers", "s03_tiles",
         "s16_metro", "s04_base", "s17_ferries", "s07_labels", "s14_search", "s15_plaques", "s13_quests", "s99_validate"]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    step_args = []
    if "--" in argv:
        at = argv.index("--")
        argv, step_args = argv[:at], argv[at + 1:]
    ap = argparse.ArgumentParser(prog="python -m pipeline.run", description="Run pipeline steps in order.")
    ap.add_argument("steps", nargs="*", help="steps to run (default: all)")
    ap.add_argument("--list", action="store_true", help="print the steps in order and exit")
    args = ap.parse_args(argv)
    if args.list:
        print("\n".join(STEPS))
        return 0
    unknown = [s for s in args.steps if s not in STEPS]
    if unknown:
        print(f"unknown step: {', '.join(unknown)} (known: {', '.join(STEPS)})", file=sys.stderr)
        return 2
    chosen = [s for s in STEPS if s in args.steps] if args.steps else list(STEPS)
    t_all = time.perf_counter()
    for name in chosen:
        try:
            module = importlib.import_module(f"pipeline.{name}")
        except ModuleNotFoundError as e:
            if e.name != f"pipeline.{name}":
                raise
            print(f"step {name} is not implemented yet", file=sys.stderr)
            return 1
        t0 = time.perf_counter()
        print(f"== {name}", flush=True)
        module.main(list(step_args))
        print(f"== {name}: {time.perf_counter() - t0:.1f} s", flush=True)
    print(f"== total: {time.perf_counter() - t_all:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
