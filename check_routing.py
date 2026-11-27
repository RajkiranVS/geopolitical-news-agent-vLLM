'''
A script to analyze the routing logic of the agent.

This is not expected to be a part of CI. Ran locally before finalizing the project.

Checks only the first get_feeds call of each run. A run fails if it hits the
recursion limit, makes no get_feeds call, passes `feed` as anything other than
a list, or includes a must_exclude feed. Missing should_include feeds only warn.
Exits 1 if any run failed.
'''

import asyncio
import json
import sys

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError

from agent import RECURSION_LIMIT, build_agent
from eval_feed_choice import _as_list, RUNS


with open('questions.json', 'r') as f:
    queries_data = json.load(f)

QUERIES = [(q.get('id'), q.get('query'), q.get('must_exclude'), q.get('should_include')) for q in queries_data]


async def main() -> int:
    agent = await build_agent()
    failures = 0
    warnings = 0
    total = 0

    for qid, text, must_exclude, should_include in QUERIES:
        for run in range(1, RUNS + 1):
            total += 1
            tag = f"[{qid} run {run}]"
            try:
                resp = await agent.ainvoke(
                    {"messages": [HumanMessage(content=text)]},
                    config={"recursion_limit": RECURSION_LIMIT},
                )
            except GraphRecursionError:
                print(f"Error {tag}: hit recursion limit ({RECURSION_LIMIT})")
                failures += 1
                continue

            calls = [tc for m in resp["messages"] if isinstance(m, AIMessage)
                     for tc in m.tool_calls if tc["name"] == "get_feeds"]
            if not calls:
                print(f"Error {tag}: no get_feeds call")
                failures += 1
                continue

            raw = calls[0]["args"].get("feed")
            if not isinstance(raw, list):
                print(f"Error {tag}: feed is {type(raw).__name__}, expected list: {raw!r}")
                failures += 1
                continue

            feeds = set(_as_list(raw))
            violation = set(must_exclude or []) & feeds
            missing = set(should_include or []) - feeds
            if violation:
                print(f"Error {tag}: feed contains excluded {sorted(violation)}")
                failures += 1
            if missing:
                print(f"Warning {tag}: feed is missing {sorted(missing)}")
                warnings += 1

    print(f"\n{total - failures}/{total} runs passed, {failures} failed, {warnings} warnings")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
