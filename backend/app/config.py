"""App settings, read from environment variables (see .env.example)."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSize(StrEnum):
    """Each AI job asks for a size, not a model name, so models can be swapped in one place."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    firecrawl_api_key: str = ""

    database_url: str = "postgresql+psycopg://campaign:campaign@localhost:5432/campaign"
    data_dir: Path = Path("data")
    brand_dir: Path | None = None
    brand_name: str = ""
    """Name for the preloaded brand. Defaults to the folder's name."""
    brand_source: str = ""
    """The preload folder as given on this machine (BRAND_DIR before Docker mounts it, which always mounts it at
    the same place). It tells one preloaded brand folder from another."""
    brand_exclude: str = ""
    """Comma-separated folder or file patterns in the preload folder that are not brand material, such as briefs."""

    model_small: str = "gpt-6-luna"
    model_medium: str = "gpt-6.1-terra"
    model_large: str = "gpt-6.1-sol"
    model_embedding: str = "text-embedding-3-small"

    writing_workers: int = 3
    """How many assets are written at the same time."""

    def model_for(self, size: ModelSize) -> str:
        return {
            ModelSize.SMALL: self.model_small,
            ModelSize.MEDIUM: self.model_medium,
            ModelSize.LARGE: self.model_large,
        }[size]

    @field_validator("brand_dir", mode="before")
    @classmethod
    def _blank_means_no_folder(cls, value: object) -> object:
        """`BRAND_DIR=` with nothing after it means no preload, not the current folder."""
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def brand_exclude_patterns(self) -> list[str]:
        return [pattern.strip() for pattern in self.brand_exclude.split(",") if pattern.strip()]

    @property
    def ai_log_file(self) -> Path:
        return self.data_dir / "logs" / "ai_calls.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
