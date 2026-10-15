# AGENTS.md

## 项目概述

PriceBot：国内金价（上金所 AU9999 / 黄金T+D）监控推送系统。技术栈与同门 StreamCap 一致：FastAPI + 后台线程事件循环 + React18/Vite/Tailwind/Radix SPA（后端伺服 dist）。

## 验证层级（真实环境，禁止只跑类型检查就宣布完成）

1. **模块级**：`python3 -m pytest tests/ -q`（82 用例：规则求值/防抖状态机是纯函数、fake 网络层见 `tests/helpers.py`——FakeSource/FakeNotifier 注册表注入，不打真网）
2. **API 级**：`python3 main.py --port 6106` 起服务，curl 走真实 HTTP；错误路径也要测（不存在的 id → 404、未知 source → 422、settings 版本冲突 → 409）
3. **UI 级（前端改动必做）**：Playwright headless Chromium 走真实交互。chromium 可执行文件用 `~/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`（`launch(executable_path=...)`，包内要求的 headless_shell 版本不在缓存里）。参考脚本模式：`/tmp/pricebot_ui_test.py`（已跑通全链路：仪表盘渲染真实金价 → 规则对话框创建 → 触发告警 → 删除联动，原生 confirm 用 `page.on("dialog", ...)`）

### 已知可用的真实测试数据

- 新浪 `SGE_AU9999` / `SGE_AUTD` 夜盘长期有效；字段布局见 `app/core/sources/sina.py` 顶部注释（**2026-10 实测**：f11=最新价、f9/f10=买一/卖一、f5=昨收、f16=时间戳）
- 上金所官网 `POST https://www.sge.com.cn/graph/Dailyhq`，form `instid=Au99.99`（注意 URL 编码：`Au(T+D)` 必须编码成 `Au%28T%2BD%29`，query string 里 `+` 会变空格）
- SGE 交易时段参考 `app/core/monitor/trading_hours.py`（夜盘跨零点归属前一晚）

## 项目特有陷阱

- **跨 event loop**：监控引擎跑在后台线程的 loop；API 端点操作引擎一律 `services.run_bg(coro)`（内部 run_coroutine_threadsafe + wrap_future），别直接 await 引擎协程
- **配置引用脱钩**：`apply_user_patch` 走 `deep_merge` 生成**新的嵌套 dict 对象**，构造时按引用捕获配置 dict 会与新配置脱钩（已踩过：渠道启用了但引擎看不见）。引擎/通知管理器必须用 **getter 惰性读取**（`MonitorEngine._get_config` / `NotificationManager._get_notify_config`）
- **配置稀疏性**：只有 `user_settings.json`（用户层）落盘；默认层 `config/default_settings.json` 进 git。`PUT /api/settings` 要带 `config_hash` 版本号，不匹配 409
- **cooldown=0 是合法值**（无冷却），反序列化禁用 `or` 短路取默认（已修过 `Rule.from_dict` 的坑）
- **触发后 streak 归零**：防抖语义是触发后需**重新**连续确认 confirm_count 次才会再次触发（冷却是另一道闸）
- **sqlite 是阻塞 IO**：API 读历史走 `asyncio.to_thread`；写只在后台 loop 线程
- **Bark 无 device_keys 时 send 返回 ok=False**（不算异常）；测试推送需先启用渠道（`PUT /api/channels/{name}` enabled=true）
- **vendored UI 组件**（`frontend/src/components/ui/*`，拷贝自 StreamCap 的 shadcn 组件）：`.pi-lens.json` 已 ignore；以 `tsc -b && vite build` 为准。已知 pi-lens turn-end 探针会按 `/home/ejoy/package.json`（家目录全局清单）解析前端 import，与 frontend/node_modules 无关——若报 Cannot find module 'sonner' 等，先查 `/home/ejoy/node_modules` 是否缺包（家目录是 bun 管理：改完 `cd /home/ejoy && bun install` 复核；**别用 npm 在家目录装包**，会按陈旧 package-lock 修剪，曾误删 sharp/onnxruntime-node）

## Unraid 生产容器更新流程（目标机 tank）

- SSH：`ssh -i ~/.ssh/id_rsa_nas root@192.168.31.139`
- 镜像 `wujiyu115/pricebot:latest`，模板 `/boot/config/plugins/dockerMan/templates-user/my-pricebot.xml`
- 持久化：`/mnt/user/appdata/pricebot/config:/app/config`（user_settings.json）、`data`（SQLite+targets/rules）、`logs`；端口 `6106`
- 流程：push main → CI（`.github/workflows/docker.yml` 多架构构建 + 冒烟测试）→ NAS `docker pull` → **严禁裸 docker run**，用 `/usr/local/emhttp/plugins/dynamix.docker.manager/scripts/rebuild_container pricebot`（保留 template 绑定）→ `docker start pricebot` → 自检：
  ```
  docker ps --filter name=pricebot   # Up ... (healthy)
  curl http://localhost:6106/api/dashboard   # engine.running=true 且 quotes 有真实价格
  docker logs --tail 30 pricebot
  ```
- 回滚：CI 每次推 `:{github.sha}` tag，改模板 `<Repository>` 指定旧 sha 再 rebuild_container
- 重建前确认无进行中的轮询（监控引擎随时可重启，无状态丢失风险——状态都在 SQLite/JSON 里）

## 配置分层速查

`GET /api/settings` 三个字段：`default_settings`（镜像默认层）、`user_overrides`（稀疏用户层）、`user_settings`（合并生效值）。新增设置项往 `config/default_settings.json` 加键即可，不会顶掉生产已改过的用户值。
