from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

from eval.invokers import ServiceInvoker, SkippedIntent
from eval.post_checks import forbidden_keywords_check, source_overlap
from eval.profiles import PROFILES
from eval.reporting import aggregate, print_table
from eval.schema import load_goldens

#this is the main entry point for the eval pipeline.
#it loads goldens, runs them through the rag system, scores them with ragas,
#runs post-checks, then saves a json report and prints a markdown table.
def main() -> None:
    #set up cli arguments so the user can pick which profile and questions file to use
    ap = argparse.ArgumentParser(description="Run Ragas eval harness")
    ap.add_argument(
        "--profile",
        required=True,
        choices=list(PROFILES.keys()),
        help="Flag profile to evaluate",
    )
    ap.add_argument(
        "--questions",
        default="eval/seed_questions.yaml",
        help="Path to seed questions YAML",
    )
    ap.add_argument(
        "--filter",
        default=None,
        help="Only run goldens with demonstrates_feature == FILTER (plus baseline)",
    )
    ap.add_argument(
        "--mode",
        default="service",
        choices=["service", "api"],
        help="Invocation mode",
    )
    ap.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: eval/results/<timestamp>_<profile>.json)",
    )
    args = ap.parse_args()
    flags = PROFILES[args.profile]
    goldens = load_goldens(args.questions)

    #if a feature filter is given, only run goldens for that feature plus the baselines
    if args.filter:
        goldens = [
            g
            for g in goldens
            if g.demonstrates_feature in (args.filter, "baseline")
        ]
    if args.mode == "service":
        invoker = ServiceInvoker()
    else:
        print("API mode not yet implemented (Phase B).", file=sys.stderr)
        sys.exit(1)

    rows: list[dict] = []
    skipped: list[dict] = []

    #run each golden through the rag system and collect the answers
    for g in goldens:
        try:
            resp, chunks = invoker.invoke(g.question, flags, g.intent)
        except SkippedIntent as e:
            #intent not supported by this invoker, skip it gracefully
            skipped.append({"id": g.id, "reason": str(e)})
            continue
        except Exception as e:
            #unexpected error, skip it and log the reason
            skipped.append({"id": g.id, "reason": f"error: {e}"})
            continue

        #store everything we need for ragas scoring and post-checks
        rows.append(
            {
                "id": g.id,
                "demonstrates_feature": g.demonstrates_feature,
                "intent": g.intent,
                "question": g.question,
                "answer": resp.answer,
                "contexts": [c.text for c in chunks],
                "ground_truth": ", ".join(g.golden_answer_keywords),
                "actual_sources": resp.sources,
                "golden_sources": g.golden_sources,
                "forbidden_keywords": g.forbidden_keywords,
            }
        )

    #run ragas scoring on all the rows we collected
    if rows:
        from eval.ragas_adapter import run as run_ragas
        metrics = run_ragas(rows)
    else:
        metrics = []

    #attach the ragas scores and post-check results to each row
    for row, m in zip(rows, metrics):
        row["ragas_metrics"] = m
        row["forbidden_check"] = forbidden_keywords_check(
            row["answer"], row["forbidden_keywords"]
        )
        row["source_overlap"] = source_overlap(
            row["actual_sources"], row["golden_sources"]
        )

    #build the output file path, defaults to eval/results/<timestamp>_<profile>.json
    timestamp = datetime.datetime.now(datetime.timezone.utc)
    out_path = (
        Path(args.output)
        if args.output
        else Path(
            f"eval/results/{timestamp:%Y%m%dT%H%M%SZ}_{args.profile}.json"
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    #assemble the full result payload and write it to disk
    payload = {
        "profile": args.profile,
        "flags": flags,
        "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
        "filter": args.filter,
        "mode": args.mode,
        "rows": rows,
        "skipped": skipped,
        "aggregate": aggregate(rows),
    }

    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print_table(payload)
    print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()
