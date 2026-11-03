---
name: kimi-api
description: 本项目的默认模型接口——修改 agent、providers 或添加模型调用前先读，避免踩 Kimi 兼容接口的坑
---

# Kimi Anthropic 兼容接口注意事项

默认提供商是 Kimi（`PROVIDER=kimi`），通过 Anthropic 官方 SDK 连接
`https://api.moonshot.cn/anthropic`，与 DeepSeek 的差异集中在 `providers.py`：

1. **鉴权是 Bearer，不是 x-api-key**。用 `ANTHROPIC_AUTH_TOKEN`，或让
   `providers.credentials()` 把 `ANTHROPIC_API_KEY` 转成 `auth_token=`；不要直接传 `api_key=`。
2. **模型名**：当前默认 `kimi-k3.1-pro`。K2 系列从 2026-10-31 起对新用户关闭、年底下线，
   不要在新配置里用 K2 的模型名。
3. **K3.1 Pro 始终思考，没有开关**。不要发 `thinking` 参数；用
   `output_config={"effort": "low"|"high"|"max"}` 控制深度（默认 low，报告质量不够再调高）。
   如果接口报 400 并提到 `output_config`，设 `REASONING_EFFORT=off` 关掉这个字段。
4. **缓存标记放顶层**。`cache_control` 写在 `messages` 里面会被忽略；本项目用顶层字段。
5. **工具函数必须返回字符串**。返回数字或其他类型可能报 400，用 `str()` 或 `json.dumps()`。
6. **多轮工具调用要原样回传 thinking 块**（含 signature），不要删除或改写。
7. **temperature / top_p 不要显式传**：K3.1 Pro 固定 1.0 / 0.95，传别的值会报错。
8. 切回 DeepSeek 用 `PROVIDER=deepseek`；自定义地址（Ollama、代理、国际站）用
   `PROVIDER=custom` 并设置 `ANTHROPIC_BASE_URL`——`PROVIDER=kimi` 时不读这个变量。
