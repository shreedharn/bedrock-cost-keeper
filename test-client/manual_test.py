#!/usr/bin/env python3
"""
Manual API Test Script for Bedrock Cost Keeper

Tests APIs one at a time with manual pauses for debugging.
Run: python manual_test.py
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional
import boto3
import requests
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Confirm
from rich.table import Table

console = Console()


class ManualTester:
    """Interactive manual test runner"""

    def __init__(self, config_file: str = 'manual_test_config.json'):
        # Load config
        if not os.path.exists(config_file):
            console.print(f"[red]Error: Config file not found: {config_file}[/red]")
            sys.exit(1)

        with open(config_file) as f:
            self.config = json.load(f)

        self.service_url = self.config['service_url']
        self.aws_profile = self.config.get('aws_profile', 'default')
        self.aws_region = self.config.get('aws_region', 'us-east-1')

        # HTTP timeout (set high for debugging)
        self.http_timeout = self.config.get('http_timeout', 300)  # 5 minutes default

        # Setup AWS clients
        try:
            session = boto3.Session(profile_name=self.aws_profile)
            self.bedrock_runtime = session.client('bedrock-runtime', region_name=self.aws_region)
            self.secrets_manager = session.client('secretsmanager', region_name=self.aws_region)
        except Exception as e:
            console.print(f"[red]Error setting up AWS clients: {e}[/red]")
            console.print("[yellow]Make sure AWS credentials are configured[/yellow]")
            sys.exit(1)

        # Test state
        self.access_token = None
        self.org_id = None
        self.app_id = self.config['test_app_id']
        self.client_id = None
        self.client_secret = None
        self.inference_profile_arn = self.config.get('inference_profile_arn')
        self.model_id = self.config.get('model_id')
        self.selected_model = None
        self.invocation_result = None

        # Logging
        self.log_file = f"logs/manual_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        os.makedirs('logs', exist_ok=True)

    def log(self, message: str, level: str = 'INFO'):
        """Log to console and file"""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level}] {message}"

        # Console (colored)
        if level == 'ERROR':
            console.print(f"[red]{message}[/red]")
        elif level == 'SUCCESS':
            console.print(f"[green]{message}[/green]")
        elif level == 'WARNING':
            console.print(f"[yellow]{message}[/yellow]")
        else:
            console.print(message)

        # File
        with open(self.log_file, 'a') as f:
            f.write(log_entry + '\n')

    def pause(self, message: str = "Press Enter to continue..."):
        """Pause execution and wait for user"""
        console.print(f"\n[yellow]{message}[/yellow]")
        input()

    def show_request(self, method: str, url: str, headers: Dict, body: Optional[Dict] = None):
        """Display request details"""
        console.print(Panel("[bold cyan]REQUEST[/bold cyan]", expand=False))
        console.print(f"[bold]Method:[/bold] {method}")
        console.print(f"[bold]URL:[/bold] {url}")

        # Mask sensitive headers
        display_headers = headers.copy()
        if 'X-API-Key' in display_headers:
            display_headers['X-API-Key'] = '***REDACTED***'
        if 'Authorization' in display_headers:
            display_headers['Authorization'] = f"Bearer ***REDACTED***"

        console.print(f"[bold]Headers:[/bold]")
        console.print(Syntax(json.dumps(display_headers, indent=2), "json"))

        if body:
            console.print(f"[bold]Body:[/bold]")
            console.print(Syntax(json.dumps(body, indent=2), "json"))

    def show_response(self, response: requests.Response):
        """Display response details"""
        console.print(Panel("[bold magenta]RESPONSE[/bold magenta]", expand=False))

        # Color code status
        if 200 <= response.status_code < 300:
            status_color = "green"
        elif 400 <= response.status_code < 500:
            status_color = "yellow"
        else:
            status_color = "red"

        console.print(f"[bold]Status:[/bold] [{status_color}]{response.status_code}[/{status_color}]")

        console.print(f"[bold]Body:[/bold]")
        try:
            json_body = response.json()
            console.print(Syntax(json.dumps(json_body, indent=2), "json"))
        except:
            console.print(response.text)

    def test_step_1_create_org(self) -> bool:
        """Step 1: Create sample-org"""
        console.print(Panel("[bold]Step 1: Create Organization (sample-org)[/bold]"))

        # Get provisioning API key from Secrets Manager
        self.log("Fetching provisioning API key from Secrets Manager...")
        try:
            secret_name = self.config['provisioning_api_key_secret_name']
            response = self.secrets_manager.get_secret_value(SecretId=secret_name)
            provisioning_api_key = response['SecretString']
            self.log("✓ Provisioning API key retrieved", 'SUCCESS')
        except Exception as e:
            self.log(f"✗ Failed to get provisioning API key: {e}", 'ERROR')
            return False

        # Generate org_id if not already set
        if not self.org_id:
            self.org_id = str(uuid.uuid4())

        # Prepare request
        url = f"{self.service_url}/api/v1/orgs/{self.org_id}"
        headers = {
            "X-API-Key": provisioning_api_key,
            "Content-Type": "application/json"
        }
        body = {
            "org_name": self.config['test_org_name'],
            "timezone": self.config['test_org_timezone'],
            "quota_scope": "APP",
            "model_ordering": self.config['model_ordering'],
            "quotas": self.config['quotas']
        }

        self.show_request("PUT", url, headers, body)

        # Execute
        try:
            response = requests.put(url, headers=headers, json=body, timeout=self.http_timeout)
            self.show_response(response)

            if response.status_code in [200, 201]:
                data = response.json()
                self.org_id = data['org_id']
                self.client_id = data['credentials']['client_id']
                self.client_secret = data['credentials']['client_secret']

                self.log(f"✓ Organization created: {self.org_id}", 'SUCCESS')
                self.log(f"✓ Client ID: {self.client_id}", 'SUCCESS')
                console.print(f"\n[bold green]Client Secret (SAVE THIS!):[/bold green] {self.client_secret}")
            else:
                self.log(f"✗ Failed to create organization: {response.status_code}", 'ERROR')
                return False
        except Exception as e:
            self.log(f"✗ Request failed: {e}", 'ERROR')
            return False

        self.pause("Review the response above. Press Enter to continue...")
        return True

    def test_step_2_create_app(self) -> bool:
        """Step 2: Create sample-app"""
        console.print(Panel("[bold]Step 2: Create Application (sample-app)[/bold]"))

        if not self.org_id:
            self.log("✗ Organization ID not available. Run step 1 first.", 'ERROR')
            return False

        # Get provisioning API key
        try:
            secret_name = self.config['provisioning_api_key_secret_name']
            response = self.secrets_manager.get_secret_value(SecretId=secret_name)
            provisioning_api_key = response['SecretString']
        except Exception as e:
            self.log(f"✗ Failed to get provisioning API key: {e}", 'ERROR')
            return False

        # Prepare request
        app_id = self.config['test_app_id']
        url = f"{self.service_url}/api/v1/orgs/{self.org_id}/apps/{app_id}"
        headers = {
            "X-API-Key": provisioning_api_key,
            "Content-Type": "application/json"
        }
        body = {
            "app_name": self.config['test_app_name']
        }

        self.show_request("PUT", url, headers, body)
        self.pause()

        # Execute
        try:
            response = requests.put(url, headers=headers, json=body, timeout=self.http_timeout)
            self.show_response(response)

            if response.status_code in [200, 201]:
                data = response.json()

                # Extract app credentials if this is a new app creation
                if 'credentials' in data:
                    # Replace org credentials with app credentials
                    self.client_id = data['credentials']['client_id']
                    self.client_secret = data['credentials']['client_secret']

                    self.log(f"✓ Application created: {app_id}", 'SUCCESS')
                    self.log(f"✓ App Client ID: {self.client_id}", 'SUCCESS')
                    console.print(f"\n[bold green]App Client Secret (SAVE THIS!):[/bold green] {self.client_secret}")
                    console.print(f"[bold yellow]Note:[/bold yellow] App credentials replace org credentials for authentication")
                else:
                    # This is an update, credentials not returned
                    self.log(f"✓ Application updated: {app_id}", 'SUCCESS')
            else:
                self.log(f"✗ Failed to create application: {response.status_code}", 'ERROR')
                return False
        except Exception as e:
            self.log(f"✗ Request failed: {e}", 'ERROR')
            return False

        self.pause("Review the response above. Press Enter to continue...")
        return True

    def test_step_3_authenticate(self) -> bool:
        """Step 3: Authenticate and get JWT token"""
        console.print(Panel("[bold]Step 3: Authenticate (Get JWT Token)[/bold]"))

        if not self.client_id or not self.client_secret:
            self.log("✗ Client credentials not available. Run steps 1-2 first.", 'ERROR')
            return False

        # Prepare request - using APP credentials from Step 2
        self.log(f"Using app credentials: {self.client_id}", 'INFO')
        url = f"{self.service_url}/auth/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,  # App client_id from Step 2
            "client_secret": self.client_secret  # App client_secret from Step 2
        }

        console.print(Panel("[bold cyan]REQUEST[/bold cyan]", expand=False))
        console.print(f"[bold]Method:[/bold] POST")
        console.print(f"[bold]URL:[/bold] {url}")
        console.print(f"[bold]Headers:[/bold]")
        console.print(Syntax(json.dumps(headers, indent=2), "json"))
        console.print(f"[bold]Form Data:[/bold]")
        console.print(f"  grant_type: {data['grant_type']}")
        console.print(f"  client_id: {self.client_id}")
        console.print(f"  client_secret: ***REDACTED***")

        self.pause()

        # Execute
        try:
            response = requests.post(url, headers=headers, data=data, timeout=self.http_timeout)
            self.show_response(response)

            if response.status_code == 200:
                data = response.json()
                self.access_token = data['access_token']
                self.log(f"✓ Authentication successful", 'SUCCESS')
                console.print(f"\n[bold green]Access Token (first 20 chars):[/bold green] {self.access_token[:20]}...")
            else:
                self.log(f"✗ Authentication failed: {response.status_code}", 'ERROR')
                return False
        except Exception as e:
            self.log(f"✗ Request failed: {e}", 'ERROR')
            return False

        self.pause("Review the response above. Press Enter to continue...")
        return True

    def test_step_4_register_inference_profile(self) -> bool:
        """Step 4: Register Application Inference Profile"""
        console.print(Panel("[bold]Step 4: Register Inference Profile[/bold]"))

        if not self.access_token:
            self.log("✗ Access token not available. Run step 3 first.", 'ERROR')
            return False

        url = f"{self.service_url}/orgs/{self.org_id}/apps/{self.app_id}/inference-profiles"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        body = {
            "profile_label": self.config['profile_label'],
            "inference_profile_arn": self.inference_profile_arn,
            "description": f"Amazon Nova Lite for {self.app_id}"
        }

        self.show_request("POST", url, headers, body)
        self.pause()

        try:
            response = requests.post(url, headers=headers, json=body, timeout=self.http_timeout)
            self.show_response(response)

            if response.status_code == 201:
                self.log("✓ Inference profile registered", 'SUCCESS')
            else:
                self.log(f"✗ Failed to register inference profile: {response.status_code}", 'ERROR')
                return False
        except Exception as e:
            self.log(f"✗ Request failed: {e}", 'ERROR')
            return False

        self.pause("Review the inference profile registration. Press Enter to continue...")
        return True

    def test_step_5_get_model_selection(self) -> bool:
        """Step 5: Get Model Selection"""
        console.print(Panel("[bold]Step 5: Get Model Selection[/bold]"))

        if not self.access_token:
            self.log("✗ Access token not available. Run step 3 first.", 'ERROR')
            return False

        url = f"{self.service_url}/orgs/{self.org_id}/apps/{self.app_id}/model-selection"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {
            "model_id": self.model_id,
            "input_tokens": 100,
            "output_tokens": 500
        }

        console.print(Panel("[bold cyan]REQUEST[/bold cyan]", expand=False))
        console.print(f"[bold]Method:[/bold] GET")
        console.print(f"[bold]URL:[/bold] {url}")
        console.print(f"[bold]Query Params:[/bold]")
        console.print(Syntax(json.dumps(params, indent=2), "json"))
        console.print(f"[bold]Headers:[/bold]")
        display_headers = {"Authorization": "Bearer ***REDACTED***"}
        console.print(Syntax(json.dumps(display_headers, indent=2), "json"))

        self.pause()

        try:
            response = requests.get(url, headers=headers, params=params, timeout=self.http_timeout)
            self.show_response(response)

            if response.status_code == 200:
                data = response.json()
                self.selected_model = data.get('selected_profile_label')
                self.log(f"✓ Model selected: {self.selected_model}", 'SUCCESS')
            else:
                self.log(f"✗ Failed to get model selection: {response.status_code}", 'ERROR')
                return False
        except Exception as e:
            self.log(f"✗ Request failed: {e}", 'ERROR')
            return False

        self.pause("Review the model selection. Press Enter to continue...")
        return True

    def test_step_6_invoke_bedrock(self) -> bool:
        """Step 6: Invoke Bedrock with Inference Profile"""
        console.print(Panel("[bold]Step 6: Invoke Bedrock Model[/bold]"))

        if not self.inference_profile_arn:
            self.log("✗ Inference profile ARN not configured", 'ERROR')
            return False

        prompt = self.config['test_prompt']
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            "inferenceConfig": {
                "maxTokens": 512,
                "temperature": 0.7
            }
        }

        console.print(Panel("[bold cyan]BEDROCK REQUEST[/bold cyan]", expand=False))
        console.print(f"[bold]Model ARN:[/bold] {self.inference_profile_arn}")
        console.print(f"[bold]Request Body:[/bold]")
        console.print(Syntax(json.dumps(request_body, indent=2), "json"))

        self.pause()

        try:
            self.log("Invoking Bedrock model...")
            response = self.bedrock_runtime.converse(
                modelId=self.inference_profile_arn,
                messages=request_body['messages'],
                inferenceConfig=request_body['inferenceConfig']
            )

            # Extract response details
            usage = response.get('usage', {})
            output_text = response.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')

            console.print(Panel("[bold magenta]BEDROCK RESPONSE[/bold magenta]", expand=False))
            console.print(f"[bold]Response Text:[/bold]")
            console.print(output_text)
            console.print(f"\n[bold]Token Usage:[/bold]")
            console.print(f"  Input Tokens: {usage.get('inputTokens', 0)}")
            console.print(f"  Output Tokens: {usage.get('outputTokens', 0)}")
            console.print(f"  Total Tokens: {usage.get('totalTokens', 0)}")

            # Store for next step
            self.invocation_result = {
                "input_tokens": usage.get('inputTokens', 0),
                "output_tokens": usage.get('outputTokens', 0),
                "model_id": self.model_id
            }

            self.log("✓ Bedrock invocation successful", 'SUCCESS')
        except Exception as e:
            self.log(f"✗ Bedrock invocation failed: {e}", 'ERROR')
            return False

        self.pause("Review the Bedrock response. Press Enter to continue...")
        return True

    def test_step_7_submit_usage(self) -> bool:
        """Step 7: Submit Usage"""
        console.print(Panel("[bold]Step 7: Submit Usage[/bold]"))

        if not self.access_token or not self.invocation_result:
            self.log("✗ Missing prerequisites. Run previous steps first.", 'ERROR')
            return False

        url = f"{self.service_url}/orgs/{self.org_id}/apps/{self.app_id}/usage"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        body = {
            "model_id": self.invocation_result['model_id'],
            "input_tokens": self.invocation_result['input_tokens'],
            "output_tokens": self.invocation_result['output_tokens'],
            "calling_region": self.aws_region
        }

        self.show_request("POST", url, headers, body)
        self.pause()

        try:
            response = requests.post(url, headers=headers, json=body, timeout=self.http_timeout)
            self.show_response(response)

            if response.status_code == 201:
                self.log("✓ Usage submitted successfully", 'SUCCESS')
            else:
                self.log(f"✗ Failed to submit usage: {response.status_code}", 'ERROR')
                return False
        except Exception as e:
            self.log(f"✗ Request failed: {e}", 'ERROR')
            return False

        self.pause("Review the usage submission. Press Enter to continue...")
        return True

    def test_step_8_check_aggregates(self) -> bool:
        """Step 8: Check Aggregates"""
        console.print(Panel("[bold]Step 8: Check Usage Aggregates[/bold]"))

        if not self.access_token:
            self.log("✗ Access token not available. Run step 3 first.", 'ERROR')
            return False

        url = f"{self.service_url}/orgs/{self.org_id}/apps/{self.app_id}/usage/aggregates"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        params = {
            "start_date": today,
            "end_date": today
        }

        console.print(Panel("[bold cyan]REQUEST[/bold cyan]", expand=False))
        console.print(f"[bold]Method:[/bold] GET")
        console.print(f"[bold]URL:[/bold] {url}")
        console.print(f"[bold]Query Params:[/bold]")
        console.print(Syntax(json.dumps(params, indent=2), "json"))

        self.pause()

        try:
            response = requests.get(url, headers=headers, params=params, timeout=self.http_timeout)
            self.show_response(response)

            if response.status_code == 200:
                self.log("✓ Aggregates retrieved successfully", 'SUCCESS')

                # Display in a nice table
                data = response.json()
                if data.get('aggregates'):
                    table = Table(title="Usage Aggregates")
                    table.add_column("Date", style="cyan")
                    table.add_column("Model", style="magenta")
                    table.add_column("Input Tokens", style="green")
                    table.add_column("Output Tokens", style="green")
                    table.add_column("Cost (USD)", style="yellow")

                    for agg in data['aggregates']:
                        table.add_row(
                            agg.get('date', 'N/A'),
                            agg.get('model_id', 'N/A'),
                            str(agg.get('input_tokens', 0)),
                            str(agg.get('output_tokens', 0)),
                            f"${agg.get('cost_usd', 0) / 1000000:.6f}"
                        )

                    console.print("\n")
                    console.print(table)
            else:
                self.log(f"✗ Failed to get aggregates: {response.status_code}", 'ERROR')
                return False
        except Exception as e:
            self.log(f"✗ Request failed: {e}", 'ERROR')
            return False

        self.pause("Review the aggregates. Press Enter to continue...")
        return True

    def run_all_tests(self):
        """Run all test steps"""
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]Bedrock Cost Keeper - Manual API Test[/bold cyan]\n"
            f"Service URL: {self.service_url}\n"
            f"AWS Profile: {self.aws_profile}\n"
            f"AWS Region: {self.aws_region}\n"
            f"Log File: {self.log_file}",
            border_style="cyan"
        ))
        console.print()

        steps = [
            ("Create Organization", self.test_step_1_create_org),
            ("Create Application", self.test_step_2_create_app),
            ("Authenticate", self.test_step_3_authenticate),
            ("Register Inference Profile", self.test_step_4_register_inference_profile),
            ("Get Model Selection", self.test_step_5_get_model_selection),
            ("Invoke Bedrock", self.test_step_6_invoke_bedrock),
            ("Submit Usage", self.test_step_7_submit_usage),
            ("Check Aggregates", self.test_step_8_check_aggregates),
        ]

        for i, (name, func) in enumerate(steps, 1):
            console.rule(f"[bold]Step {i}/{len(steps)}: {name}[/bold]", style="cyan")
            console.print()

            if not Confirm.ask(f"Run this step?", default=True):
                console.print("[yellow]⊘ Skipped[/yellow]\n")
                continue

            try:
                success = func()
                if not success:
                    console.print(f"\n[red]✗ Step {i} failed[/red]")
                    if not Confirm.ask("Continue anyway?", default=False):
                        console.print("[red]Test aborted[/red]")
                        return
                else:
                    console.print(f"\n[green]✓ Step {i} completed[/green]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Test interrupted by user[/yellow]")
                return
            except Exception as e:
                console.print(f"[red]Error in step {i}: {e}[/red]")
                if not Confirm.ask("Continue after error?", default=False):
                    return

            console.print()

        console.print(Panel.fit(
            "[bold green]✓ All tests completed successfully![/bold green]\n"
            f"Log file: {self.log_file}",
            border_style="green"
        ))


if __name__ == '__main__':
    try:
        tester = ManualTester()
        tester.run_all_tests()
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting...[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        sys.exit(1)
