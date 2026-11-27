# Feed-routing experiment — findings log

Experiment: move feed routing out of system prompts into the MCP tool schema
(per-feed `about` descriptions); add a 4th feed (`aljazeera_all`); measure how
often each model picks it. Data: `feed_choice.csv` (vLLM), `hosted_feed_choice.csv`.

Conditions
- baseline: prompt still names 3 feeds + routing rules; schema has 4 feeds with descriptions
- schema_only: feed names/routing removed from prompt; added
  "feed: choose every feed whose description in the tool fits the question."
- schema_format (vLLM only): schema_only + one placeholder example `feed: ["<feed>", "<feed>"]`

## Results so far

| Model / runtime | Condition | AJ when it fits (q1-4) | AJ on India q (q5-7) | Feeds per call | feed as list |
|---|---|---|---|---|---|
| Qwen2.5-3B AWQ / vLLM | baseline | 0/12 | 0/9 | 1-2 | 10/10 |
| Qwen2.5-3B AWQ / vLLM | schema_only | 3/12 | 0/9 | 1 | 2/10 (6 string, 2 no call) |
| Qwen2.5-3B AWQ / vLLM | schema_format | 9/12 | 0/9 | 1-2 | 10/10 |
| Nova Pro v1 / AgentCore | baseline | 0/4 | 0/3 | 3 (all old) | 10/10 |
| Nova Pro v1 / AgentCore | schema_only | 4/4 | 3/3 | 4 (all) | 10/10 |
| gpt-5.6-luna / Foundry | baseline | 0/4 | 0/3 | 2 (3 on India q) | 10/10 |
| gpt-5.6-luna / Foundry | schema_only | 4/4 | 0/3 | 3 world; 1-3 India | 10/10 |
| gemini-3.8-flash / Google ADK | baseline | 0/4 | 0/3 | 2 (3 on India q) | 10/10 |
| gemini-3.8-flash / Google ADK | schema_only | 4/4 | 1/3 | 3 world; 1 or 4 India | 10/10 |

Notes: vLLM runs at temperature 0 -> 3 runs per query were identical (effectively n=10/condition).
Hosted models: 1 run per query.

## Findings (model behaviour)

F1. Prompt beats schema. With routing rules in the prompt, the new feed was never
    picked by either model (0%), although the schema described it.
F2. Cost of prompt routing: on AgentCore baseline, Gaza/Sudan/Lebanon/Sahel returned
    few or no items because the feed that covers them was never queried.
F3. Examples do double duty (Qwen). Removing feed names from examples also removed the
    only demonstration of the list format -> `feed` sent as a string in 7/10 queries
    (server rejects). A placeholder example `["<feed>", "<feed>"]` fixed format 10/10.
F4. With format fixed, Qwen routes by description: 75% AJ hit, 0% false picks on India q.
F5. (Note: the 9/12 schema_format hit rate counts these 3 Sahel calls as AJ picks, but they
    were rejected — 6/12 picks actually fetched AJ.)
    Qwen invented a feed: feed ["reuters_africa","aljazeera_all"] (Sahel, schema_format).
    CONFIRMED in MLflow (trace tr-1875c757...): pydantic literal_error, the whole call was
    rejected -> the valid aljazeera_all was never fetched either. Allowlist worked.
    But the recovery failed: no retry with the valid feed although the error listed all
    four; the answer said "no matching headlines right now" (false — nothing was fetched),
    then exposed feed IDs and asked the user about "reuters_africa".
    Design options: drop unknown feeds and report them in failed_feeds (reason
    "unknown_feed") so valid feeds still return; prompt: "if a call fails validation, fix
    the arguments and call again".
F6. Indian domestic topics (state elections, RBI) routed to hindu_international instead of
    hindu_national in every Qwen condition.
F7. Qwen schema_only: q6 hit recursion limit x3; q8 (Ukraine) made no tool call x3.
F8. Nova Pro does not route, it includes everything: all 3 feeds in baseline, all 4 in
    schema_only. "every feed whose description fits" may encourage this. Cheap in tokens
    (keyword filter + limit), costs one extra fetch (latency).
