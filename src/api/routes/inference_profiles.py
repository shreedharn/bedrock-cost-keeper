"""API routes for managing AWS Bedrock inference profiles."""
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from ..models.requests import InferenceProfileRegistrationRequest
from ..models.responses import InferenceProfileResponse
from ..dependencies import get_inference_profile_service, verify_jwt_token
from ...domain.services.inference_profile_service import InferenceProfileService
from ...core.exceptions import InvalidRequestException, InternalServerErrorException

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/orgs/{org_id}/apps/{app_id}/inference-profiles",
    tags=["inference-profiles"]
)


@router.post(
    "",
    response_model=InferenceProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an inference profile",
    description="""
    Register an AWS Bedrock inference profile for an application.

    This allows using the profile_label in usage submissions instead of
    bedrock_model_id. The service will automatically resolve the label to
    the appropriate model based on the calling region.

    Multi-tenant use case: Create separate profiles for each tenant to
    enable granular cost tracking and allocation.
    """
)
async def register_inference_profile(
    org_id: str,
    app_id: str,
    request: InferenceProfileRegistrationRequest,
    auth: dict = Depends(verify_jwt_token),
    profile_service: InferenceProfileService = Depends(get_inference_profile_service)
):
    """Register an inference profile for an app."""
    try:
        result = await profile_service.register_profile(
            org_id=org_id,
            app_id=app_id,
            profile_label=request.profile_label,
            inference_profile_arn=request.inference_profile_arn,
            description=request.description
        )
        return InferenceProfileResponse(**result)
    except ValueError as e:
        raise InvalidRequestException(str(e))
    except Exception as e:
        logger.error(f"Failed to register inference profile: {e}", exc_info=True)
        raise InternalServerErrorException("Failed to register inference profile")


@router.get(
    "",
    response_model=List[InferenceProfileResponse],
    summary="List inference profiles",
    description="List all registered inference profiles for an application."
)
async def list_inference_profiles(
    org_id: str,
    app_id: str,
    auth: dict = Depends(verify_jwt_token),
    profile_service: InferenceProfileService = Depends(get_inference_profile_service)
):
    """List all registered inference profiles for an app."""
    try:
        profiles = await profile_service.list_profiles(org_id, app_id)

        # Convert to response models
        results = []
        for profile in profiles:
            # Extract profile label from sk (format: PROFILE#<label>)
            profile_label = profile['sk'].replace('PROFILE#', '')

            results.append(InferenceProfileResponse(
                profile_label=profile_label,
                inference_profile_arn=profile['inference_profile_arn'],
                supported_regions=list(profile.get('model_arns', {}).keys()),
                status='registered',
                description=profile.get('description'),
                created_at=profile.get('created_at')
            ))

        return results
    except Exception as e:
        logger.error(f"Failed to list inference profiles: {e}", exc_info=True)
        raise InternalServerErrorException("Failed to list inference profiles")


@router.get(
    "/{profile_label}",
    response_model=InferenceProfileResponse,
    summary="Get inference profile details",
    description="Get details of a specific registered inference profile."
)
async def get_inference_profile(
    org_id: str,
    app_id: str,
    profile_label: str,
    auth: dict = Depends(verify_jwt_token),
    profile_service: InferenceProfileService = Depends(get_inference_profile_service)
):
    """Get details of a specific inference profile."""
    try:
        profile = await profile_service.get_profile(org_id, app_id, profile_label)

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Inference profile '{profile_label}' not found"
            )

        return InferenceProfileResponse(
            profile_label=profile_label,
            inference_profile_arn=profile['inference_profile_arn'],
            supported_regions=list(profile.get('model_arns', {}).keys()),
            status='registered',
            description=profile.get('description'),
            created_at=profile.get('created_at')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get inference profile: {e}", exc_info=True)
        raise InternalServerErrorException("Failed to get inference profile")
