# 慢慢买（Manmanbuy）App 逆向笔记

逆向目标：`com.manmanbuy.bijia`（慢慢买比价）v5.2.41 / vcode 2245，
目标是拿到**商品历史价格**接口，供 PriceBot 做电商商品价监控。

结论于 2026-10-19 通过真实 HTTP 调用验证：`getBiJiaInfo` 免签名直连返回
完整 JSON（title / 当前价 / 历史最低 / 日线曲线 / 商城），慢慢买 web 好价流
里的商品逐个反查 **20/20 命中**。

产物：`app/core/sources/manmanbuy.py`（适配器）+ `tests/test_manmanbuy.py`（45 用例）。

## 1. 产物与工具链

| 产物 | 位置 | 工具 |
|------|------|------|
| APK（102,842,113 B） | `/tmp/mmb.apk`（md5 `ac3122f48db6a04f538c7e089f5de0f7`） | 豌豆荚 |
| RN bundle | APK 内 `assets/index.android.bundle`（11.2MB） | unzip |
| Hermes 反汇编 | `/tmp/mmb_work/mmb.hasm`（**173 MB**） | hermes-dec |
| 函数索引 | `/tmp/mmb_work/func_index.json`（56,977 条） | 自建脚本 |

### 1.1 取 APK 的网络现实（2026-10 实测）

apkpure / apkcombo / apk.tw 超时；coolapk 404；`app.mi.com` 页面正常但显示
「维护中」且 `/download/78674` 重定向回详情页。**豌豆荚可达**：

```
https://www.wandoujia.com/apps/com.manmanbuy.bijia   → /apps/6559910
https://www.wandoujia.com/apps/6559910/download      → 302 →
https://ucdl.25pp.com/fs08/2026/10/16/8/106_4dc8....apk
```

下载后 md5 与豌豆荚公示一致。

### 1.2 Hermes 反编译（Java 路线不可行）

APK 里**只有 1 个 classes.dex（13,876 字节）**——Java 层是空壳，爱加密加固：

```
assets/ijiami.dat (9.3MB)   assets/ijiami.ajm (3.5MB)   assets/IJMDal.Data
assets/signed.bin  assets/af.bin  assets/alauncher.dat  assets/bicon.dat
lib/arm64-v8a/libijmDataEncryption.so   lib/arm64-v8a/libEncryptorP.so
```

真实业务逻辑在 **React Native Hermes bundle**（`assets/index.android.bundle`，
magic `c61fbc03c103191f`，HBC version 90）。jadx 对 Hermes 字节码无能为力。

用 hermes-dec 0.1.8：

```bash
python3 -m pip install hermes-dec
HBC=/home/ejoy/.pyenv/versions/3.12.0/bin        # 注意 PATH：装进 pyenv 3.12
$HBC/hbc-file-parser   index.android.bundle > parsed.txt      # 表格文本，非 JSON
$HBC/hbc-disassembler  index.android.bundle  mmb.hasm          # 173MB，耗时几分钟
```

bundle 头信息：`function_count=56977`、`identifier_count=33704`、
`string_count=56463`、`overflow=169`、`string_storage_size=949006`。

**踩坑**：手写 header / string-table 解析易错（字段布局误判、overflow 表索引越界
直接崩）；直接用 hermes-dec，不要自己啃。

建函数索引（id, name, hasm 行号, offset）后即可按符号定位，例如：

```python
# 找包含 makeSign 定义行的函数
grep -n "String: 'makeSign'" mmb.hasm     # → 209641（PutById 定义点）
```

## 2. 关键符号索引（Hermes 侧）

| 符号 | hasm 位置 | 说明 |
|------|-----------|------|
| `ajaxPost` | L198004 | 统一 POST 封装：`Content-Type: application/x-www-form-urlencoded; charset=utf-8`、`Accept: */*`、`Manmanbuy-RequestId` 头 |
| `makeSign` / `_makeSign` | L209641 / func#4921-4924 | 签名主函数（约 L209500 起） |
| `dealKeyDES` / `encryptDES` / `decryptDES` | func#5414-5416（L222285/305/349） | CryptoJS **DES-ECB + Pkcs7**，key 来自 `keyDES` |
| `keyDES` 常量 | L221186 附近 `PutById` | 固定串 `4d16-0cd3-cf5c-04f9-057e-11c3-9438-ebc0` |
| `RNReactNativeMencryptSign` | func#4920 尾部 | 原生模块：`getToken` / `getDeviceInfo` / `getFixId` |
| `getHistoryTrend` 方法名表 | L198551 | 旧 aspx 通道方法白名单（20 个） |
| `TrendStore` | L197548 | 历史价格业务编排 |

