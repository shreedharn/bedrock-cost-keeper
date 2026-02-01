"""Unit tests for InferenceProfileService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from botocore.exceptions import ClientError

from src.domain.services.inference_profile_service import InferenceProfileService


@pytest.fixture
def mock_db():
    """Create a mock database bridge."""
    db = MagicMock()
    db.register_inference_profile = AsyncMock()
    db.get_inference_profile = AsyncMock(return_value=None)
    db.list_inference_profiles = AsyncMock(return_value=[])
    return db


@pytest.fixture
def profile_service(mock_db):
    """Create an InferenceProfileService instance."""
    return InferenceProfileService(mock_db)


class TestValidateArnFormat:
    """Tests for ARN format validation."""

    def test_valid_arn_format(self, profile_service):
        """Test validation of valid ARN format."""
        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/my-profile"
        assert profile_service._validate_arn_format(arn) is True

    def test_valid_arn_with_hyphens_in_profile(self, profile_service):
        """Test ARN with hyphens in profile name."""
        arn = "arn:aws:bedrock:us-west-2:123456789012:inference-profile/tenant-a-premium"
        assert profile_service._validate_arn_format(arn) is True

    def test_valid_arn_different_region(self, profile_service):
        """Test ARN with different region."""
        arn = "arn:aws:bedrock:eu-west-1:987654321098:inference-profile/profile123"
        assert profile_service._validate_arn_format(arn) is True

    def test_invalid_arn_wrong_service(self, profile_service):
        """Test ARN with wrong service name."""
        arn = "arn:aws:s3:us-east-1:123456789012:inference-profile/my-profile"
        assert profile_service._validate_arn_format(arn) is False

    def test_invalid_arn_wrong_resource_type(self, profile_service):
        """Test ARN with wrong resource type."""
        arn = "arn:aws:bedrock:us-east-1:123456789012:model/my-model"
        assert profile_service._validate_arn_format(arn) is False

    def test_invalid_arn_malformed(self, profile_service):
        """Test malformed ARN."""
        arn = "not-an-arn"
        assert profile_service._validate_arn_format(arn) is False

    def test_invalid_arn_missing_profile_id(self, profile_service):
        """Test ARN without profile ID."""
        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/"
        assert profile_service._validate_arn_format(arn) is False


class TestGetProfileDetails:
    """Tests for AWS GetInferenceProfile API interaction."""

    @pytest.mark.asyncio
    @patch('src.domain.services.inference_profile_service.boto3')
    async def test_get_profile_details_single_region(self, mock_boto3, profile_service):
        """Test getting profile details for single-region profile."""
        # Mock AWS response
        mock_bedrock = MagicMock()
        mock_boto3.client.return_value = mock_bedrock
        mock_bedrock.get_inference_profile.return_value = {
            'inferenceProfileId': 'my-profile',
            'inferenceProfileArn': 'arn:aws:bedrock:us-east-1:123456789012:inference-profile/my-profile',
            'status': 'ACTIVE',
            'models': [
                {
                    'modelArn': 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0',
                    'region': 'us-east-1'
                }
            ]
        }

        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/my-profile"
        result = await profile_service._get_profile_details(arn)

        assert result['models'] == {
            'us-east-1': 'amazon.nova-pro-v1:0'
        }

        # Verify boto3 client was called correctly
        mock_boto3.client.assert_called_once_with('bedrock', region_name='us-east-1')
        mock_bedrock.get_inference_profile.assert_called_once_with(
            inferenceProfileIdentifier=arn
        )

    @pytest.mark.asyncio
    @patch('src.domain.services.inference_profile_service.boto3')
    async def test_get_profile_details_multi_region(self, mock_boto3, profile_service):
        """Test getting profile details for cross-region profile."""
        mock_bedrock = MagicMock()
        mock_boto3.client.return_value = mock_bedrock
        mock_bedrock.get_inference_profile.return_value = {
            'inferenceProfileId': 'multi-region-profile',
            'models': [
                {
                    'modelArn': 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0',
                    'region': 'us-east-1'
                },
                {
                    'modelArn': 'arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-pro-v1:0',
                    'region': 'us-west-2'
                },
                {
                    'modelArn': 'arn:aws:bedrock:eu-west-1::foundation-model/amazon.nova-pro-v1:0',
                    'region': 'eu-west-1'
                }
            ]
        }

        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/multi-region"
        result = await profile_service._get_profile_details(arn)

        assert len(result['models']) == 3
        assert result['models']['us-east-1'] == 'amazon.nova-pro-v1:0'
        assert result['models']['us-west-2'] == 'amazon.nova-pro-v1:0'
        assert result['models']['eu-west-1'] == 'amazon.nova-pro-v1:0'

    @pytest.mark.asyncio
    @patch('src.domain.services.inference_profile_service.boto3')
    async def test_get_profile_details_no_models(self, mock_boto3, profile_service):
        """Test error when profile has no models."""
        mock_bedrock = MagicMock()
        mock_boto3.client.return_value = mock_bedrock
        mock_bedrock.get_inference_profile.return_value = {
            'inferenceProfileId': 'empty-profile',
            'models': []
        }

        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/empty"

        with pytest.raises(ValueError, match="Unable to determine models"):
            await profile_service._get_profile_details(arn)


class TestRegisterProfile:
    """Tests for profile registration."""

    @pytest.mark.asyncio
    @patch('src.domain.services.inference_profile_service.boto3')
    async def test_register_profile_success(self, mock_boto3, profile_service, mock_db):
        """Test successful profile registration."""
        # Mock AWS response
        mock_bedrock = MagicMock()
        mock_boto3.client.return_value = mock_bedrock
        mock_bedrock.get_inference_profile.return_value = {
            'inferenceProfileId': 'tenant-a',
            'models': [
                {
                    'modelArn': 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0',
                    'region': 'us-east-1'
                }
            ]
        }

        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/tenant-a"
        result = await profile_service.register_profile(
            org_id="org-123",
            app_id="app-456",
            profile_label="tenant-a-premium",
            inference_profile_arn=arn,
            description="Premium profile for Tenant A"
        )

        assert result['profile_label'] == "tenant-a-premium"
        assert result['inference_profile_arn'] == arn
        assert result['supported_regions'] == ['us-east-1']
        assert result['status'] == 'registered'
        assert result['description'] == "Premium profile for Tenant A"

        # Verify database was called
        mock_db.register_inference_profile.assert_called_once()
        call_args = mock_db.register_inference_profile.call_args[1]
        assert call_args['org_id'] == "org-123"
        assert call_args['app_id'] == "app-456"
        assert call_args['profile_label'] == "tenant-a-premium"

    @pytest.mark.asyncio
    async def test_register_profile_invalid_arn(self, profile_service, mock_db):
        """Test registration with invalid ARN format."""
        with pytest.raises(ValueError, match="Invalid inference profile ARN"):
            await profile_service.register_profile(
                org_id="org-123",
                app_id="app-456",
                profile_label="test",
                inference_profile_arn="not-a-valid-arn"
            )

        # Verify database was NOT called
        mock_db.register_inference_profile.assert_not_called()

    @pytest.mark.asyncio
    @patch('src.domain.services.inference_profile_service.boto3')
    async def test_register_profile_aws_error(self, mock_boto3, profile_service, mock_db):
        """Test registration when AWS API fails."""
        # Mock AWS error
        mock_bedrock = MagicMock()
        mock_boto3.client.return_value = mock_bedrock
        mock_bedrock.get_inference_profile.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Profile not found'}},
            'GetInferenceProfile'
        )

        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/nonexistent"

        with pytest.raises(ValueError, match="Failed to retrieve inference profile from AWS"):
            await profile_service.register_profile(
                org_id="org-123",
                app_id="app-456",
                profile_label="test",
                inference_profile_arn=arn
            )

        # Verify database was NOT called
        mock_db.register_inference_profile.assert_not_called()


class TestGetModelForRegion:
    """Tests for model resolution by region."""

    @pytest.mark.asyncio
    async def test_get_model_for_region_success(self, profile_service, mock_db):
        """Test successful model resolution for a region."""
        # Mock database response
        mock_db.get_inference_profile.return_value = {
            'profile_label': 'tenant-a-premium',
            'inference_profile_arn': 'arn:aws:bedrock:us-east-1:123456789012:inference-profile/tenant-a',
            'model_arns': {
                'us-east-1': 'amazon.nova-pro-v1:0',
                'us-west-2': 'amazon.nova-pro-v1:0',
                'eu-west-1': 'amazon.nova-pro-v1:0'
            }
        }

        model_id = await profile_service.get_model_for_region(
            org_id="org-123",
            app_id="app-456",
            profile_label="tenant-a-premium",
            calling_region="us-west-2"
        )

        assert model_id == 'amazon.nova-pro-v1:0'
        mock_db.get_inference_profile.assert_called_once_with("org-123", "app-456", "tenant-a-premium")

    @pytest.mark.asyncio
    async def test_get_model_for_region_profile_not_registered(self, profile_service, mock_db):
        """Test error when profile is not registered."""
        mock_db.get_inference_profile.return_value = None

        with pytest.raises(ValueError, match="Inference profile not registered"):
            await profile_service.get_model_for_region(
                org_id="org-123",
                app_id="app-456",
                profile_label="nonexistent",
                calling_region="us-east-1"
            )

    @pytest.mark.asyncio
    async def test_get_model_for_region_unsupported_region(self, profile_service, mock_db):
        """Test error when region is not supported by profile."""
        mock_db.get_inference_profile.return_value = {
            'model_arns': {
                'us-east-1': 'amazon.nova-pro-v1:0'
            }
        }

        with pytest.raises(ValueError, match="Region ap-southeast-1 not supported"):
            await profile_service.get_model_for_region(
                org_id="org-123",
                app_id="app-456",
                profile_label="test",
                calling_region="ap-southeast-1"
            )


class TestListAndGetProfiles:
    """Tests for listing and retrieving profiles."""

    @pytest.mark.asyncio
    async def test_list_profiles(self, profile_service, mock_db):
        """Test listing all profiles for an app."""
        mock_db.list_inference_profiles.return_value = [
            {
                'sk': 'PROFILE#tenant-a',
                'inference_profile_arn': 'arn:aws:bedrock:us-east-1:123456789012:inference-profile/tenant-a',
                'model_arns': {'us-east-1': 'model-1'}
            },
            {
                'sk': 'PROFILE#tenant-b',
                'inference_profile_arn': 'arn:aws:bedrock:us-east-1:123456789012:inference-profile/tenant-b',
                'model_arns': {'us-west-2': 'model-2'}
            }
        ]

        profiles = await profile_service.list_profiles("org-123", "app-456")

        assert len(profiles) == 2
        mock_db.list_inference_profiles.assert_called_once_with("org-123", "app-456")

    @pytest.mark.asyncio
    async def test_get_profile(self, profile_service, mock_db):
        """Test getting a specific profile."""
        mock_db.get_inference_profile.return_value = {
            'profile_label': 'test',
            'inference_profile_arn': 'arn:aws:bedrock:us-east-1:123456789012:inference-profile/test'
        }

        profile = await profile_service.get_profile("org-123", "app-456", "test")

        assert profile is not None
        assert profile['profile_label'] == 'test'
        mock_db.get_inference_profile.assert_called_once_with("org-123", "app-456", "test")

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, profile_service, mock_db):
        """Test getting a profile that doesn't exist."""
        mock_db.get_inference_profile.return_value = None

        profile = await profile_service.get_profile("org-123", "app-456", "nonexistent")

        assert profile is None
