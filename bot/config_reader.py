from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, StrictStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    bot_token: SecretStr
    super_admin_id: int
    ngrok_authtoken: SecretStr
    db_host: StrictStr
    db_port: int
    db_name: StrictStr
    db_user: StrictStr
    db_pass: SecretStr
    qr_secret_key: SecretStr

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_pass.get_secret_value()}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


config = Settings()
