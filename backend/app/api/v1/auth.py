from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the caller's profile",
    responses={
        200: {"description": "Profile of the JWT-authenticated user"},
        401: {"description": "Missing or invalid bearer token"},
    },
)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Return the profile of whoever the bearer token belongs to.

    The frontend hits this once after sign-in to populate the in-memory
    user context (role, ``preferred_locale``, ``full_name``). It does
    NOT trigger any side effect — repeated calls are free.
    """
    return UserResponse.model_validate(current_user)
