---
title: Configuration Guide
description: Configuration options, environment variables, and deployment best practices for Agent Decisions Dashboard.
---

::: warning AI Translation Notice
This document was translated by an AI language model. In case of any discrepancies or ambiguities, please refer to the [original Chinese documentation](/docs/configuration) as the authoritative reference.
:::

# Configuration Guide

### Primary Configuration

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8080,
    "cors_allowed_origins": ["http://localhost:5173"]
  },
  "storage": {
    "engine": "sqlite",
    "database_url": "sqlite://agent_audit.db",
    "retention_days": 30
  },
  "telemetry": {
    "enable_live_events": true,
    "buffer_capacity": 4096
  }
}
```

---

## Production Recommendations

1. **Environment Variable Protection**: Never commit real API keys or sensitive credentials into Git repositories.
2. **Graceful Shutdown & Timeouts**: Set appropriate timeout constraints on long-running processes to prevent orphan executions.
3. **Continuous Monitoring**: Combine console logs and health telemetry to monitor service uptime and operational status.