原生库 `libmmbKey.so`（x86_64 4.2MB）导出的 JNI 符号：

```
Java_com_maochunjie_mencryptsign_RNReactNativeMencryptSignModule_getToken
Java_com_maochunjie_mencryptsign_RNReactNativeMencryptSignModule_getDeviceInfo
Java_com_maochunjie_mencryptsign_RNReactNativeMencryptSignModule_getFixId
```

该 .so 的 section header 被大幅裁剪（只有 `.dynsym/.dynstr/.symtab/.dynamic`，
无 `.text/.rodata` 段头），JNI 符号本身也不在 `.dynsym`（`.dynsym` 只剩
`__cxa_finalize`/`__cxa_atexit` 两条）——函数在 PLT/GOT 后，靠 `strings` 才能看到
符号名。**结论：签名链依赖设备指纹 native，复现成本极高。**

## 3. 签名机制（结论：不需要复现）

观察到的两套通道，**校验强度不同**：

### 3.1 new-api 通道（强制 token/sign，放弃了）

```
POST https://apapia-search-weblogic.manmanbuy.com/japi/price/searchDefault
POST https://apapia-search-weblogic.manmanbuy.com/api/searchapi/list
POST https://apapia-search-weblogic.manmanbuy.com/japi/sku/searchList
```

一律返回：

```json
{"code":10006,"msg":"token校验失败","ok":0,"result":null}
```

响应头带 `mmb-req-id`。`ajaxPost` 里签名参数形如
`encodeURIComponent('token')+'='+encodeURIComponent(sign)` 追加到 body 尾部
（L199636/L199976 调用点），sign 由 `makeSign(params)` 生成
（`Object.keys` 排序 → `map` → `join('&')` → 与 SMZDM 同构）。
但 token 本身来自 native `RNReactNativeMencryptSign.getToken()`（设备指纹 +
黑盒），纯 JS 侧无法生成。

`/japi/*` 里也有几个漏网端点（实测免签但无数据）：
`japi/query/parsePrice`（`code:1000 查询成功` 但 `obj` 全 null）、
`recKey/queryAdByKey`（`obj: []`）、`appsearching/searchPreposition`
（`code:1000` 但只回布尔占位）、`multipleSearch/generateSearchId`（回 searchId）。

### 3.2 旧 aspx 通道（**免签名可用**，采用）

Hermes 里 `getBiJiaInfo` 系列走 `ajaxPost` + `/ChromeWidgetServices/WidgetServices.ashx`，
按 methodName 分派到不同主机。实测四个候选主机：

| 主机 | `WidgetServices.ashx` 结果 |
|------|---------------------------|
| `apapia.manmanbuy.com` | **302 → `https://www.aliyun.com/`**（拦截） |
| `apapia-history.manmanbuy.com` | **302 → `https://www.aliyun.com/`**（拦截） |
| `apapia-history-weblogic-sa.manmanbuy.com` | 404（是 new-api 主机，只是路径不存在） |
| `apapia-history-simple.manmanbuy.com` | **200 + 完整 JSON**（免签名） ✅ |

关键代码位置（hasm L581600 附近，`getBiJiaInfoByWxSmall_url`）：

```
methodName: 'getBiJiaInfoByWxSmall_url'
p_url:      <商品链接>
c_devid2:   <deviceInfo.c_devid_lite + "_ABS">
url:        'http(s)://apapia.manmanbuy.com/ChromeWidgetServices/WidgetServices.ashx'
```

即：**校验被关掉的 `-simple` 主机上，`getBiJiaInfo` 只需 `methodName` + `p_url`
两个表单字段，无 token、无 sign、无 Cookie、无 Referer 要求**（实测去掉
Referer / 改 GET / 换 UA 均不影响）。

