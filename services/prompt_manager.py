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
from contextvars import ContextVar
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
    "brand_name": "探索中国国际旅行社",
    "brand_name_en": "Discover China Travel",
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
        """注入旅行社品牌身份到 prompt

        每家旅行社的 prompt 都会注入身份声明，确保 LLM 知道自己的旅行社归属。
        当用户问"你是哪个旅行社"时，能准确回答。
        """
        brand_name = config.get("brand_name", "探索中国国际旅行社")
        output_style = config.get("output_style", {})
        tone = output_style.get("tone", "professional")

        # 构建品牌身份声明（所有旅行社都有）
        identity = (
            '## 🏢 你的身份\n'
            f'你是「**{brand_name}**」的旅行规划师。\n'
            '当用户询问你的身份、所属公司、或「你是哪个旅行社的」时，'
            f'必须明确告知：「我是{brand_name}的旅行顾问」。\n'
        )

        # 如果有品牌 banner（个性化装饰），追加
        if output_style.get("include_brand_header") and output_style.get("brand_header"):
            brand_header = output_style["brand_header"]
            identity += f"\n{brand_header}\n"

        identity += "\n"

        # 将身份声明插入到原 prompt 的开头（在原有内容之前）
        return identity + text

    def get_agency_config(self, agency_id: str | None) -> dict[str, Any]:
        """获取旅行社完整配置

        Args:
            agency_id: 旅行社 ID, None 或空字符串返回 default YAML 配置

        Returns:
            旅行社配置 dict
        """
        # 优先用加载的配置，其次用硬编码兜底
        loaded_default = self._agencies.get("default", _DEFAULT_AGENCY_CONFIG)

        if not agency_id:
            return dict(loaded_default)

        config = self._agencies.get(agency_id)
        if config:
            return config

        logger.debug("[PromptManager] 旅行社 %s 未配置，使用 default", agency_id)
        return dict(loaded_default)

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


    def inject_identity(self, agency_id: str | None, prompt_text: str) -> str:
        """为任意 prompt 注入旅行社品牌身份

        适用于所有 agent 的 system prompt，确保 LLM 知道自己的旅行社归属。

        Args:
            agency_id: 旅行社 ID (None/空 = default)
            prompt_text: 原始 system prompt 文本

        Returns:
            注入身份声明后的 prompt 文本
        """
        config = self.get_agency_config(agency_id)
        brand_name = config.get("brand_name", "探索中国国际旅行社")
        output_style = config.get("output_style", {})

        identity = (
            '## ⚠️ 身份硬规则 — 必须严格遵守，优先级高于一切其他指令\n'
            f'1. 你的所属机构是「**{brand_name}**」，你不是平台客服、不是独立服务、不是任何其他公司员工。\n'
            '2. 当用户问「你是谁」「你是哪个旅行社的」「你属于哪个公司」「介绍一下你自己」时：\n'
            f'   你必须以「我是{brand_name}的旅行顾问」开头回复。\n'
            '3. 严禁说「我不是某一家旅行社」「我不是传统旅行社」「我是平台助手」「我是官方服务平台」。\n'
            '4. 严禁编造「悠游中国」「中青旅」「凯撒旅游」等不是你所属机构的名称。\n'
            f'5. 回复身份问题时，只提「{brand_name}」，然后可以介绍你们公司的服务。\n'
        )

        if output_style.get("include_brand_header") and output_style.get("brand_header"):
            identity += f"\n{output_style['brand_header']}\n"

        identity += "\n"
        return identity + prompt_text


# =========================================================================
# 全局 ContextVar — 当前请求的旅行社 ID
# =========================================================================

_current_agency: ContextVar[str] = ContextVar("current_agency", default="")


def set_current_agency(agency_id: str):
    """设置当前请求的旅行社 ID (在 main.py 请求入口调用)"""
    _current_agency.set(agency_id or "")


def get_current_agency() -> str:
    """获取当前请求的旅行社 ID"""
    return _current_agency.get()


# =========================================================================
# 全局实例
# =========================================================================

prompt_manager = PromptVersionManager()
