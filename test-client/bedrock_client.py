#!/usr/bin/env python3
"""
Bedrock Cost Keeper Test Client

This client demonstrates the complete workflow:
1. Authenticate via OAuth2 client_credentials flow
2. Get model selection recommendation
3. Invoke AWS Bedrock with the recommended model
4. Calculate costs from token usage
5. Submit cost data back to the service
6. Verify aggregation
"""

import json
import os
import sys
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone

import boto3
import requests
from botocore.exceptions import ClientError


class BedrockCostKeeperClient:
    """Client for interacting with Bedrock Cost Keeper service"""

    def __init__(self, config_file: str = 'config.json'):
        """Initialize the client with configuration"""
        with open(config_file, 'r') as f:
            self.config = json.load(f)

        self.service_url = self.config['service_url'].rstrip('/')
        self.client_id = self.config['client_id']
        self.client_secret = self.config['client_secret']
        self.org_id = self.config['org_id']
        self.app_id = self.config['app_id']
        self.aws_region = self.config.get('aws_region', 'us-east-1')

        self.access_token: Optional[str] = None
        self.token_expiry: Optional[float] = None

        # Initialize Bedrock client
        self.bedrock_runtime = boto3.client(
            'bedrock-runtime',
            region_name=self.aws_region
        )

    def authenticate(self) -> str:
        """Authenticate and get JWT access token"""
        print("[INFO] Authenticating with Bedrock Cost Keeper...")

        response = requests.post(
            f'{self.service_url}/token',
            data={
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        if response.status_code != 200:
            raise Exception(f"Authentication failed: {response.text}")

        data = response.json()
        self.access_token = data['access_token']
        self.token_expiry = time.time() + data['expires_in']

        print(f"[INFO] Authenticated successfully. Token expires in {data['expires_in']} seconds")
        return self.access_token

    def ensure_authenticated(self):
        """Ensure we have a valid access token"""
        if not self.access_token or time.time() >= self.token_expiry - 60:
            self.authenticate()

    def get_headers(self) -> Dict[str, str]:
        """Get HTTP headers with authentication"""
        self.ensure_authenticated()
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

    def get_model_selection(self) -> Dict[str, Any]:
        """Get recommended model based on quotas"""
        print("[INFO] Getting model selection recommendation...")

        response = requests.get(
            f'{self.service_url}/model-selection',
            headers=self.get_headers()
        )

        if response.status_code != 200:
            raise Exception(f"Model selection failed: {response.text}")

        data = response.json()
        print(f"[INFO] Recommended model: {data['model_label']}")
        print(f"[INFO] Model ID: {data['model_id']}")

        return data

    def invoke_bedrock(self, model_id: str, messages: list) -> Dict[str, Any]:
        """Invoke AWS Bedrock with the specified model"""
        print(f"[INFO] Invoking Bedrock model: {model_id}")

        try:
            response = self.bedrock_runtime.converse(
                modelId=model_id,
                messages=messages,
                inferenceConfig={
                    'maxTokens': 512,
                    'temperature': 0.7
                }
            )

            print("[INFO] Bedrock invocation successful")
            return response

        except ClientError as e:
            print(f"[ERROR] Bedrock invocation failed: {e}")
            raise

    def submit_usage(
        self,
        request_id: str,
        model_label: str,
        bedrock_model_id: str,
        input_tokens: int,
        output_tokens: int,
        status: str = 'OK'
    ) -> Dict[str, Any]:
        """Submit usage data to the service (service calculates cost from tokens)"""
        print(f"[INFO] Submitting usage data for request {request_id}...")
        print(f"[INFO] Input tokens: {input_tokens}, Output tokens: {output_tokens}")

        payload = {
            'request_id': request_id,
            'model_label': model_label,
            'bedrock_model_id': bedrock_model_id,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'status': status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        response = requests.post(
            f'{self.service_url}/orgs/{self.org_id}/apps/{self.app_id}/usage',
            headers=self.get_headers(),
            json=payload
        )

        if response.status_code != 202:
            raise Exception(f"Usage submission failed: {response.text}")

        result = response.json()

        # Extract and display server-calculated cost
        calculated_cost = result.get('processing', {}).get('cost_usd_micros', 0)
        print(f"[INFO] Service calculated cost: ${calculated_cost / 1_000_000:.6f} ({calculated_cost} USD micros)")
        print("[INFO] Usage submitted successfully")

        return result

    def get_aggregates(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Get usage aggregates"""
        if date is None:
            date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        print(f"[INFO] Getting aggregates for date: {date}")

        response = requests.get(
            f'{self.service_url}/aggregates',
            headers=self.get_headers(),
            params={'date': date}
        )

        if response.status_code != 200:
            raise Exception(f"Get aggregates failed: {response.text}")

        data = response.json()
        print(f"[INFO] Total cost today: ${data['total_cost_usd']:.6f}")
        print(f"[INFO] Total requests: {data['total_requests']}")

        return data

    def run_inference_loop(self, count: int = 5):
        """Run multiple inference requests and track costs"""
        print(f"\n{'='*60}")
        print(f"Running {count} inference requests")
        print(f"{'='*60}\n")

        total_cost = 0
        successful_requests = 0

        for i in range(count):
            print(f"\n--- Request {i+1}/{count} ---")

            try:
                # Get model selection
                model_selection = self.get_model_selection()
                model_id = model_selection['model_id']
                model_label = model_selection['model_label']
                pricing = model_selection['pricing']

                # Prepare message
                messages = [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'text': self.config.get(
                                    'test_prompt',
                                    'What is the capital of France? Respond in one sentence.'
                                )
                            }
                        ]
                    }
                ]

                # Invoke Bedrock
                bedrock_response = self.invoke_bedrock(model_id, messages)

                # Extract usage and response
                usage = bedrock_response['usage']
                response_text = bedrock_response['output']['message']['content'][0]['text']
                request_id = bedrock_response['ResponseMetadata']['RequestId']

                print(f"[INFO] Response: {response_text[:100]}...")

                # Submit usage (service calculates cost)
                submission_result = self.submit_usage(
                    request_id,
                    model_label,
                    model_id,
                    usage['inputTokens'],
                    usage['outputTokens']
                )

                # Extract service-calculated cost for tracking
                cost_usd_micros = submission_result.get('processing', {}).get('cost_usd_micros', 0)
                total_cost += cost_usd_micros
                successful_requests += 1

                # Small delay between requests
                time.sleep(0.5)

            except Exception as e:
                print(f"[ERROR] Request failed: {e}")
                continue

        # Get final aggregates
        print(f"\n{'='*60}")
        print("Final Summary")
        print(f"{'='*60}")
        print(f"Successful requests: {successful_requests}/{count}")
        print(f"Total cost (calculated): ${total_cost / 1_000_000:.6f}")

        # Verify with service
        print("\nVerifying with service...")
        time.sleep(2)  # Wait for aggregation to complete
        aggregates = self.get_aggregates()

        print(f"\n{'='*60}")
        print("Service Aggregates")
        print(f"{'='*60}")
        print(json.dumps(aggregates, indent=2))


def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == '--config':
        config_file = sys.argv[2] if len(sys.argv) > 2 else 'config.json'
    else:
        config_file = 'config.json'

    if not os.path.exists(config_file):
        print(f"[ERROR] Configuration file not found: {config_file}")
        print("Please create config.json with your credentials")
        sys.exit(1)

    try:
        client = BedrockCostKeeperClient(config_file)
        client.run_inference_loop(count=5)
        print("\n[INFO] Test completed successfully!")

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
