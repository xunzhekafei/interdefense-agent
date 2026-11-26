# 部署（给评审 / 试用用）

> 本文档对应 `interdefense-agent`（答辩复盘）版本；旧版 `myagent` 的部署步骤仍基本适用。

目标：把一个**公网 HTTPS 地址 + 评审账号**交给大赛评委。
本机开发不需要这些步骤——没有 `auth.json` 时系统默认**不启用登录**。

## 一、准备

- Linux 服务器（Ubuntu 22.04 / Debian 12 均可），1 核 2G 起步
- Python 3.10+
- Node.js 22+（只在构建前端时需要）
- 一个模型 API 密钥：默认 DeepSeek；如需项目级预算控制，可切到 Kimi（见「额度控制」）

## 二、安装

```bash
git clone https://github.com/xunzhekafei/interdefense-agent.git
cd interdefense-agent
python3 -m venv .venv
.venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-lock.txt
cd frontend && npm ci && npm run build && cd ..
```

语音是可选功能，两种装法二选一：

- **只用文字**：不装任何语音依赖。`/api/health` 里 `speech.asr=false`，麦克风按钮不出现，
  其余功能完全正常。
- **要语音（CPU，推荐）**：只装一个包，**不要**装 `requirements-speech.txt` 里的 CUDA 依赖：

  ```bash
  .venv/bin/pip install "faster-whisper>=1.2,<2"
  ```

  启动时设 `WHISPER_DEVICE=cpu`、`WHISPER_MODEL=small`（约 460MB，首次使用
  自动下载；国内先 `export HF_ENDPOINT=https://hf-mirror.com`）。
  2C2G 内存偏紧：模型常驻约 500MB–1GB，报告生成时并发高，建议试用期同时在线人数控制在 3–5 人。

## 三、建评审账号

```bash
.venv/bin/python -m backend.auth add reviewer
# 交互式输入密码（至少 6 位）
.venv/bin/python -m backend.auth list
```

可以建多个账号。账号写在 `.web-data/auth.json`，**不会进 git**。

## 四、启动

```bash
export PROVIDER="deepseek"             # 默认值，写出来只是让配置一目了然
export ANTHROPIC_API_KEY="你的密钥"    # DeepSeek 使用 x-api-key；切到 Kimi 时自动改用 Bearer
export WEB_ALLOWED_HOSTS="你的域名或隧道地址"
.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

可选环境变量：

| 变量 | 作用 |
| --- | --- |
| `PROVIDER` | `deepseek`（默认）/ `kimi` / `custom` |
| `MODEL` | 默认 `claude-haiku-4-5`；一般不用改 |
| `REASONING_EFFORT` | Kimi 推理深度（仅 `PROVIDER=kimi` 时生效），默认 `low`；报告质量不够时设 `high`。若接口报 400 且提到 `output_config`，设 `off` 关闭该字段 |
| `WORKFLOW_MAX_PARALLEL` | 报告并发，默认 8。Kimi 未到 Tier1 时并发只有 1，设 `1` 避免 429 |
| `AUTH_SECRET` | 签名登录 cookie 的密钥；不设会自动生成 `.web-data/auth_secret` |
| `AUTH_TTL_DAYS` | 登录有效期，默认 7 天 |
| `WEB_ALLOWED_HOSTS` | 允许的 Host，逗号分隔；公网部署**必须**加上域名/隧道地址 |
| `WEB_ALLOWED_ORIGINS` | 额外的跨源来源；同源请求自动放行，一般不用设 |
| `WHISPER_DEVICE` | `cpu` / `cuda` / `auto`（默认）。没有显卡就用 `cpu` |
| `WHISPER_MODEL` | 默认 CPU 下用 `small`；有显卡可用 `large-v3-turbo`（约 1.6GB，中文更准） |
| `HF_ENDPOINT` | 首次下载模型走镜像：`https://hf-mirror.com` |

### 登录与会话安全

- 登出会把账号的 token 版本号 +1，已签发但未过期的 cookie 立即作废（同账号其它设备也会下线）；
  只删除浏览器 cookie 已不足以保证安全。
- 连续登录失败按「客户端 IP」与「IP + 用户名」各计一次：第 5 次起锁 60 秒，之后逐次翻倍，
  上限 15 分钟。重启服务会清零计数。经 nginx / Tunnel 反代后 `client.host` 通常是
  127.0.0.1，限流会退化为全局计数——单用户评审场景可接受。
- 所有 HTTP 响应带 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`
  与 CSP；HTTPS 请求（或 `X-Forwarded-Proto: https`）额外带 HSTS。
  `/docs` 豁免 CSP，因为 Swagger UI 从 CDN 加载。nginx 自己加同名头时后端不覆盖。

用 systemd 托管（示例）：

```ini
[Unit]
Description=InterDefense Studio
After=network.target

