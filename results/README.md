# Results: feed-routing experiment

This folder is the lab notebook for the experiment in the write-up
[Who picked the new feed?](https://rajkiranvs.github.io/geo-news-mcp-server/).
The question: when an MCP tool gains a new option, does the model pick it up from the tool's
schema, or only when the system prompt tells it to?

## Files

| File | What it holds |
|---|---|
| `findings.md` | Every finding in order, numbered: F1–F37 (model behaviour), E1–E13 (engineering and method issues), R3-x and R3b-x (round 3). Corrections are added next to the original finding, not edited away. |
| `feed_choice.csv` | Every `get_feeds` call made by the local vLLM agent (Qwen2.5-3B), written by `eval_feed_choice.py`. Three runs per question. |
| `hosted_feed_choice.csv` | The same for the hosted runtimes (AgentCore / Nova Pro, Foundry / gpt-5.6-luna, Google ADK / gemini-3.8-flash), copied by hand from each runtime's traces. One run per question. |
| `prompts/` | Saved system prompts, so a run can be matched to the prompt it used. |

Both CSVs share these columns: `condition, platform, query_id, expected, run, call_index, feed, feed_type, keyword, error`.
`call_index` 0 marks a run with no successful call; `error` then says why (`no_tool_call`, `recursion_limit`).

## Conditions

| Condition | What changed |
|---|---|
| `baseline` | The prompt lists three feeds and routing rules; the schema already has a fourth feed (`aljazeera_all`) with a description. |
| `schema_only` | Feed list and routing rules removed from the prompt; one line tells the model to choose feeds by their descriptions in the tool. |
| `schema_format` | vLLM only: `schema_only` plus one prompt example showing `feed` as a list. |
| `schema_examples` | Round 3: the array example moves into the tool schema (`examples`); no prompt example of the feed format. New session for every question on every runtime. |
| `schema_format_examples` | vLLM only, accidental: both the prompt example and the schema example. Kept and labelled rather than deleted. |
| `shared_prompt` | vLLM only: Qwen given gpt-5.6-luna's Foundry prompt word for word, schema example kept. |

## Read before comparing

- **Sessions.** In `baseline` and `schema_only`, each hosted runtime answered all ten questions in one chat session, so a model could repeat its earlier calls (E13). vLLM always started fresh, and `schema_examples` used a new session everywhere.
- **Live feeds.** Feeds change by the hour, so compare the feed and keyword choices across conditions, not the answers.
- **Different models.** Each runtime ran a different model, so rows compare model-and-runtime pairs, not clouds.

## Re-running

The vLLM eval and the regression check need vLLM serving `Qwen/Qwen2.5-3B-Instruct-AWQ` on port 8000 and the deployed MCP server:

```
uv run --env-file .env eval_feed_choice.py <condition>
uv run --env-file .env check_routing.py
```

`check_routing.py` reads its questions and pass/fail rules from `questions.json`.
