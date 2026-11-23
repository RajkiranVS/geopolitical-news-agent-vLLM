'''
An helper function that uses langchain's MultiServerMCPClient to call MCPServer running as AWS Lambda Function and get the 
feeds from the allowlisted RSS Feed Sources using the get_feed tool

Method:
get_geopolitical_feeds: A method that extract the feeds along with the sources[used for citation]

Args:
    - api_key: to send x_api_key in header to authenticate - fetched using src.fetch_api_key.get_api_key_from_secrets
    - lambda_url: The URL of the AWS Lambda MCP Server
    - feed: the representation strings of allowlisted RSS-Feed URLs
    - keyword: sent by the model - extracted from user query
    - limit: number of articles to extract
'''
from langchain_mcp_adapters.client import MultiServerMCPClient
from typing import List

async def get_geopolitical_feeds(api_key: str, lambda_url: str):
    """
    Connect to MCP server via MultiServerMCPClient and call 'get_feeds'.
    """
    client = MultiServerMCPClient({
        "geopolitical_feeds_mcp": {
            "transport": "streamable_http",
            "url": lambda_url,
            "headers": {"x-api-key": api_key},
        }
    })

    tools = await client.get_tools(server_name="geopolitical_feeds_mcp")
    return tools
   