F9. Hit rate alone misleads for include-all models -> report hit rate, false-pick rate
    AND average feeds per call.
F10. Nova Pro, "India's Supreme Court" (schema_only) — three layers failed:
     a) Retrieval: bag-of-words keyword match let through a US tariffs story whose summary
        mentions India + "Supreme" + "Court" (the US Supreme Court ruling).
     b) Relevance: model presented it as India's Supreme Court news despite the prompt rule
        "Include only items directly about the user's topic".
     c) Faithfulness: every fact is in the source, but the model merged the struck-down
        tariffs and the new excess-capacity duties into one event, and said India was
        affected by the struck-down tariffs (source: named for the new duties).
     Lesson: a citation check proves each fact has a source, not that the summary is right.
F11. Keyword quality: models pass multi-word keywords ("Indian state elections",
     "RBI India's economy") that the all-terms filter makes too narrow.
F12. agent.py smoke test (Qwen, Ukraine): a North Korea item passed the keyword filter and
     was presented as Ukraine news; one bullet's summary did not match its headline
     (Russia's own figures vs "leaked data") — check in MLflow.

F13. Foundry baseline is the only model that routes Indian domestic questions correctly:
     adds hindu_national for q5-7 only (Qwen never did, Nova always did). Prompt routing
     works well here — but still 0/4 Al Jazeera, same as F1.
F14. Foundry q2 (Sudan): keyword "Sudan" on bbc_world + hindu_international -> no matches;
     retry call 2 without keyword (same 2 feeds) also had nothing on Sudan — retry rule
     worked as designed, but it retried the same feeds. Correct refusal, no made-up
     facts, but the user got nothing while the feed that covers Sudan was never queried.
     Same cost as F2 (AgentCore baseline).
F15. Foundry q5 ("India elections"): relevance failure again — answer included a Pakistani
     TV show cancelled in India and India-China border talks; neither is about state
     elections. Same pattern as F10b/F12: keyword passes, model presents what it gets.
F16. Foundry q6 (India Supreme Court): correct and on-topic (Anand Mohan release quashed,
     Umar Khalid/Sharjeel Imam bail notice, Thirupparankundram). Compare with Nova F10:
     the same question pulled in a US tariffs item there. That item is The Hindu
     INTERNATIONAL (see F19) — so it was not caused by adding Al Jazeera.
F17. Foundry q10 (climate): call 1 keyword "climate" -> nothing; retry used a DIFFERENT
     keyword "COP" (not the no-keyword fallback the retry rule describes), same 2 feeds.
     Retry behaviour is inconsistent: q2 dropped the keyword, q10 swapped it. Short acronym
     "COP" may not match "COP30"-style tokens in a whole-word filter. Answer: correct
     refusal ("no matching headlines on the climate talks"), nothing invented.

F18. Foundry baseline instructions name feeds in 3 places: the feed list + routing rules,
     and BOTH failure examples ("The Hindu national (timeout)", "BBC results may be
     incomplete"). The first draft of the schema_only edit removed the list but kept the
     failure examples -> feed names still leak through examples (cf. F3: examples do
     double duty). Fixed before the schema_only run.

F19. Foundry schema_only q6 (India Supreme Court), ~1h after baseline: SAME feeds (order
     differs) and SAME keyword as baseline, but the 3 Indian SC stories were gone; only the
     US tariffs item (The Hindu international) matched. So the change is in RETRIEVAL, not in
     the prompt. Likely causes: (a) hindu_national rotated the stories out of its RSS
     window, or (b) newer Indian SC items don't contain the word "India" — Indian domestic
     news rarely says "India", and the all-terms filter requires it. TODO: curl tools/call
     with keyword "Supreme Court" on hindu_national to tell (a) from (b).
     Good sign: unlike Nova (F10), gpt-5.6-luna said plainly the match was the US Supreme
     Court and that no Indian ruling was in the feeds. Still listed it as a bullet.
F20. Method: feeds are live, so ANSWERS are not comparable across conditions run hours
     apart; only the feed/keyword ARGUMENTS are. For answer-quality comparisons, run
     conditions back-to-back or replay a frozen snapshot (fixtures) through the tool.

F21. Follow-up to F19 ("Use hindu_national feeds"): hindu_national returned Indian SC items,
     incl. Thirupparankundram — a story the BASELINE q6 call also found with keyword
     "India Supreme Court". So the story did NOT rotate out, which rules out (a) for it. Yet
     the schema_only call with the same keyword and feeds missed it. Remaining explanations:
     the item's text changed (lost "India"), or hindu_national failed/was incomplete on that
     call and the model did not report it (FAILURES rule). TODO: keyword of this follow-up
     call + failed_feeds in the schema_only q6 tool output.

F22. Foundry schema_only is the cleanest routing of any model: AJ on all 4 "fits" questions
     and all 3 optional world questions, never on India questions (0/3), and it narrowed
     India questions instead of adding everything: RBI -> hindu_national only; elections ->
     hindu_national + bbc_world; Supreme Court -> national + both world-ish feeds.
     Contrast: Nova picks all 4 every time (F8), Qwen needed a format example (F3).
     So "every feed whose description fits" is read as routing by gpt-5.6-luna but as
     "include all" by Nova — same words, different models.
F23. Foundry q2 (Sudan) — clearest user-facing benefit: baseline (bbc + hindu_intl, plus a
     no-keyword retry) returned NOTHING on Sudan; schema_only returned 1 item, from
     aljazeera_all ("War and drought threaten livelihoods of Sudan's farmers", 26 Nov).
     Same model, same question, ~2h apart — only the feed choice changed.
     q10 (climate) schema_only: 0 items from all 3 feeds, failed_feeds empty, and NO retry
     call although the retry rule applies (baseline did retry). Retry compliance is
     inconsistent across runs (see F17).

F24. RESOLVES F19/F21. schema_only q6 tool output: failed_feeds = [] and 1 item (the US
     tariffs story, hindu_international). hindu_national was fetched fine and returned
     ZERO matches for "India Supreme Court", although it held Indian SC stories
     (Thirupparankundram, protests plea) — shown by the follow-up call.
     => Retrieval false negative from the all-terms keyword filter: domestic stories don't
     say "India". The only item containing all three words is the wrong one (US court +
     "India was also named"). The baseline match on the same story was likely an earlier
     version of its text. Not a feed failure, not a model failure.
     Possible fixes (to test, one at a time):
       - prompt: "for a country's own national feed, don't put that country in keyword"
       - server: per-feed implicit terms (hindu_national implies "India") that count as
         matched, or rank by term overlap instead of requiring all terms.

F25. Method — confound: each runtime uses a different model (Qwen 3B / Nova Pro /
     gpt-5.6-luna / gemini-3.8-flash), so results compare MODEL+RUNTIME pairs, not clouds.
     Runtimes also differ in how they pass tool schemas and results (e.g. E8). Frame the
     post as "how do different models read the same tool schema", not "AWS vs Azure".
     To isolate one factor: same model on two runtimes (e.g. a Claude model on both
     Bedrock and Foundry), or two models on one runtime. Hosted runs are n=1 per question.

F26. ADK gemini-3.8-flash baseline (local adk web): routing identical to Foundry baseline —
     bbc_world + hindu_international for world q, + hindu_national for all 3 India q,
     Al Jazeera 0/4. F1 (prompt beats schema) now holds on all 4 models.
F27. Gemini dropped "India" from the keyword on India questions: q5 "election", q6
     "Supreme Court" (Foundry used "India elections" / "India Supreme Court"). That sidesteps
     the all-terms false negative in F24 — but "Supreme Court" on bbc_world can also match
     the US court. Keyword style differs by model; worth a column in the write-up.

F28. ADK Gemini retries heavily and ignores "call get_feeds once more": Gaza 5 calls
     (Gaza -> ceasefire -> Hamas -> Israel -> talks), Sahel 2 (Mali), Sudan 2 (Africa),
     Lebanon 2 (Hezbollah). It searches SIDEWAYS (related entities) instead of broader,
     and never tries another feed — Al Jazeera, which covers all four, is never queried.
     Retry style per model: Foundry drop/swap/skip (F17/F23), Gemini entity-hopping.
     Q5 call 2 repeated call 1 exactly (wasted call); call 3 narrowed to hindu_national with
     no keyword. Q10 call 2 swapped "climate" for "COP" (same as Foundry, F17), same feeds.
F29. Strongest evidence for F24: Gemini q6 keyword "Supreme Court" (no "India") on the same
     feeds returned 3 Indian SC stories from hindu_national (FSSAI nutrition labelling,
     Thirupparankundram, protests plea). Foundry's "India Supreme Court" got 0 from that
     feed the same afternoon. Keyword over-specification, confirmed.
F30. ADK Gemini output format broke the prompt: bullets end with the feed ID and headline
     ("— hindu_national: <title>") instead of source name + markdown link. Feed IDs leak to
     the user, and NO links -> claims can't be checked by the reader. (q6, q8, q9.)
F31. ADK q8 (Ukraine): includes North Korea expelling a Swiss diplomat — tangential, but the
     source ties it to children from Russian-occupied Ukraine, so defensible. Rest on-topic.

F32. ADK Gemini schema_only (GCP playground, redeployed): AJ on first call for all 4 "fits"
     and all 3 optional q. India q: Supreme Court and RBI -> hindu_national ONLY; elections
     -> all 4 feeds (1 false pick). Between Foundry (precise) and Nova (all 4 always).
F33. Retries dropped sharply once the right feed was in the first call: Gaza 5 calls -> 2,
     Sudan 2 -> 1, Sahel/Lebanon still 2 (no matches anywhere). Total ADK calls: baseline
     21 -> schema_only 15. Better routing = fewer wasted tool calls (latency + cost).
F34. Sudan again the clearest win on a 2nd model: baseline nothing (Sudan, then Africa);
     schema_only answered from Al Jazeera on the first call.
F35. ADK output format partly fixed: bullets now end with "(BBC)", "(Al Jazeera)",
     "(The Hindu)" — no feed IDs (cf. F30) — but still NO markdown links, against the
     prompt. Links missing in both ADK conditions -> Gemini-specific, not prompt-specific.
F36. ADK q1 relevance drift: asked about ceasefire TALKS; retry "gaza" returned strikes and
     a celebrity (Ms Rachel) item, all presented as the answer. No item was about talks;
     the answer never said so. Same pattern as F15/F10b: what matches gets presented.
F37. q7 RBI: hindu_national only, then "economy" -> no headlines. Neither run reached any
     RBI item; feed set has no business/economy feed. Gap in the registry, not routing.

## Engineering / process issues

E1. SAM build on Windows failed: `mcp` depends on pywin32 (win32 marker); SAM resolved it
    for Linux. Fix: `sam build --use-container` (or `uv pip compile --python-platform
    x86_64-manylinux2014`). Consider `use_container = true` in samconfig.toml.
E2. PowerShell `sam build; sam deploy` deploys a STALE build when the build fails.
    Use `sam build ...; if ($?) { sam deploy }`.
E3. Docker Desktop engine not running -> "no docker runtime"; engine API 500 while starting.
E4. Eval script bugs (fixed): first_feeds stored the LAST call's feeds; CSV joined string
    feeds per character. Added `_as_list` + `feed_type` column.
E5. A schema_format run was mislabeled schema_only; 30 duplicate rows removed
    (backup: feed_choice.backup.csv).
E6. Model note: AgentCore runs used Nova Pro v1; the original article says Nova Lite.
E7. Schema change detail: FEED_PARAM_DESCRIPTION joined with "; " after sentences ending in
    "." -> ".;" — fixed to " ".
E8. Foundry passes BOTH tool result forms to the model: the text content block (JSON string)
    AND structuredResponse (structuredContent) — every get_feeds result is sent twice,
    ~2x tool-output tokens. Source: FastMCP returns content + structuredContent for typed
    returns. Check whether other runtimes do the same; option: return only one form.
E9. Local ADK web on Windows: port 8000 already taken by vLLM (WSL forwards it) ->
    WinError 10048; port 8080 -> WinError 10013 (not in excluded ranges, likely another
    service holding it). Used `adk web --port 8765`. ADK project itself was fine: MCP_URL
    ends in /mcp, streamable HTTP, x-api-key header, Vertex auth via .env.
E10. ADK local, gemini-3.8-flash, baseline q1 (Gaza): MCP connection works (the model got
    the tool) but the turn ended with errorCode MALFORMED_FUNCTION_CALL, errorMessage
    undefined — Gemini produced a get_feeds call that did not parse/validate. Possibly the
    same failure seen in GCP (reported there as "can't connect"). Did NOT recur: the retry
    in a new session worked, and no later baseline question hit it (1 failure in ~11 turns).
    Treat as transient Gemini output error; ADK has no automatic retry for it -> a
    production agent needs one.
E11. ADK runtime record: only the first local attempt (MALFORMED_FUNCTION_CALL, E10) ran on
    local `adk web`. The ADK baseline q1-q10 ran in the GCP Agent Engine playground, so the
    deployed agent DID reach the MCP server. schema_only must also run there (redeploy).
F24b. Correction to F24/F29 framing ("keyword, not model"): three factors combined —
     (1) model keyword choice (gpt-5.6-luna added "India", Gemini did not), (2) the server's
     all-terms filter, (3) model feed choice (the US item came via hindu_international;
     Gemini schema_only asked hindu_national alone). Plus feed text drift: Foundry baseline
     found Indian SC items with the same "India Supreme Court" keyword hours earlier.
     Write-up and carousel reworded: "A strict filter met a reasonable keyword."

## Round 3 — schema_examples (27 Nov 2026)
Prompted by a LinkedIn comment (Louis Philip): keep the schema as the single source; put an
array example in the schema and test with no prompt examples of the feed format.
Server change: feed Field gains examples=[["hindu_national","hindu_international"]]
(no aljazeera_all, so the example cannot nudge the Al Jazeera questions). Test added
(examples use real feed names); 70 tests pass. Deployed; tools/list confirms
"examples":[["hindu_national","hindu_international"]] under inputSchema.properties.feed.
Prompts: vLLM back to schema_only wording (no feed: ["<feed>", "<feed>"]); hosted prompts
unchanged from schema_only (they never had a feed-format example).
Per runtime, also record whether "examples" reaches the model (pass-through).
R3-1. vLLM/Qwen schema_examples (12:01-12:03, prompt with NO feed example): 30/30 lists,
     AJ 12/12 on fits, 0/9 on India q, no invented feeds. MLflow check: the ChatOpenAI span's
     invocation_params carry "examples":[["hindu_national","hindu_international"]] under feed,
     so LangChain passed the schema example through to vLLM.
     Caveat: the example may steer as well as teach — hindu_national appears on Ukraine (q8) and
     US-China (q9); q5/q6 went to hindu_national for the first time (example or descriptions,
     can't separate). q7 RBI still hindu_international. q5/q6 sent no keyword.
R3-2. An earlier run at 11:58-12:01 still had the prompt's feed: ["<feed>", "<feed>"] example
     (confirmed in MLflow) — i.e. prompt example + schema example. Relabelled those 33 rows
     condition=schema_format_examples (backup: feed_choice.backup2.csv). It differs from the
     clean run on Sahel (bbc_world only), Lebanon (no keyword) and US-China (AJ only).
R3-3. ADK pass-through CONFIRMED (local adk web, Request view, Gaza q1): the get_feeds
     declaration sent to gemini-3.8-flash carries "examples":[["hindu_national","hindu_international"]]
     under parameters.properties.feed, beside the enum and min/maxItems. ADK sends the raw
     JSON schema, so nothing was stripped.
     Side finding: ADK 2.15 wraps every tool and parameter description in
     <<<BEGIN/END_UNTRUSTED_TOOL_DESCRIPTION>>> markers and appends a system-instruction line
     saying tool descriptions are data, not instructions — built-in prompt-injection hygiene
     for MCP servers. Our routing still works through it, since the descriptions inform
     rather than instruct.
     ADK schema_examples runs are LOCAL adk web (schema_only ran in the GCP playground):
     same agent code, prompt and model; runtime host differs.
R3-4. ADK MALFORMED_FUNCTION_CALL explained: the failed Sudan request had 444 prompt tokens vs
     ~1,710 for every successful first call — the get_feeds declaration (~1,270 tokens) was
     missing. ADK sent no tools (tool list not loaded for that new session), the prompt still
     said "call get_feeds", Gemini emitted a call to an undeclared function -> MALFORMED.
     Retry in a new session: 1,708 tokens, normal. Likely the same cause as E10 (also a first
     turn). Runtime failure, excluded from picks. Fix idea: fail loudly when the MCP toolset
     returns no tools instead of calling the model without them.
R3-5. ADK schema_examples (local): AJ 4/4 on fits (first call), 0/3 on India q — all three
     India questions went to hindu_national ALONE (schema_only: elections took all 4 feeds),
     3/3 optional. Unlike Qwen, Gemini never added the example's feeds to world questions:
     no steering visible. 15 tool calls (same as schema_only). Sahel: retry "Africa" returned
     a BBC item and the model declined it as off-topic — good relevance. Sudan: Al Jazeera
     queried but its Sudan story had rotated out; correct "no headlines". Answers carried
     markdown links (Gaza) — earlier ADK runs dropped them.
R3-6. AgentCore Nova Pro schema_examples (Harness playground, schema_only system prompt confirmed
     in Configs): in fresh sessions Gaza went to bbc_world + hindu_international + hindu_national
     — the three OLD feeds, Al Jazeera dropped. schema_only sent all 4 every time. Nova's
     reasoning lists all four feeds (tool list current, not stale). Picks made inside one long
     session were discarded (carry-over from earlier turns). Working hypothesis: the example
     (hindu_national, hindu_international) pulled Nova back toward the Hindu feeds + BBC.
     Prompt says "once per question", so no retry after 0 items.
R3-7. AgentCore Nova Pro schema_examples, 10 fresh sessions: AJ 3/4 on fits (Sudan went to
     bbc+hindu_intl+hindu_national), 1/3 on India q (RBI took all 4), 3/3 optional. Nova no
     longer sends all four feeds everywhere: 3 feeds on most world q, 1-2 on India q.
     REVISES R3-6 (fully withdrawn): the Gaza probe that dropped AJ ran on the OLD baseline
     prompt — the Harness playground resets the system prompt to the saved (baseline) config
     on every New session (see E12). With the schema_only prompt pasted into each session,
     Gaza picked AJ. No evidence of example steering on Nova; weak signal only:
     hindu_national (an example feed) appeared on Sudan.
R3-8. Nova returned nothing on 7 of 10 questions: multi-word keywords ("Gaza ceasefire",
     "US China trade", "climate talks", "Indian state elections", "India Supreme Court",
     "RBI India economy") hit the all-terms filter, and the prompt's "once per question"
     forbids a retry. Gemini under the same filter retried and recovered (Gaza -> "Gaza").
     Keyword style + retry policy matter as much as routing for whether the reader gets news.
E12. AgentCore Harness playground: a system-prompt edit in Configs applies only to the current
    session; every New session falls back to the harness's saved prompt, which is still the
    BASELINE (three named feeds). Each schema_examples question was run with the schema_only
    prompt pasted in by hand. Consequences: (a) any session without the paste silently runs
    the old prompt — it explains the R3-6 probe; (b) the agent's saved/deployed config —
    what any other caller gets — is still the baseline prompt. Fix: save the schema_only
    prompt to the harness/agent configuration (or redeploy), then re-check with a fresh
    session.
E13. CONFOUND in AgentCore rounds 1-2: baseline and schema_only were each run as all ten
    questions in ONE session (confirmed by Raj). Nova saw its earlier calls, so "all 4 feeds
    every time" (F8) and "3 old feeds every time" may be carry-over, not per-question
    choice. Round 3 used fresh sessions, so AgentCore schema_only vs schema_examples is NOT
    comparable. Action: rerun AgentCore schema_only (and ideally baseline) in fresh sessions,
    prompt pasted per session. The published write-up's Nova claims ("all four feeds every
    time", false picks 3/3) rest on the one-session run and may need a correction.
    Same applies to FOUNDRY and ADK rounds 1-2 (ADK ran in the GCP Vertex Agent Studio
    playground, also one session; confirmed by Raj). Only vLLM ran a fresh invocation per
    question. Mitigation: Q1 (Gaza) is first in every session, so its pick has no carry-over —
    in schema_only all three hosted models picked AJ on Q1, and in baseline none did.
    Round 3 (fresh sessions, verified for ADK via distinct session ids in session.db)
    reproduces the schema effect: Gemini 4/4, Nova 3/4 on fits. Decision (27 Nov): no
    reruns of rounds 1-2 (cost); Round 3 uses fresh sessions everywhere.

R3-9. Side note (1 question, not in Round 3 numbers): AgentCore Nova Pro with FOUNDRY's prompt
     pasted in, Gaza q1, fresh session -> items from aljazeera_all, bbc_world and
     hindu_international; with its own AgentCore prompt the same question returned 0 items.
     Consistent with R3-8: Foundry's keyword rule ("only the essential names... every extra
     word narrows the results") plus an allowed retry, versus AgentCore's "one to three topic
     words" and "once per question". Keyword guidance, not routing, decided whether the reader
     got news.
R3-10. Same prompt (Foundry's), same question (Gaza), same four items retrieved on both
     runtimes — so differences are the model's alone:
     - Relevance: gpt-5.6-luna opens with "no new developments in ceasefire talks"; Nova
       puts that caveat last.
     - Faithfulness: Nova's closing "Context" claims "significant casualties on both sides" —
       every item reports Palestinian deaths only; and "the situation suggests a high level of
       tension and hostility" is its own inference. gpt-5.6-luna adds nothing beyond items.
     - Attribution: Nova states "Israel killed nine people" as fact (source headline: "...
       officials say"); gpt-5.6-luna writes "The Hindu reports that..." on every bullet.
     Cleanest grounding evidence in the experiment: identical prompt and evidence, the model
     alone introduced an unsupported claim.
R3-11. Foundry gpt-5.6-luna schema_examples, new chat per question (first clean Foundry
     data): AJ 4/4 on fits, 1/3 on India q (Supreme Court took hindu_national+bbc+AJ),
     3/3 optional; 15 tool calls (retries on Gaza, Sudan, Sahel, RBI, climate — this time
     following the rule: drop or broaden the keyword). Keyword on q6 was "Supreme Court"
     (no "India") and returned four Indian rulings — the F24 miss did not recur.
     Q4 answered from one Al Jazeera item found by the "Mali" retry.

### Round 3 summary (schema example, no prompt format example, fresh sessions everywhere)
| Model / runtime | AJ when it fits | AJ on India q | Calls | Example reached model? |
|---|---|---|---|---|
| Qwen2.5-3B / vLLM | 12/12 | 0/9 | 33 / 30 runs | yes (MLflow) |
| gemini-3.8-flash / ADK (local) | 4/4 | 0/3 | 15 | yes (ADK request view) |
| gpt-5.6-luna / Foundry | 4/4 | 1/3 | 15 | not checked |
| Nova Pro / AgentCore | 3/4 | 1/3 | 10 (no retries allowed) | not checked |
- The schema example fixed Qwen's format without a prompt example (30/30 lists, no invented
  feeds) — the prompt can be cleaned without breaking calls, as Louis suggested.
- Steering by the example was visible only in the small model (hindu_national on world q).
- With fresh sessions, the hosted models picked AJ on 11 of 12 fitting questions.
- Whether the reader got news depended more on keyword style and retry policy than on
  routing (R3-8, R3-9); with identical evidence, the models still differed on
  faithfulness (R3-10).
