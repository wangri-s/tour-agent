"""Prompt 版本管理器 — 多旅行社 prompt 版本控制

功能:
  1. 版本注册: 为每种 prompt (trip_planner/quote_agent/...) 注册多个版本
  2. 旅行社配置: YAML 驱动，每个旅行社独立配置 prompt 版本 + 品牌 + 风格
  3. 热加载: reload() 无需重启服务
  4. 降级链: agency 未配置 → default 配置 → 内置默认 prompt


用法:
    manager = PromptVersionManager()
    await manager.load_all()

    # 获取某旅行社的 trip_planner prompt
    prompt = manager.get_prompt("luxury_travel", "trip_planner")

    # 获取旅行社完整配置
    config = manager.get_agency_config("luxury_travel")

架构:
    config/agencies/{agency_id}.yaml  → 旅行社配置
    prompts/versions/                 → 各 prompt 的版本实现
    services/prompt_manager.py        → 管理器 (本文件)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# =========================================================================
# 内置默认 prompt (兜底)
# =========================================================================

# 导入默认版本
from prompts.versions.trip_planner_v1 import TRIP_PLANNER_V1_STANDARD

_BUILTIN_PROMPTS: dict[str, dict[str, str]] = {
    "trip_planner": {
        "v1_standard": TRIP_PLANNER_V1_STANDARD,
    },
}

# 默认旅行社配置
_DEFAULT_AGENCY_CONFIG: dict[str, Any] = {
    "agency_id": "default",
    "brand_name": "默认旅行社",
    "brand_name_en": "Default Travel Agency",
    "default_language": "zh",
    "prompt_versions": {
        "trip_planner": "v1_standard",
    },
    "model_overrides": {},
    "output_style": {
        "tone": "professional",
        "currency": "CNY",
        "include_brand_header": False,
    },
}


class PromptVersionManager:
    """多版本 prompt 管理器

    加载顺序:
      1. 内置默认 prompt (硬编码兜底)
      2. prompts/versions/ 目录下的版本文件 (Python 模块)
      3. config/agencies/{agency_id}.yaml (旅行社配置)
    """

    def __init__(self):
        self._agencies: dict[str, dict[str, Any]] = {}
        self._prompts: dict[str, dict[str, str]] = dict(_BUILTIN_PROMPTS)
        self._loaded = False

    # =========================================================================
    # 加载
    # =========================================================================

    async def load_all(self) -> dict[str, Any]:
        """加载所有配置和版本

        Returns:
            {"agencies": N, "versions": {...}, "status": "ok"}
        """
        # 1. 加载 prompt 版本
        self._load_prompt_versions()

        # 2. 加载旅行社配置
        self._load_agency_configs()

        self._loaded = True

        summary = {
            "agencies": len(self._agencies),
            "versions": {
                name: list(versions.keys())
                for name, versions in self._prompts.items()
            },
            "status": "ok",
        }

        logger.info(
            "[PromptManager] 加载完成: %d 家旅行社, %d 种 prompt, 版本: %s",
            summary["agencies"],
            len(self._prompts),
            summary["versions"],
        )
        return summary

    def _load_prompt_versions(self):
        """扫描 prompts/versions/ 目录，动态加载版本模块"""
        versions_dir = PROJECT_ROOT / "prompts" / "versions"

        # 动态导入版本文件
        version_files = {
            "v2_luxury": "trip_planner_v2",
            "v3_budget": "trip_planner_v3",
        }

        for version_key, module_name in version_files.items():
            try:
                mod = __import__(
                    f"prompts.versions.{module_name}",
                    fromlist=[module_name],
                )
                # 按约定: 模块导出 PROMPT 变量
                if hasattr(mod, "PROMPT"):
                    if "trip_planner" not in self._prompts:
                        self._prompts["trip_planner"] = {}
                    self._prompts["trip_planner"][version_key] = mod.PROMPT
                    logger.debug("[PromptManager] 加载版本: trip_planner/%s", version_key)
            except ImportError as e:
                logger.warning("[PromptManager] 版本加载失败 %s: %s", version_key, e)

    def _load_agency_configs(self):
        """加载 config/agencies/*.yaml"""
        config_dir = PROJECT_ROOT / "config" / "agencies"
        if not config_dir.exists():
            logger.warning("[PromptManager] 配置目录不存在: %s", config_dir)
            return

        for yaml_file in config_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                if not config or "agency_id" not in config:
                    logger.warning("[PromptManager] 跳过无效配置: %s", yaml_file)
                    continue

                agency_id = config["agency_id"]
                # 合并默认值
                merged = {**_DEFAULT_AGENCY_CONFIG, **config}
                self._agencies[agency_id] = merged
                logger.info(
                    "[PromptManager] 加载旅行社: %s (%s) → trip_planner=%s",
                    agency_id,
                    config.get("brand_name", agency_id),
                    merged.get("prompt_versions", {}).get("trip_planner", "default"),
                )
            except Exception as e:
                logger.error("[PromptManager] 加载配置失败 %s: %s", yaml_file, e)

    # =========================================================================
    # 查询
    # =========================================================================

    def get_prompt(self, agency_id: str | None, prompt_name: str = "trip_planner") -> str:
        """获取旅行社对应的 prompt 文本

        降级链:
          1. agency YAML 的 prompt_overrides.{prompt_name} (完全自定义)
          2. agency YAML 的 prompt_versions.{prompt_name} → 版本文件
          3. default YAML 配置
          4. 内置 v1_standard

        Args:
            agency_id: 旅行社 ID (如 "luxury_travel"), None 则用 default
            prompt_name: prompt 名称 (如 "trip_planner")

        Returns:
            prompt 文本字符串
        """
        # 1. 确定版本
        config = self.get_agency_config(agency_id)

        # ---- 1a. YAML 内联覆盖 (最高优先级) ----
        overrides = config.get("prompt_overrides", {})
        override_text = overrides.get(prompt_name, "").strip()
        if override_text:
            logger.info(
                "[PromptManager] prompt=%s, agency=%s, source=YAML override",
                prompt_name, agency_id or "default",
            )
            return self._apply_brand_header(override_text, config)

        # ---- 1b. 版本路由 ----
        version = (
            config.get("prompt_versions", {})
            .get(prompt_name, "v1_standard")
        )

        # 2. 查找版本对应的 prompt 文本
        prompts = self._prompts.get(prompt_name, {})
        text = prompts.get(version)

        if text:
            logger.debug(
                "[PromptManager] prompt=%s, agency=%s, version=%s",
                prompt_name, agency_id or "default", version,
            )
            return self._apply_brand_header(text, config)

        # 3. 降级: 版本不存在 → v1_standard
        logger.warning(
            "[PromptManager] 版本 %s/%s 不存在，降级 v1_standard",
            prompt_name, version,
        )
        return self._apply_brand_header(
            prompts.get("v1_standard", _BUILTIN_PROMPTS["trip_planner"]["v1_standard"]),
            config,
        )

    def _apply_brand_header(self, text: str, config: dict) -> str:
        """如果配置了品牌头，加到 prompt 前面"""
        output_style = config.get("output_style", {})
        if output_style.get("include_brand_header") and output_style.get("brand_header"):
            brand_header = output_style["brand_header"]
            return f"## 品牌身份\n你代表「{config['brand_name']}」。\n{brand_header}\n\n{text}"
        return text

    def get_agency_config(self, agency_id: str | None) -> dict[str, Any]:
        """获取旅行社完整配置

        Args:
            agency_id: 旅行社 ID, None 或空字符串返回 default

        Returns:
            旅行社配置 dict
        """
        if not agency_id:
            return dict(_DEFAULT_AGENCY_CONFIG)

        config = self._agencies.get(agency_id)
        if config:
            return config

        logger.debug("[PromptManager] 旅行社 %s 未配置，使用 default", agency_id)
        return dict(_DEFAULT_AGENCY_CONFIG)

    def list_agencies(self) -> list[dict[str, Any]]:
        """列出所有已配置的旅行社"""
        result = []
        for agency_id, config in self._agencies.items():
            result.append({
                "agency_id": agency_id,
                "brand_name": config.get("brand_name", agency_id),
                "brand_name_en": config.get("brand_name_en", ""),
                "prompt_versions": config.get("prompt_versions", {}),
            })
        return result

    def list_versions(self, prompt_name: str = "trip_planner") -> list[dict[str, str]]:
        """列出某个 prompt 的所有可用版本"""
        versions = self._prompts.get(prompt_name, {})
        return [
            {
                "version": v,
                "length": len(text),
                "preview": text[:120] + "...",
            }
            for v, text in versions.items()
        ]

    # =========================================================================
    # 热加载
    # =========================================================================

    async def reload(self) -> dict[str, Any]:
        """重新加载所有配置 (热更新)"""
        self._agencies.clear()
        return await self.load_all()

    # =========================================================================
    # 状态
    # =========================================================================

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def agency_count(self) -> int:
        return len(self._agencies)


# =========================================================================
# 全局实例
# =========================================================================

prompt_manager = PromptVersionManager()
