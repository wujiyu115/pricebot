# PriceBot

国内金价监控推送系统 —— 上金所 **AU9999 / 黄金T+D** 实时监控、规则告警、Bark 推送。

## 功能

- **实时行情**：新浪财经行情源（上金所现货/延期，含买卖盘），上金所官网日K源（历史走势/收盘监控）
- **规则告警**：上/下穿阈值、窗口涨跌幅%、窗口涨跌额；连续确认防抖 + 冷却时间
- **推送渠道**：Bark（iOS，优先）/ **Ntfy（开源 APP 弹窗，Android 首选）** / Telegram / 飞书 / **钉钉 / 企业微信机器人（备选）** / 通用 Webhook、Telegram、飞书、钉钉、通用 Webhook，支持渠道级测试推送
- **数据源可动态扩展**：
  - 适配器注册表（`app/core/sources/`），新增数据源 = 新模块 + `@register`
  - `generic_http` 通用源：JSONPath / 正则提取，**免代码**接入任意价格接口
- **WebUI**：仪表盘（金价卡片 + 90 日走势 + 最近告警）、标的管理、规则管理、渠道管理、系统设置
- **配置两层**：默认层（镜像内）+ 用户稀疏覆盖层（`config/user_settings.json`），乐观锁并发写

## 快速开始

```bash
# 本地开发
pip install -r requirements.txt
python main.py --host 0.0.0.0 --port 6106

# 前端
cd frontend && bun install && bun run build   # 产物由后端伺服

# Docker
docker run -d --name pricebot -p 6106:6106 \
  -v ./config:/app/config -v ./data:/app/data \
  wujiyu115/pricebot:latest
```

打开 `http://127.0.0.1:6106`，在「推送渠道」页配置 Bark 设备 Key 并启用，在「告警规则」页添加规则即可。

## 监控标的（默认）

| 标的 | 数据源 | 代码 |
| --- | --- | --- |
| 上金所黄金9999 | sina | `SGE_AU9999` |
| 上金所黄金T+D | sina | `SGE_AUTD` |
| A股股票/指数 | sina_stock | `sh600519` / `sz000001` / `sh000001`(上证指数) |
| 商品期货主力连续 | sina_futures | `SC0`(原油) / `RB0`(螺纹) / `CU0`(铜) / `I0`(铁矿) / `AU0`(沪金) |
| 加密货币（技术演示） | binance | `BTCUSDT` / `ETHUSDT` / `SOLUSDT` |
| 电商商品售价 | generic_http | 任意服务端渲染价格的商品页/价格 API（URL + JSONPath/正则） |

加密货币走 Binance 官方只读公共镜像（data-api.binance.vision），7x24 交易、涨跌幅按 24h 开盘基准。

**电商商品监控**（generic_http 源，WebUI 标的表单选择「通用 HTTP 数据源」后填 URL + 提取规则）：

```json
{
  "name": "Redmi 10X 4G",
  "source": "generic_http",
  "symbol": "MI_10000229",
  "interval_seconds": 600,
  "extra": {
    "url": "https://www.mi.com/buy/detail?product_id=10000229",
    "regex": "\"price\":\"([0-9.]+)\""
  }
}
```

- JSON 接口填 `json_path`（如 `data.price`），HTML/文本填 `regex`（第一个捕获组），支持自定义 headers（带 Cookie 调用三方价格接口）
- 实测可用：小米商城（服务端渲染、价格未混淆）；**京东/淘宝商品页价格由 JS 登录后加载且服务端混淆**（`"price":"4??"`），不支持直接抓取——请改用带 Cookie 的价格接口或三方比价 API
A股代码规则：`sh`/`sz`/`bj` + 6 位数字；指数 `sh000xxx`/`sz399xxx`（单位:点）。涨跌幅按昨收自动计算。
期货代码规则：品种 + 0（主力连续），如 `SC0`/`RB0`/`CU0`/`HC0`/`J0`/`M0`/`TA0`/`AU0`/`AG0`；涨跌幅按昨结算计算；单位按品种映射（原油=元/桶、金=元/克、银=元/千克、其余=元/吨，可用标的 extra.unit 覆盖）。

## 项目结构

```
app/
├── core/
│   ├── config/     # 两层配置（layering 纯函数 + ConfigManager）
│   ├── sources/    # 数据源适配器注册表（sina / sge_daily / generic_http）
│   ├── monitor/    # 引擎、规则求值、SQLite 存储、交易时段、后台 loop
│   └── notify/     # 推送渠道适配器（bark / telegram / feishu / dingtalk / webhook）
├── server/         # FastAPI 路由 + SPA 挂载
└── models/         # pydantic schemas
frontend/           # React 18 + Vite + Tailwind + Radix UI
config/             # default_settings.json（默认层，进 git）
data/               # targets/rules SQLite（运行数据，持久卷）
tests/              # pytest（规则纯函数 / fake 网络层 / API 端到端）
```

## 开发

```bash
python3 -m pytest tests/ -q     # 82 个用例
python3 -m ruff check app/ tests/
cd frontend && ./node_modules/.bin/tsc --noEmit -p tsconfig.json
```

## License

MIT
