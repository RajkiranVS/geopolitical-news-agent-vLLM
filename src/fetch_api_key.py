'''
A helper function to fetch the Lambda MCP Server API Key from the AWS Secrets Manager

Methos:
get_api_key_from_secrets:
 Args:
  - secret_name: AWS Secret Manager SECRET_ID
  - region_name: Region in which this secret manager reisdes

Returns:
 - api_key as plain text

'''
import os
import json
import boto3
from botocore.exceptions import ClientError

def get_api_key_from_secrets(secret_name: str, region_name: str) -> str:
    """
    Retrieve API key from AWS Secrets Manager.
    The secret should contain JSON like: {"api_key": "YOUR_KEY"}
    """
    client = boto3.client("secretsmanager", region_name=region_name)
    try:
        response = client.get_secret_value(SecretId=secret_name)
        if "SecretString" in response:
            secret_data = json.loads(response["SecretString"])
            api_key = secret_data.get("api_key")
            if not api_key:
                raise ValueError("Secret JSON does not contain 'api_key'.")
            return api_key
        else:
            raise ValueError("SecretString not found in AWS Secrets Manager response.")
    except ClientError as e:
        raise RuntimeError(f"Failed to retrieve secret: {e}")

if __name__ == "__main__":
    api_key = get_api_key_from_secrets(secret_name=os.environ['secrets_id'], region_name=os.environ['aws_region'])
    print(api_key)