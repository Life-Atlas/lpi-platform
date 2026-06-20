from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    anthropic_api_key: str = ""
    daily_cost_cap_usd: float = 10.0
    github_client_id: str = ""
    github_client_secret: str = ""
    admin_user_ids: str = ""

    @property
    def admin_ids_list(self) -> list[str]:
        if not self.admin_user_ids:
            return []
        return [uid.strip() for uid in self.admin_user_ids.split(",") if uid.strip()]

    @field_validator(
        "supabase_url",
        "supabase_key",
        "supabase_service_role_key",
        "supabase_jwt_secret",
        mode="before",
    )
    @classmethod
    def _strip_env_values(cls, value: str | None) -> str:
        if value is None:
            return ""
        return value.strip()

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
