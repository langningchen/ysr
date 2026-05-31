# utils/config_loader.py
import tomllib
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Literal

class AccountConfig(BaseModel):
    username: str
    password: str
    cookie_path: str = "cookies.json"

class QueueConfig(BaseModel):
    queue_pref: Literal["fast", "normal", "threshold"] = "threshold"
    threshold_minutes: float = Field(default=10.0, ge=0.0)

class AppConfig(BaseModel):
    account: AccountConfig
    queue: QueueConfig

def load_config(config_path: str = "config.toml") -> AppConfig:
    """
    强类型配置文件加载器
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"未找到配置文件: {config_path}")
        
    with open(path, "rb") as f:
        data = tomllib.load(f)
        
    # Pydantic 核心数据校验
    return AppConfig.model_validate(data)
