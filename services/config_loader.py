"""统一配置加载器 — 从 config/tour_agent.yaml 读取所有配置

支持:
  - ${ENV_VAR:-default} 环境变量语法
  - 点号路径访问: config.get("llm.models.planner")
  - 热加载: config.reload()
  - 类型安全: config.get_int(), config.get_bool()

用法:
    from services.config_loader import config
    model = config.get("llm.models.planner", "qwen-max")

架构:
    config/tour_agent.yaml → ConfigLoader → 全局 config 实例 → 各服务模块
    环境变量 (.env)         ↗
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "tour_agent.yaml"


def _resolve_env(value: Any) -> Any:
    """递归解析 ${ENV_VAR:-default} 语法"""
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            var_name = m.group(1)
            default = m.group(2) if m.group(2) is not None else ""
            return os.getenv(var_name, default)
        return re.sub(r'\$\{(\w+)(?::-([^}]*))?\}', _replace, value)
    elif isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


class ConfigLoader:
    """统一配置加载器

    单例模式，首次访问时自动加载。
    """

    _instance: ConfigLoader | None = None
    _data: dict[str, Any] = {}
    _loaded: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # =========================================================================
    # 加载
    # =========================================================================

    def load(self, path: Path | None = None) -> dict[str, Any]:
        """加载配置文件

        Args:
            path: YAML 文件路径，默认 config/tour_agent.yaml

        Returns:
            解析后的完整配置 dict
        """
        yaml_path = path or DEFAULT_CONFIG_PATH

        if not yaml_path.exists():
            logger.warning("[Config] 配置文件不存在: %s, 使用空配置", yaml_path)
            self._data = {}
            self._loaded = True
            return self._data

        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw:
            logger.warning("[Config] 配置文件为空")
            self._data = {}
        else:
            self._data = _resolve_env(raw)

        self._loaded = True

        logger.info(
            "[Config] 加载完成: %s — %d 顶级配置段 (%s)",
            yaml_path.name,
            len(self._data),
            ", ".join(self._data.keys()),
        )
        return self._data

    def reload(self) -> dict[str, Any]:
        """热加载配置"""
        self._loaded = False
        return self.load()

    # =========================================================================
    # 通用访问
    # =========================================================================

    def get(self, path: str, default: Any = None) -> Any:
        """点号路径访问: config.get("llm.models.planner")"""
        if not self._loaded:
            self.load()

        keys = path.split(".")
        node: Any = self._data
        for key in keys:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                return default
            if node is None:
                return default
        return node

    def get_str(self, path: str, default: str = "") -> str:
        return str(self.get(path, default))

    def get_int(self, path: str, default: int = 0) -> int:
        return int(self.get(path, default))

    def get_bool(self, path: str, default: bool = False) -> bool:
        val = self.get(path, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "yes", "1", "on")
        return bool(val)

    def get_float(self, path: str, default: float = 0.0) -> float:
        return float(self.get(path, default))

    def get_list(self, path: str, default: list | None = None) -> list:
        val = self.get(path, default or [])
        return val if isinstance(val, list) else [val]

    def get_dict(self, path: str) -> dict[str, Any]:
        val = self.get(path, {})
        return val if isinstance(val, dict) else {}

    # =========================================================================
    # 快捷属性
    # =========================================================================

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def data(self) -> dict[str, Any]:
        if not self._loaded:
            self.load()
        return self._data

    @property
    def version(self) -> str:
        return self.get_str("settings.version", "0.5.0")


# =========================================================================
# 全局实例
# =========================================================================

config = ConfigLoader()
