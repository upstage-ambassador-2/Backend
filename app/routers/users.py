from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.schemas import MeOut, PlannedIntegrationOut
from app.serializers import integration_status, user_out


router = APIRouter(tags=["users"])


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
    if provider.lower() in {"gmail", "contacts", "google_contacts"}:
        return PlannedIntegrationOut(
            provider=provider,
            message="Gmail/Contacts는 Google OAuth 동의 시점에 연결됩니다.",
        )
    return PlannedIntegrationOut(provider=provider, message="지원 예정입니다.")
