"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE: run_benchmark.py
FOLDER: examples/
PURPOSE: Runs 10 episodes with 3 review types and prints comparison stats
USED BY: Judges evaluating the reward heuristic dynamically
KEY CLASSES/FUNCTIONS: main()
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import asyncio
from codereview_env.client import CodeReviewEnv
from codereview_env.models import CodeReviewAction

TYPES = [
    {"name": "Generic (bad)", "text": "LGTM looks good!"},
    {"name": "Medium", "text": "There might be an issue here. Consider fixing it."},
    {
        "name": "Specific (good)",
        "text": "Line 3: Critical bug — The indexing is exceeding array bounds causing a runtime error. Switch `>` to `>=` to patch it safely.",
    },
]


async def main():
    print("============================================================")
    print(" 📊 CodeReview-Env Dynamic Benchmarking ")
    print(" Running 10 episodes for each review type.")
    print("============================================================\n")

    port = os.getenv("PORT", "8000")
    base_url = f"http://localhost:{port}"

    results = {"Generic (bad)": [], "Medium": [], "Specific (good)": []}

    async with CodeReviewEnv(base_url=base_url) as env:
        for t in TYPES:
            print(f"Evaluating: {t['name']}...")
            for i in range(10):
                try:
                    await env.reset()
                    action = CodeReviewAction(
                        review_comment=t["text"], severity="major"
                    )
                    result = await env.step(action)
                    rew = float(
                        result.reward
                        if hasattr(result, "reward")
                        else (
                            result.get("reward", 0.05) if hasattr(result, "get") else 0.05
                        )
                    )
                    results[t["name"]].append(rew)
                except Exception as e:
                    print(
                        f"Error on iteration {i}: {e}. Ensure API relies on localhost:{port}"
                    )
                    break

    # Calculate statistics
    stats = {}
    for k, v in results.items():
        if len(v) == 0:
            stats[k] = (0.05, 0.05, 0.05)
            continue
        stats[k] = (sum(v) / len(v), min(v), max(v))  # Avg  # Min  # Max

    # Output Table
    print("\n┌────────────────┬──────────────┬──────────────┬──────────────┐")
    print("│ Review Type    │ Avg Reward   │ Min Reward   │ Max Reward   │")
    print("├────────────────┼──────────────┼──────────────┼──────────────┤")
    for k, (avg, mn, mx) in stats.items():
        print(f"│ {k:<14} │    {avg:.2f}      │    {mn:.2f}      │    {mx:.2f}      │")
    print("└────────────────┴──────────────┴──────────────┴──────────────┘\n")


if __name__ == "__main__":
    asyncio.run(main())
