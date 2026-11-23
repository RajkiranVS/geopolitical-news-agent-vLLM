# agent.py
import os
import asyncio
from pathlib import Path

import mlflow
from pydantic import SecretStr
from langchain_openai import ChatOpenAI

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from src.fetch_api_key import get_api_key_from_secrets
from src.feeds import get_geopolitical_feeds

AWS_REGION = os.environ['aws_region']
AWS_SECRET_NAME = os.environ['secrets_id']
AWS_LAMBDA_MCP_URL = os.environ['mcp_url']

SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.md").read_text(encoding="utf-8").strip()
if not SYSTEM_PROMPT:
    raise RuntimeError("system_prompt.md is empty")

# MLflow tracing: every LLM call, tool call and agent step is logged as a span.
mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT", "geopolitical-agent"))
mlflow.langchain.autolog()

async def main():
    api_key = get_api_key_from_secrets(secret_name=AWS_SECRET_NAME, region_name=AWS_REGION)
    tools = await get_geopolitical_feeds(api_key=api_key, lambda_url=AWS_LAMBDA_MCP_URL)

    # Step 1: Create agent with vLLM-backed ChatOpenAI
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        api_key=SecretStr("EMPTY"),  # vLLM doesn't require real key
        model="Qwen/Qwen2.5-3B-Instruct-AWQ",
        temperature=0.0,
        max_completion_tokens=800
    )
    agent = create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)

    # Defined here so `query` is the only traced input; the agent comes from the closure
    # (otherwise MLflow shows the agent's memory address in the trace title).
    @mlflow.trace(name="geopolitical_agent", span_type="AGENT")
    async def run_query(query: str) -> str:
        # Cap the loop. The prompt's empty-result retry is agent -> tools -> agent -> tools -> agent
        # (5 steps), so 6 lets that finish with one step of headroom. Each tool result is ~1.5k
        # tokens; extra rounds would overflow the 4,096-token context.
        # TODO: replace with proper middleware or a custom StateGraph.
        try:
            response = await agent.ainvoke(
                {"messages": [HumanMessage(content=query)]},
                config={"recursion_limit": 6},
            )
        except GraphRecursionError:
            return ("Sorry, I couldn't finish this briefing within the step limit. "
                    "Try a more specific question.")
        return response["messages"][-1].content

    # Step 2: Run agent query (async)
    query = input("Ask me anything about any geopolitical updates: ")
    answer = await run_query(query)

    print("Agent Response:", answer)

if __name__ == "__main__":
    asyncio.run(main())
