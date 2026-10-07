# -*- coding: utf-8 -*-
"""
Agent Decisions Dashboard - Configuration Manager
通用项目配置加载器与校验器
"""

import os
import json
import copy
from pathlib import Path
from typing import Dict, Any

DEFAULT_CONFIG: Dict[str, Any] = {
    "project_name": "Agent Decisions Dashboard",
    "project_subtitle": "Human-Agent Collaborative Governance & Decision Ledger",
    "brand_logo": "AD",
    "brand_icon": "⚖️",
    "host": "127.0.0.1",
    "port": 8765,
    "decisions_dir": "decisions",
    "database_path": "decisions.db",
    "metadata_json_path": "decisions/metadata.json",
    "doc_data_json_path": "doc_data.json",
    "git_commit": {
        "enabled": True,
        "commit_prefix": "feat(decision)",
        "co_author": "",
        "include_user_opinion": True,
        "include_agent_reply": True
    },
    "categories": {
        "objects": ["核心架构", "前端界面", "后端服务", "存储层", "DevOps"],
        "functions": ["设计规范", "API协议", "安全策略", "性能调优", "运维部署"]
    },
    "lifecycle_states": [
        {
            "id": "decided",
            "name": "已决策",
            "badge": "🟢 已决策",
            "badge_class": "badge-decided",
            "description": "本轮已有明确决定；是否同意与实现状态分别记录"
        },
        {
            "id": "discussing",
            "name": "待讨论",
            "badge": "🟡 待讨论",
            "badge_class": "badge-discussing",
            "description": "方向基本明确，技术细节、参数或数据结构待推敲"
        },
        {
            "id": "pending",
            "name": "待决策",
            "badge": "🔴 待决策",
            "badge_class": "badge-pending",
            "description": "存在方案选型、卡点或分歧，等待明确拍板"
        },
        {
            "id": "deferred", "name": "推迟再议", "badge": "⏳ 推迟再议",
            "badge_class": "badge-discussing", "description": "按原话中的时间或条件继续；同意结论独立保留"
        },
        {
            "id": "superseded", "name": "已被替代", "badge": "📦 已被替代",
            "badge_class": "badge-superseded", "description": "由新议题接替；原结论仅供追溯"
        }
    ]
}

class Config:
    def __init__(self, data: Dict[str, Any], base_dir: Path):
        self._data = data
        self.base_dir = base_dir

    @property
    def project_name(self) -> str:
        return self._data.get("project_name", DEFAULT_CONFIG["project_name"])

    @property
    def project_subtitle(self) -> str:
        return self._data.get("project_subtitle", DEFAULT_CONFIG["project_subtitle"])

    @property
    def brand_logo(self) -> str:
        return self._data.get("brand_logo", DEFAULT_CONFIG["brand_logo"])

    @property
    def brand_icon(self) -> str:
        return self._data.get("brand_icon", DEFAULT_CONFIG["brand_icon"])

    @property
    def host(self) -> str:
        return os.environ.get("AGENT_DASHBOARD_HOST", self._data.get("host", "127.0.0.1"))

    @property
    def port(self) -> int:
        env_port = os.environ.get("AGENT_DASHBOARD_PORT")
        if env_port:
            try:
                return int(env_port)
            except ValueError:
                pass
        return int(self._data.get("port", 8765))

    @property
    def decisions_dir(self) -> Path:
        p = Path(self._data.get("decisions_dir", DEFAULT_CONFIG["decisions_dir"]))
        return p if p.is_absolute() else (self.base_dir / p).resolve()

    @property
    def database_path(self) -> Path:
        p = Path(self._data.get("database_path", DEFAULT_CONFIG["database_path"]))
        return p if p.is_absolute() else (self.base_dir / p).resolve()

    @property
    def metadata_json_path(self) -> Path:
        p = Path(self._data.get("metadata_json_path", DEFAULT_CONFIG["metadata_json_path"]))
        return p if p.is_absolute() else (self.base_dir / p).resolve()

    @property
    def doc_data_json_path(self) -> Path:
        p = Path(self._data.get("doc_data_json_path", DEFAULT_CONFIG["doc_data_json_path"]))
        return p if p.is_absolute() else (self.base_dir / p).resolve()

    @property
    def git_commit(self) -> Dict[str, Any]:
        return self._data.get("git_commit", DEFAULT_CONFIG["git_commit"])

    @property
    def git_commit_enabled(self) -> bool:
        return bool(self.git_commit.get("enabled", True))

    @property
    def categories(self) -> Dict[str, Any]:
        return self._data.get("categories", DEFAULT_CONFIG["categories"])

    @property
    def lifecycle_states(self) -> list:
        return self._data.get("lifecycle_states", DEFAULT_CONFIG["lifecycle_states"])

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


def load_config(config_path: Path = None, base_dir: Path = None) -> Config:
    """显式配置的相对路径以配置目录为基准；坏配置必须中止。"""
    if base_dir is None:
        base_dir = Path(config_path).resolve().parent if config_path is not None else Path.cwd()

    cfg_file = config_path or (base_dir / "dashboard.config.json")
    loaded_data = copy.deepcopy(DEFAULT_CONFIG)

    if config_path is not None and not Path(config_path).is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    if cfg_file and Path(cfg_file).exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                user_data = json.load(f)
                if not isinstance(user_data, dict):
                    raise ValueError("配置根节点必须为对象")
                loaded_data.update(user_data)
        except (OSError, ValueError) as e:
            raise ValueError(f"加载配置文件 {cfg_file} 失败: {e}") from e

    return Config(loaded_data, base_dir)
