# 部署（给评审用）

目标：把一个**公网 HTTPS 地址 + 评审账号**交给大赛评委。
本机开发不需要这些步骤——没有 `auth.json` 时系统默认**不启用登录**。

## 一、准备

- Linux 服务器（Ubuntu 22.04 / Debian 12 均可），1 核 2G 起步
- Python 3.10+
- Node.js 22+（只在构建前端时需要）
- 一个 DeepSeek API 密钥（建议单独开户、设额度上限）

## 二、安装

```bash
git clone https://github.com/xunzhekafei/myagent.git
cd myagent
python3 -m venv .venv
.venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-web.txt
cd frontend && npm ci && npm run build && cd ..
```

**不装** `requirements-speech.txt`：语音依赖约 2.3 GB、模型 1.6 GB；不装时
纯语音会话自动隐藏，文字面试完全正常。评审先用文字模式即可。

## 三、建评审账号

```bash
.venv/bin/python -m backend.auth add reviewer
# 交互式输入密码（至少 6 位）
.venv/bin/python -m backend.auth list
```

可以建多个账号。账号写在 `.web-data/auth.json`，**不会进 git**。

## 四、启动

```bash
export ANTHROPIC_API_KEY="你的密钥"
export WEB_ALLOWED_HOSTS="你的域名或隧道地址"
.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

可选环境变量：

| 变量 | 作用 |
| --- | --- |
| `AUTH_SECRET` | 签名登录 cookie 的密钥；不设会自动生成 `.web-data/auth_secret` |
| `AUTH_TTL_DAYS` | 登录有效期，默认 7 天 |
| `WEB_ALLOWED_HOSTS` | 允许的 Host，逗号分隔；公网部署**必须**加上域名/隧道地址 |
| `WEB_ALLOWED_ORIGINS` | 额外的跨源来源；同源请求自动放行，一般不用设 |

用 systemd 托管（示例）：

```ini
[Unit]
Description=Interview Studio
After=network.target

[Service]
WorkingDirectory=/opt/myagent
Environment=ANTHROPIC_API_KEY=你的密钥
Environment=WEB_ALLOWED_HOSTS=你的域名
ExecStart=/opt/myagent/.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000
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
- [ ] HTTPS 下点麦克风能弹出授权
- [ ] `git status` 干净，密钥和账号文件都没进仓库

## 七、安全

- `AUTH_SECRET` 泄露等于任何人都能伪造登录 cookie；用长随机串，不要提交
- API 密钥只放在服务器环境变量里，不要写进代码或前端
- 给 DeepSeek 密钥设额度上限，防止被刷
- 评审结束后可以删除 `.web-data/auth.json` 或直接停服务
