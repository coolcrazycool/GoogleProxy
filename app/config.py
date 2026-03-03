from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Settings:
    DATA_DIR: str = os.getenv("DATA_DIR", "./data")
    TOKENS_FILE: str = os.getenv("TOKENS_FILE", "tokens.json")

    @property
    def tokens_file_path(self) -> str:
        return str(Path(self.DATA_DIR) / self.TOKENS_FILE)


settings = Settings()
