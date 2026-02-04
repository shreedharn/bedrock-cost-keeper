"""AWS Secrets Manager utilities."""

import boto3
import json
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def get_secret(secret_name: str, region_name: str = "us-east-1") -> Optional[str]:
    """
    Retrieve a secret from AWS Secrets Manager.

    Args:
        secret_name: Name of the secret in Secrets Manager
        region_name: AWS region where the secret is stored

    Returns:
        The secret value as a string, or None if retrieval fails
    """
    try:
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name
        )

        response = client.get_secret_value(SecretId=secret_name)

        # Secrets can be stored as either string or binary
        if 'SecretString' in response:
            secret = response['SecretString']
            # Try to parse as JSON in case it's a JSON secret
            try:
                secret_dict = json.loads(secret)
                # If it's a JSON object with a single key, return that value
                if isinstance(secret_dict, dict) and len(secret_dict) == 1:
                    return list(secret_dict.values())[0]
                return secret
            except json.JSONDecodeError:
                return secret
        else:
            # Binary secret
            return response['SecretBinary'].decode('utf-8')

    except Exception as e:
        logger.error(f"Failed to retrieve secret '{secret_name}': {e}")
        return None