## 4. 可用接口：`getBiJiaInfo`

```
POST https://apapia-history-simple.manmanbuy.com/ChromeWidgetServices/WidgetServices.ashx
Content-Type: application/x-www-form-urlencoded; charset=utf-8

methodName=getBiJiaInfo&p_url=<URL 编码的商品链接>
```

`p_url` 接受：

- 京东 `https://item.jd.com/<sku>.html`、`https://item.m.jd.com/product/<sku>.html`、
  `http://` 版、`item.jd.hk` 均可（同一 SKU 等价）
- 慢慢买自身商品页 `https://m.manmanbuy.com/d.aspx?id=<bjid>`
- 淘宝/天猫/苏宁/亚马逊链接：**需慢慢买已收录**，未收录返回全空壳

响应字段（46 个，实测）：

| 字段 | 含义 |
|------|------|
| `title` | 商品标题（未收录时为空串） |
| `spmoney` | **当前标价**（字符串，如 `"1759"`；未收录为 `"0"`） |
| `lowerPrice` | 历史最低标价（数字） |
| `lowerPriceyh` | 历史最低到手价（数字） |
| `lowerDate` / `lowerDateyh` | 历史最低出现时间，`.NET /Date(ms-0000)/` 格式 |
| `jiagequshi` | **日线曲线**：`[Date.UTC(y,m,d),price,""]` 逗号拼接的字符串 |
| `jiagequshiyh` | 到手价曲线（同上格式，第三项是优惠说明文案） |
| `currentPriceStatus` | 价位状态文案（`30天最低` / `低于90天平均` / `近期价格平稳` / `近期价格上涨`） |
| `currentPriceyhStatus` | 到手价版价位状态 |
| `qushi` | 走势文案（`上涨` / `先涨后跌` / `历史最低`） |
| `changPriceRemark` | 变动幅度说明（`涨幅7%` / `降幅4%`） |
| `zk_scname` / `zk_scid` | 商城名 / 商城 id（1=京东商城，对应天猫为「天猫商城」） |
| `spbh` | 商品编号（京东 SKU 或慢慢买内部码） |
| `url` | 归一化后的商品链接（`http://` 非 https） |
| `smallpic` / `bigpic` | 图片 |
| `monthSale` / `monthLowerPrice` | 月销量 / 月最低价（多数为 0） |

### 4.1 曲线格式陷阱

`jiagequshi` 是**字符串**，不是 JSON 数组，形如：

```
[Date.UTC(2025,8,1),1499,""],[Date.UTC(2025,8,2),1499.00,""],...
```

- **`Date.UTC` 的月份是 0-based**：`Date.UTC(2026,9,19)` 是 **2026-10-19**
  （适配器里 `date(y, m+1, d)`）。
- 同一天可能有多个点（当天多次变价）→ 按日期去重**保留最后一个**（当天最终价）。
- 价格可能是 `1499` 或 `1499.00`，统一 `parse_float`。
- 曲线可达 375+ 点（约一年），去重后 ~340 天。

### 4.2 未收录 / 限流

- **未收录商品**：HTTP 200 + `spmoney:"0"` + `title:""` + 所有曲线为空 +
  `lowerDate` 为 `/Date(-62135596800000-0000)/`（DateTime.MinValue）+
  `zk_scname` 回落成「中国亚马逊」。适配器据此抛 `SourceError("未收录")`。
- **`getHistoryTrend`（同主机）被单独限流**：稳定返回
  `{"ok":0,"code":7700,"msg":"访问太频繁了，请稍后重试"}`，等 20s 仍限流。
- **`getBiJiaInfo` 未观测到限流**：连打 30 次（10 个 SKU × 3 轮，间隔 0）
  全部 200 且响应体完整，无衰减。仍建议轮询 ≥30s。

## 5. 覆盖度实测

用慢慢买自己的移动 web 好价流取样本
（`https://s.manmanbuy.com/m/search/result?keyword=<词>`，服务端渲染，
`d.aspx?id=` 卡片 20 条/页），再拿每个 bjid 的 `d.aspx` 页去反查：

```
20/20 命中（京东 11 + 天猫 9；洗衣机/家电品类）
```

另外单点验证：