[Service]
WorkingDirectory=/opt/interdefense-agent
Environment=PROVIDER=deepseek
Environment=ANTHROPIC_API_KEY=你的密钥
Environment=WEB_ALLOWED_HOSTS=你的域名
Environment=WHISPER_DEVICE=cpu
Environment=WHISPER_MODEL=small
Environment=HF_ENDPOINT=https://hf-mirror.com
ExecStart=/opt/interdefense-agent/.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

## 五、HTTPS（二选一）

麦克风权限和 WebSocket 都要求安全上下文，**不能用纯 HTTP 给评审**。

### A. 没有域名：Cloudflare Tunnel（推荐，最快）

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
./cloudflared tunnel --url http://127.0.0.1:8000
```

它会打印一个 `https://xxx.trycloudflare.com`，HTTPS 和 WebSocket 都能用。
把这个域名加到 `WEB_ALLOWED_HOSTS` 后重启服务。

> 临时地址每次重启都会变。比赛期间可以 `cloudflared tunnel login` 建命名隧道
> 固定域名（仍然免费，需要 Cloudflare 账号）。

### B. 有域名：nginx + Let's Encrypt

```bash
sudo apt install nginx certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名
```

nginx 关键片段（WebSocket 必须加 Upgrade 头）：

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## 六、部署前检查

- [ ] `curl https://你的地址/api/health` 返回 200
- [ ] 浏览器打开地址 → 出现登录页
- [ ] 用评审账号登录 → 能看到界面
- [ ] 界面里**没有**学校、姓名、指导教师
- [ ] `/api/sessions` 里**没有**测试记录（有就「立即结束 → 删除记录」清掉）
- [ ] 手机打开同一地址，能「添加到主屏幕」，图标打开后无地址栏
- [ ] 上传一份 `.docx` 讲稿，能正确解析出段落
- [ ] 答辩场景跑一场：摘要卡 → 追问 → 报告（四维是答辩四维）
- [ ] HTTPS 下点麦克风能弹出授权；说话后转写结果能填进输入框
- [ ] `git status` 干净，密钥和账号文件都没进仓库

## 七、额度控制（可选）

默认使用 DeepSeek：只能给**账户**充值，不能给单个 key 设上限。
如果需要给评审单独限预算，可以切到 Kimi（`PROVIDER=kimi`），按项目设日/月预算：

1. 先完成个人实名认证（未认证只能有 1 个项目、10 个 key，分不出评审项目）
2. 控制台顶部切到新项目（例如 `myagent-reviewer`）
3. 项目设置 → 项目预算/限速设置 → 日预算、月预算（例如 ¥10/天、¥50/月）
4. 在**这个项目下**创建 API Key，填到服务器环境变量

并发也按**累计充值**分档：Tier0（¥0）只有 1 路并发、3 RPM，报告 workflow 的
8 路并行会直接 429。**至少充值 ¥50 到 Tier1**（15 路并发）；不想充值就把
`WORKFLOW_MAX_PARALLEL` 设成 `1`，代价是报告变慢。项目预算只限制花多少，
不影响余额和并发档位。

达到预算后该项目下所有请求都会被拒绝，其他项目不受影响。
注意计费有约 10 分钟延迟，预算别设得刚好够用，留 20–30% 余量。

## 八、安全

- `AUTH_SECRET` 泄露等于任何人都能伪造登录 cookie；用长随机串，不要提交
- API 密钥只放在服务器环境变量里，不要写进代码或前端
- 如使用 Kimi，给项目设日/月预算，防止链接被刷
- 评审结束后可以删除 `.web-data/auth.json` 或直接停服务

## 九、备份与恢复

数据库在 `.web-data/interviews.sqlite3`（WAL 模式），账号文件在同目录。
**不要直接 `cp` 正在写入的数据库**——可能拿到半写状态。用脚本的一致快照：

```bash
python tools/backup.py                    # 生成 .web-data/backups/<时间戳>/
python tools/backup.py --keep 14          # 只保留最近 14 份
```

每份备份包含 `interviews.sqlite3`、`auth.json`、`auth_secret`（存在时）。
POSIX 上备份目录自动设为 0700、文件 0600；`.web-data` 已被 gitignore，
不要把备份上传到仓库或网盘。

恢复前**必须先停服务**，否则运行中的进程会继续写旧库：

```bash
sudo systemctl stop interdefense
python tools/backup.py --restore .web-data/backups/20261110-120000
sudo systemctl start interdefense
```

脚本会先做 `PRAGMA integrity_check`，校验失败拒绝恢复；并把当前库另存为
`interviews.sqlite3.pre-restore-<时间戳>`，恢复错了还能回退。
旧的 `-wal/-shm` 会被移除，因为它们属于恢复前的库。
