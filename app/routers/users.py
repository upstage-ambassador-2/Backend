from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas import MeOut, PlannedIntegrationOut
from app.serializers import integration_status, user_out


router = APIRouter(tags=["users"])

GOOGLE_INTEGRATION_PROVIDERS = {"gmail", "contacts", "google_contacts"}
PLANNED_INTEGRATION_PROVIDERS = {"slack", "notion"}


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, db: DbSession) -> MeOut:
    db.refresh(user, ["oauth_token"])
    return MeOut(user=user_out(user), integrations=integration_status(user.oauth_token))


@router.get("/integrations")
def integrations(user: CurrentUser, db: DbSession):
    db.refresh(user, ["oauth_token"])
    return integration_status(user.oauth_token)


@router.post("/integrations/{provider}/toggle", response_model=PlannedIntegrationOut)
def planned_integration_toggle(provider: str, user: CurrentUser) -> PlannedIntegrationOut:
    normalized_provider = provider.lower()
    if normalized_provider not in GOOGLE_INTEGRATION_PROVIDERS | PLANNED_INTEGRATION_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="지원하지 않는 연동 제공자입니다.",
        )

    if normalized_provider in GOOGLE_INTEGRATION_PROVIDERS:
        return PlannedIntegrationOut(
            provider="contacts" if normalized_provider == "google_contacts" else normalized_provider,
            message="Gmail/Contacts는 Google OAuth 동의 시점에 연결됩니다.",
        )
    return PlannedIntegrationOut(provider=normalized_provider, message="지원 예정입니다.")
