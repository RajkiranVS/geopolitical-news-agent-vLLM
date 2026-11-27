import json
import asyncio, csv, sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError

from agent import RECURSION_LIMIT, build_agent

CONDITION = sys.argv[1] if len(sys.argv) > 1 else "baseline"
RUNS = 3
OUT = Path("results/feed_choice.csv")
FIELDS = ["condition", "platform", "query_id", "expected", "run", "call_index", "feed", "feed_type", "keyword", "error"]

with open('questions.json','r') as f:
    queries_data = json.load(f)

QUERIES = [(q.get('id'), q.get('query'), q.get('expected')) for q in queries_data]

def _as_list(value) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


async def main():
    agent = await build_agent()
    OUT.parent.mkdir(exist_ok=True)
    new_file = not OUT.exists()
    first_feeds = {}  # (query_id, run) -> feeds of the first call

    with OUT.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()

        for qid, text, expected in QUERIES:
            for run in range(1, RUNS + 1):
                base = dict(condition=CONDITION, platform="vllm", query_id=qid, expected=expected, run=run)
                try:
                    resp = await agent.ainvoke(
                        {"messages": [HumanMessage(content=text)]},
                        config={"recursion_limit": RECURSION_LIMIT},
                    )
                except GraphRecursionError:
                    writer.writerow({**base, "call_index": 0, "error": "recursion_limit"})
                    continue

                calls = [tc for m in resp["messages"] if isinstance(m, AIMessage)
                         for tc in m.tool_calls if tc["name"] == "get_feeds"]
                if not calls:
                    writer.writerow({**base, "call_index": 0, "error": "no_tool_call"})
                    continue
                for i, tc in enumerate(calls, start=1):
                    raw = tc["args"].get("feed")
                    feeds = _as_list(raw)
                    feed_type = "str" if isinstance(raw, str) else "list" if isinstance(raw, list) else type(raw).__name__
                    writer.writerow({**base, "call_index": i, "feed": ";".join(feeds), "feed_type": feed_type,
                                     "keyword": tc["args"].get("keyword") or ""})
                first_feeds[(qid, run)] = _as_list(calls[0]["args"].get("feed"))
                print(f"q{qid} r{run}: {calls[0]['args'].get('feed')}")

    # Summary: share of runs whose first get_feeds call included aljazeera_all.
    # Runs with no tool call or a recursion error never land in first_feeds -> "not picked".
    print(f"\n[{CONDITION}] aljazeera_all picked on first call:")
    for group in ("yes", "no"):
        keys = [(qid, run) for qid, _, exp in QUERIES if exp == group
                for run in range(1, RUNS + 1)]
        picked = sum("aljazeera_all" in first_feeds.get(k, []) for k in keys)
        print(f"  expected={group:<3} {picked}/{len(keys)} = {picked / len(keys):.0%}")

    for qid, text, exp in QUERIES:
        if exp == "optional":
            print(f"  q{qid}: {[first_feeds.get((qid, r)) for r in range(1, RUNS + 1)]}")

if __name__ == "__main__":
    asyncio.run(main())