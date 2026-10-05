// Offline fallback data
window.DASHBOARD_DEFAULT_DATA = {
  "config": {
    "project_name": "Agent Decisions Dashboard",
    "project_subtitle": "Human-Agent Collaborative Governance & Decision Ledger",
    "brand_logo": "AD",
    "brand_icon": "⚖️"
  },
  "topics": [
    {
      "id": "adr-001-architecture-style",
      "title": "系统架构选型：轻量解耦与状态集中治理",
      "object": "核心架构",
      "function": "设计规范",
      "lifecycle_status": "decided",
      "decision_status": "已定案",
      "impl_status": "已完成",
      "priority": "最高",
      "summary": "采用单议题独立 Markdown 文件存储讨论细节，结合 SQLite 与 Git 自动提交实现生命周期闭环治理。",
      "rounds_count": 2,
      "last_user_opinion": "确认方案，必须确保零外部重量级依赖，支持单机快速启动与 Git 离线回溯。",
      "last_agent_reply": "已实现基于 Python 标准库的轻量服务器与自动化语义提交引擎。"
    }
  ],
  "settled_decisions": [],
  "open_questions": [],
  "changelog": []
};
