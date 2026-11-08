---
title: FAQ & Troubleshooting
description: Frequently asked questions and diagnostics for Agent Decisions Dashboard.
---

::: warning AI Translation Notice
This document was translated by an AI language model. In case of any discrepancies or ambiguities, please refer to the [original Chinese documentation](/docs/faq) as the authoritative reference.
:::

# FAQ & Troubleshooting

Common questions and answers regarding daily usage and integration:

### Q: How does it capture agent decision steps?

**A**: It integrates via lightweight OpenTelemetry-compatible middleware or WebSocket event streams emitted by the agent runner.

### Q: Does it support offline local playback?

**A**: Yes. Exported JSON trace files can be directly loaded into the dashboard for offline analysis without any running server.


---

## General Troubleshooting Steps

1. **Verify Runtime Versions**: Ensure Node.js, Python, Rust, or browser versions meet minimum compatibility requirements.
2. **Check Diagnostic Logs**: Review console output and error logs for informative stack traces and line numbers.
3. **Submit Issue Feedback**: If you discover an underlying bug, please open an issue on the GitHub repository with a reproducible test case.
