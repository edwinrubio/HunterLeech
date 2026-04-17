from pydantic_settings import BaseSettings, SettingsConfigDict


class ETLConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    socrata_app_token: str = ""
    batch_size: int = 500          # records per UNWIND transaction
    page_size: int = 1000          # rows per Socrata API page
    http_timeout: float = 30.0     # seconds per Socrata request

    state_dir: str = ".etl_state"  # local dir for run-state JSON files


etl_config = ETLConfig()
