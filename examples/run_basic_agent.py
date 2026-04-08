"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE: run_basic_agent.py
FOLDER: examples/
PURPOSE: Demonstrates running one complete episode in CodeReview-Env
USED BY: Anyone wanting to try the environment manually
KEY FUNCTIONS: main() — connects, resets, steps, prints reward
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import asyncio
from codereview_env.client import CodeReviewEnv
from codereview_env.models import CodeReviewAction

async def main():
    print("============================================================")
    print(" 🤖 Welcome to CodeReview-Env Basic Agent Run ")
    print(" This script will connect to the environment, load a PR")
    print(" diff, and submit a hardcoded actionable review.")
    print("============================================================\n")

    port = os.getenv("PORT", "8000") # Use 7860 if running via docker mapping
    base_url = f"http://localhost:{port}"
    print(f"[*] Connecting to Environment Server at {base_url}...")

    async with CodeReviewEnv(base_url=base_url) as env:
        try:
            print("\n[*} Calling reset()...")
            obs = await env.reset()
            print(f"    Loaded file: {obs.filename} ({obs.language})")
            print("    PR Diff Snippet:")
            print("------------------------------------------------------------")
            print(obs.pr_diff[:300] + "\n..." if len(obs.pr_diff) > 300 else obs.pr_diff)
            print("------------------------------------------------------------\n")

            hardcoded_review = (
                "Line 3: There's an off-by-one error here. The loop should use < len(items) "
                "instead of <= len(items). Consider using enumerate() for cleaner iteration."
            )
            print(f"[*] Submitting Review:\n    \"{hardcoded_review}\"\n")

            action = CodeReviewAction(
                review_comment=hardcoded_review,
                severity="major",
                line_references=[3]
            )

            result = await env.step(action)
            
            # The result could be a StepResult or mapping depending on OpenEnv integration
            info = result.info if hasattr(result, "info") else result.get("info", {}) if isinstance(result, dict) else {}
            reward = float(result.reward if hasattr(result, "reward") else result.get("reward", 0.0) if hasattr(result, "get") else 0.0)
            breakdown = info.get("reward_breakdown", {})
            checks = breakdown.get("checks", {})
            llm = breakdown.get("llm_scores", {})

            def tick(val): return "✅" if val else "❌"

            table = f"""
┌─────────────────────────────┬────────┐
│ Check                       │ Result │
├─────────────────────────────┼────────┤
│ Not empty                   │  {tick(checks.get('not_empty'))}    │
│ Detailed (>100 chars)       │  {tick(checks.get('is_detailed'))}    │
│ References line numbers     │  {tick(checks.get('has_line_references'))}    │
│ Actionable language         │  {tick(checks.get('is_actionable'))}    │
│ Not generic                 │  {tick(checks.get('not_generic'))}    │
│ LLM Bug Detection           │  {llm.get('bug_detection', 0)}/10  │
│ LLM Specificity             │  {llm.get('specificity', 0)}/10  │
│ LLM Actionability           │  {llm.get('actionability', 0)}/10  │
├─────────────────────────────┼────────┤
│ TOTAL REWARD                │  {reward:.2f}  │
└─────────────────────────────┴────────┘
            """
            print(table)
            print("Run with: python examples/run_basic_agent.py\n")

        except Exception as e:
            print(f"Error communicating with environment: {e}")
            print("Make sure your API server is running (uvicorn server.app:app)")

if __name__ == "__main__":
    asyncio.run(main())
