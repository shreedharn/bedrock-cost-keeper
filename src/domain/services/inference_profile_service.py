"""Service for managing AWS Bedrock inference profiles.

Inference profiles enable cost allocation at a granular level by tagging
requests with custom identifiers. This is particularly useful for multi-tenant
scenarios where you need to track costs per tenant or customer.
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError


class InferenceProfileService:
    """Service for managing inference profiles and model resolution."""

    def __init__(self, db):
        """Initialize the service.

        Args:
            db: DynamoDBBridge instance for database operations
        """
        self.db = db

    async def register_profile(
        self,
        org_id: str,
        app_id: str,
        profile_label: str,
        inference_profile_arn: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Register an inference profile for an app.

        Steps:
        1. Validate ARN format
        2. Call GetInferenceProfile to validate and get model details
        3. Store in database

        Args:
            org_id: Organization ID
            app_id: Application ID
            profile_label: Label to use for this profile (used in usage submissions)
            inference_profile_arn: AWS Bedrock inference profile ARN
            description: Optional description of the profile

        Returns:
            Dict containing registration details

        Raises:
            ValueError: If ARN format is invalid or profile doesn't exist in AWS
        """
        # Validate ARN format
        if not self._validate_arn_format(inference_profile_arn):
            raise ValueError(f"Invalid inference profile ARN: {inference_profile_arn}")

        # Get profile details from AWS
        try:
            profile_details = await self._get_profile_details(inference_profile_arn)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            raise ValueError(
                f"Failed to retrieve inference profile from AWS ({error_code}): {error_msg}"
            )

        # Store registration
        created_at = datetime.now(timezone.utc)
        await self.db.register_inference_profile(
            org_id=org_id,
            app_id=app_id,
            profile_label=profile_label,
            inference_profile_arn=inference_profile_arn,
            model_arns=profile_details['models'],
            description=description,
            created_at=created_at
        )

        return {
            "profile_label": profile_label,
            "inference_profile_arn": inference_profile_arn,
            "supported_regions": list(profile_details['models'].keys()),
            "status": "registered",
            "description": description,
            "created_at": created_at
        }

    async def get_model_for_region(
        self,
        org_id: str,
        app_id: str,
        profile_label: str,
        calling_region: str
    ) -> str:
        """Get the underlying model ID for a profile in a specific region.

        Args:
            org_id: Organization ID
            app_id: Application ID
            profile_label: Profile label
            calling_region: AWS region where the request is being made

        Returns:
            bedrock_model_id for the calling region

        Raises:
            ValueError: If profile not registered or region not supported
        """
        # Lookup registered profile
        profile = await self.db.get_inference_profile(org_id, app_id, profile_label)
        if not profile:
            raise ValueError(
                f"Inference profile not registered: {profile_label}. "
                f"Register it first using POST /orgs/{org_id}/apps/{app_id}/inference-profiles"
            )

        # Extract model for calling region
        model_arns = profile.get('model_arns', {})
        if calling_region not in model_arns:
            raise ValueError(
                f"Region {calling_region} not supported for profile {profile_label}. "
                f"Supported regions: {list(model_arns.keys())}"
            )

        return model_arns[calling_region]

    async def list_profiles(
        self,
        org_id: str,
        app_id: str
    ) -> list:
        """List all registered inference profiles for an app.

        Args:
            org_id: Organization ID
            app_id: Application ID

        Returns:
            List of profile registrations
        """
        return await self.db.list_inference_profiles(org_id, app_id)

    async def get_profile(
        self,
        org_id: str,
        app_id: str,
        profile_label: str
    ) -> Optional[Dict[str, Any]]:
        """Get details of a specific inference profile.

        Args:
            org_id: Organization ID
            app_id: Application ID
            profile_label: Profile label

        Returns:
            Profile details or None if not found
        """
        return await self.db.get_inference_profile(org_id, app_id, profile_label)

    async def _get_profile_details(self, profile_arn: str) -> Dict[str, Any]:
        """Call AWS Bedrock GetInferenceProfile API.

        Args:
            profile_arn: AWS Bedrock inference profile ARN

        Returns:
            Dict with 'models' key mapping region -> model_id

        Raises:
            ClientError: If AWS API call fails
        """
        # Extract region from ARN
        # Format: arn:aws:bedrock:REGION:ACCOUNT:inference-profile/PROFILE-ID
        arn_parts = profile_arn.split(':')
        region = arn_parts[3]

        # Create Bedrock client for the profile's region
        bedrock = boto3.client('bedrock', region_name=region)

        # Call GetInferenceProfile API
        response = bedrock.get_inference_profile(
            inferenceProfileIdentifier=profile_arn
        )

        # Parse response - returns models by region
        # Structure varies based on profile type (single vs cross-region)
        models = {}

        # Handle both single-region and cross-region profiles
        model_list = response.get('models', [])
        if not model_list:
            # Fallback: some profiles might not have 'models' list
            # Try to extract from other fields
            raise ValueError(
                f"Unable to determine models for inference profile {profile_arn}. "
                "Profile may be invalid or in an unexpected format."
            )

        for model_info in model_list:
            # Extract region (default to profile's region if not specified)
            model_region = model_info.get('region', region)

            # Extract model ID from ARN
            # Format: arn:aws:bedrock:REGION::foundation-model/MODEL-ID
            model_arn = model_info.get('modelArn', '')
            if model_arn:
                model_id = model_arn.split('/')[-1]
                models[model_region] = model_id
            else:
                # Fallback: try modelId field directly
                model_id = model_info.get('modelId', '')
                if model_id:
                    models[model_region] = model_id

        if not models:
            raise ValueError(
                f"No models found in inference profile {profile_arn}. "
                "Profile may be empty or malformed."
            )

        return {'models': models}

    def _validate_arn_format(self, arn: str) -> bool:
        """Validate inference profile ARN format.

        Expected format:
        arn:aws:bedrock:<region>:<account-id>:inference-profile/<profile-id>

        Args:
            arn: ARN to validate

        Returns:
            True if valid, False otherwise
        """
        pattern = r'^arn:aws:bedrock:[a-z0-9-]+:\d{12}:inference-profile/[\w-]+$'
        return bool(re.match(pattern, arn))
