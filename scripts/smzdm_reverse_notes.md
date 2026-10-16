# SMZDM App API 逆向笔记

逆向目标：`com.smzdm.client.android`（什么值得买）v11.1.95，
恢复 App 内部 API 的签名算法与公共参数，绕过企业开放平台注册。
结论于 2026-10-16 通过真实 HTTP 调用验证（`error_code=0` + 真实好价数据）。

PoC 脚本：`smzdm_sign_poc.py`（同目录，仅 stdlib 依赖）。

## 1. 产物与工具链

| 产物 | 位置 | 工具 |
|------|------|------|
| APK（103MB） | `/tmp/smzdm.apk` | 应用汇 appchina.com（JS 渲染页，Playwright 抓下载按钮 onclick） |
| 全量反编译源 | `/tmp/smzdm_src/sources`（26614 类） | jadx CLI v1.5.1（`/tmp/jadx_tool`） |
| native 密钥库 | `/tmp/smzdm_lib/.../liblib_zdm_key.so` | unzip + capstone |

获取 APK 的网络现实（2026-10 实测）：apkpure/apkmirror/apkcombo/apk.tw 全部超时，
coolapk 404，官网 404；**应用汇可达**（下载链 302 到 qn.yingyonghui.com 时效签名 URL）。

## 2. 关键类索引（混淆名 → 职责）

| 反编译路径 | 职责 |
|------------|------|
| `mf/C6052a.java` | OkHttp 签名拦截器（算法主体） |
| `mf/C6053b.java` | OkHttp Cookie 注入拦截器（`S0.n(true)`） |
| `lf/c.java` | 主 OkHttpClient 构建处（注册上述两个拦截器） |
| `com/smzdm/client/base/utils/C4717r0.java` | MD5 hex 工具（`.a(String)`） |
| `com/smzdm/client/base/utils/ZDMKeyUtil.java` | native 密钥加载（`lib_zdm_key`） |
| `com/smzdm/client/base/utils/S0.java` | 公共参数/Cookie/UA 构造 |
| `mf/C6054c.java` | `time` 参数（服务端时间同步，毫秒） |
| `com/smzdm/client/base/utils/o1.java` | `v` 参数（App 版本） |
| `lf/g.java` | 业务层请求入口（`b()` → POST form） |

注意：SMZDM 自有代码全部混淆在 `com.byazt.***`（3655 文件），但**公共参数/签名
链路在未混淆的 `com.smzdm.client.base.utils` 与 `mf` 包**，直接可读。
新版 host 是 `app-api / homepage-api / user-api / haojia-api ... smzdm.com`，
旧文档的 `api.smzdm.com` 已废弃（404）。

## 3. 签名算法（已验证）

```python
sign = md5("&".join(f"{k}={v}" for k in sorted(params) if v not in (None, ""))
        + "&key=" + KEY).hexdigest().upper()   # 拼接后整体 replace(" ", "")
```

- KEY（v11.1.95）= `apr1$AwP!wRRT$gJ/q.X24poeBInlUJC`
- 公共参数（GET 入 query / POST 入 form body，**全部参与签名**）：
  `f=android`、`v=<App版本>`、`weixin=<0/1>`、`time=<13位毫秒>`、
  `basic_v=<0/1>`、`zhuanzai_ab=<ab组，可空>`
- `s-api.smzdm.com` 主机额外加 `sid`
- `time` 服务端容忍 ±5 分钟；同步接口 `app-api.smzdm.com/get_server_time`
  （无签名请求 404，但 404 也带 `Date` 头，取毫秒即可）

## 4. 请求头要求

- **Cookie**（`C6053b` 注入，缺 `device_id` 直接被拒）：
  `device_id=<32位hex>`、`new_device_id`、`smzdm_id`、`f`、`v` 等；
  `device_id` 内容任意（真实 App 是对设备串 MD5，仿造 hex 即通过）
- **User-Agent**：
  `smzdm_android_V{ver} rv:{code} ({model};Android{rel};{lang})smzdmapp`