- `item.jd.com/100012043978.html`（茅台飞天）→ 1759 元，历史最低 1499（2026-03-30）
- `item.jd.com/100026667910.html`（iPhone 13）→ 3499 元，历史最低 2981.51
- 任意编造 SKU（如 `100035464132`）→ 未收录空壳

**注意**：淘宝/天猫链接仅在慢慢买已收录时才有数据（未收录返回空壳，且
`zk_scname` 回落「淘宝天猫」）；拼多多链接基本不收录。

## 6. 已下线/不可用的通道（别再试）

| 通道 | 现状（2026-10） |
|------|-----------------|
| `apapia.manmanbuy.com/ChromeWidgetServices/WidgetServices.ashx` | 302 → `www.aliyun.com` |
| `apapia-history.manmanbuy.com/...（同上）` | 302 → `www.aliyun.com` |
| `www.manmanbuy.com/history.aspx?url=` | 200 但空壳；`his.aspx`/`dianshangjiage.aspx` 302 到 404 |
| `www.manmanbuy.com/pricetrend.aspx?url=` | 200 + 40KB HTML，但无价格数据（未登录/需 JS） |
| `apapia.manmanbuy.com/index_json.ashx?methodName=getHistoryTrend` | 200 但空 body |
| `m.manmanbuy.com/d.aspx?id=<bjid>` | 200 + 2.8KB JS 跳转壳（`js/vm.js`，需浏览器执行） |
| `www.manmanbuy.com/search.aspx?key=` | 302 → `alival.manmanbuy.com/index.html?url=...`（阿里人机验证） |
| `s.manmanbuy.com/m/search/result?keyword=` | ✅ 可用（服务端渲染，仅移动 UA；桌面 UA/无 UA 返回 307） |

`alival.manmanbuy.com` 是阿里的验证页（慢慢买用了阿里云 WAF），
带 `?url=` 回跳参数；不带浏览器指纹拿不到内容。

## 7. 集成到 PriceBot 的备注

- 适配器：`app/core/sources/manmanbuy.py`，`symbol` = 商品链接（或纯数字 bjid）。
- `Quote` 映射：

  | Quote 字段 | 来源 |
  |-----------|------|
  | `last` | `spmoney`（或 `price_field="final"` 时的到手价曲线末点） |
  | `prev_close` | 曲线倒数第二天价格（电商价常年不动，通常等于 last → 0%） |
  | `low` / `high` | 窗口内（默认 90 天）曲线最低/最高 |
  | `time` | 曲线最后一天（`YYYY-MM-DD`） |
  | `unit` | `元` |
  | `name` | `title`（截 60 字） |
  | `extra` | 商城 / 价位状态 / 历史最低及其日期 / 走势文案 / 曲线点数 / `url` |

- `extra` 选项：`price_field`（`price` 标价 | `final` 到手价）、
  `window_days`（low/high 窗口，0=全历史）、`method`（可切
  `getBiJiaInfo_weixin`，字段一致）。
- `quote.extra["url"]` 会被引擎当作标的详情链接（`_target_link`），
  因此推送里可点击跳商品页。
- 电商价不是连续行情：`prev_close` 多等于 `last`，`pct_move_*` 规则基本不会
  触发；实用规则是 `cross_below`（跌破目标价）与 `price_move_down`
  （窗口内降价额度）。历史最低在 `extra["hist_low"]`，可作阈值参考。

## 8. 复现步骤（App 升级后重新核对）

1. 豌豆荚下 APK，`unzip -l | grep index.android.bundle` 确认仍是 Hermes。
2. `hbc-disassembler` 出 hasm，`grep "String: 'getBiJiaInfo'"` 找方法名，
   沿 `LoadConstString: '://apapia...WidgetServices.ashx'` 找主机名。
3. 依次试 §3.2 的四个主机，看哪个返回 200 + JSON（`-simple` 通常仍是关闭校验那个）。
4. 若 `-simple` 也上了校验，则退回 new-api 通道 → 需要复现
   `makeSign` + native `getToken`（成本高，建议放弃改用其它源）。
5. 更新 `app/core/sources/manmanbuy.py` 的 `_API_HOST` 常量与
   `tests/test_manmanbuy.py` 的 fixture。
