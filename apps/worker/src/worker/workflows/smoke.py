"""Smoke test: fetch the Hacker News front page without needing an API key.

Run from the repo root in VS Code (F5 → "Smoke test: fetch HN front page") or:
    bash tools/uv.sh run --all-packages python -m worker.workflows.smoke
"""

import asyncio

from worker.workflows.tech_digest import fetch_hn_front_page


async def main() -> None:
    stories = await fetch_hn_front_page(10)
    print(f"fetched {len(stories)} stories from Hacker News")
    for story in stories:
        print(f"  [{story.score}] {story.title} -> {story.url}")


if __name__ == "__main__":
    asyncio.run(main())