## 5. 已验证端点与数据结构

### 5.1 App 搜索接口（主路径，适配器默认）

`GET https://s-api.smzdm.com/sou/list_v10`（T1.java 构造，好价 tab）

关键参数：`keyword`（搜索词）、`search_tab=good_price`（好价 tab，
C4169j0：baicai/coupon/haitao 均归一到 good_price）、`limit`/`offset`/
`order`/`page`、`search_source=1`、`sid`（s-api 主机专属：毫秒时间
+4 位随机数，Ng.f.o()）。

响应 `data.rows[]` 混排（yuanchuang 文章/zhiyoushuo 值友说/
**youhui 好价**），好价行字段：

| 字段 | 含义 |
|------|------|
| `article_channel_type` | `youhui` = 好价行（过滤依据） |
| `article_price` | 成交价（活动类条目可为空） |
| `page_price` | 原价（`¥2998` 格式） |
| `publish_date_lt` | 发布时间 Unix 秒（取最新用） |
| `article_mall` | 商城名（**字符串**，与推荐流的 list 结构不同） |
| `article_subtitle` | 副标题（如 `2293.3元（需用券）`） |
| `article_region` / `article_channel_name` | 区域（国内/海淘）/ 子频道 |

任意关键词精确匹配、结果与设备无关（确定，无匹配即真无）；
标题匹配需去空格+小写归一化（`action6` 命中「Action 6」）。

### 5.2 首页好价推荐流（旧路径，extra.mode="home"）

`GET https://homepage-api.smzdm.com/v3/home` →
`data.component[]`（zz_type: circular_banner/hongbao/filter/banner/**list**）→
`component[zz_type=="list"].zz_content[]` 为混排信息流。

好价条目（`article_first_channel_name == "好价"`）字段：

| 字段 | 含义 |
|------|------|
| `article_id` / `article_url` | 条目 ID / 详情页 |
| `article_title` | 标题 |
| `article_price` | 成交价（活动类条目可为空） |
| `article_page_price` | 原价（`¥2599` 格式） |
| `article_discount` | 折扣（`7.4折`） |
| `article_mall` | `[{"article_title": "京东"\|天猫精选\|...}]` |
| `article_date` / `article_channel_name` / `article_region` | 时间 / 子频道（国内/发现/海淘） / 区域 |

## 6. 密钥失效时重新提取（App 升级换 key）

1. **下载新版 APK**：应用汇（见 §1，注意 JS 渲染 + 302 时效链）。
2. **jadx 全量反编译**：确认签名拦截器路径是否仍是 `mf/C6052a.java`
   （grep `put("sign"` / `addQueryParameter`）。
3. **提取 native 密钥**（不需要执行 native，纯静态即可）：
   ```bash
   unzip -o app.apk "lib/arm64-v8a/liblib_zdm_key.so" -d /tmp/smzdm_lib
   readelf -sW liblib_zdm_key.so | grep getDefaultNativeKey   # 记下地址
   ```
   用 python capstone 反汇编该 JNI 函数：它只是 `std::string` 构造返回
   `adrp/add` 指向的 rodata 明文（v11.1.95 时位于 0x215a0）；
   直接按地址读文件偏移即得新 key。
   （ELF vaddr→file offset 映射：遍 LOAD 类型 program header。）
4. 用 `smzdm_sign_poc.py` 换 KEY/VER 重跑验证：`error_code=0` 即成功；
   `error_msg=="device_id 没有赋值"` 说明签名已过、只差 Cookie。

## 7. 集成到 PriceBot 的备注

- 建议源适配器 `app/core/sources/smzdm.py`：签名 + Cookie 每次请求现算
  （time 必须新鲜），解析见 §5；`target.extra` 可放关键词/频道过滤。
  已实现（2026-10-16）：search 主路径 + home 旧路径，168 pytest 全过。
- rate limit 未实测，建议 ≥30s 轮询间隔。
- MD5 是协议要求（防伪签名），集成时不要"修复"为更强哈希。
