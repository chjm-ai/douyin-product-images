---
name: douyin-product-images
description: 从抖音商品分享链接（v.douyin.com 短链 / haohuo.jinritemai.com 商品页）提取商品主图、详情长图、买家秀实拍并保存到本地。适用于「提取抖音商品图片」「下载抖音商品详情图」「这个链接的图保存下来」等需求。
agent_created: true
---

# 抖音商品图片提取

从一条抖音商品分享链接里提取三类图片：**主图轮播**、**详情长图**、**买家秀**。

## 先读这段：可靠性预期

| 图片 | 依赖 | 可靠性 |
|---|---|---|
| 主图（5 张，800×800） | 纯 DOM + CDN | ✅ 稳定 |
| 买家秀（前 5 张，360×480） | 纯 DOM + CDN | ✅ 稳定 |
| **详情长图（20+ 张，750 宽）** | **回放页面签名接口** | ⚠️ **不稳定** |

详情图那条路本质上是「抢一个新鲜签名」，成败取决于 `msToken` 是否存在、`a_bogus` 是否足够长且没被消耗。**换机器、换 IP、换浏览器 profile 都可能直接失效**，失败时接口返回 `200 + 空 body`（不报错，静默丢包）。

`run.sh` 已内置预热 + 多轮重试，但**不保证成功**。只要主图和买家秀，用 `SKIP_DETAIL=1`，那条路是确定的。

## 为什么详情图这么麻烦（根因）

分享落地页自己的请求是这样的：

```
POST /aweme/v2/shop/promotion/pack/detail/?is_h5=1&origin_type=detail_share_v2&a_bogus=...
body: promotion_id=3843019061009187217&enter_from=copy&meta_param=<7KB JSON>
→ 响应仅 ~903 字节（detail_config / jump_url / 空 detail_imgs）
```

**关键在 `enter_from=copy` + `meta_param`**：这两个参数告诉服务端「这是一个分享落地页」，于是只返回精简数据。所以页面 DOM 里永远没有「商品图文详情」那一段——不是抓不到，是服务端压根没给。

把 body 换成极简的 `promotion_id=<promotion_id>`，同一个接口会返回 **21KB 完整数据**（实测 21 张详情图）。但这一步要绕过签名校验，于是就有了下面的不稳定。

## 快速开始

```bash
./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_商品名

# 只要主图 + 买家秀（稳）
SKIP_DETAIL=1 ./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_商品名

# 详情图多试几轮
MAX_TRY=6 ./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_商品名
```

```
抖音图片_商品名/
├── 主图_01~05.jpg
├── 详情图/详情_01~21.png     ← 拿不到时此目录为空
└── 详情页_买家秀/买家秀_01~05.jpg
```

## 0. 前置

- `agent-browser`：`npm i -g agent-browser && agent-browser install`
- `python3`（仅标准库）
- macOS 的 `sips`（可选，webp / heic → jpg）

## 1. 链接体检

| 输入 | 结果 |
|---|---|
| `v.douyin.com/xxx` 短链 | ✅ 能用 |
| `haohuo.jinritemai.com/...&ug_share_id=...&detail_schema=...&alkey=...` 完整长链 | ✅ 能用 |
| 长链但被裁剪掉 `ug_share_id`/`detail_schema`/`alkey` | ❌ 落到「检测到当前环境存在安全风险」页，只有 53 个字，连 `pack/detail` 都不会发 |
| `douyin.com/video/...` | ❌ 是视频不是商品 |

`run.sh` 会做这个体检并直接提示，不用浪费一轮。

**短链变长链**：不需要，也没必要——短链 302 一跳就到长链，`collect.js` 从最终 `location.href` 里解析 `product_id` / `promotion_id`。反过来长链无法还原成短链。

## 2. 预热主站（别省）

```bash
agent-browser open "https://www.douyin.com/"
```

`msToken` 由主站的 JS/cookie 环境产生。**没预热过主站，商品页的请求多半不带 `msToken`，签名回放必然返回空 body。** 这是「换台机器就失败」最常见的原因。

## 3. 抓签名接口

```bash
agent-browser network requests --filter "pack/detail" | python3 scripts/build_payload.py
```

`build_payload.py` 干三件事：

1. 逐行解析（**不能 `tr -d '\n'`**，多条 URL 会被拼成一个废链接）；
2. 按签名完整度打分排序：带 `msToken` +4、`a_bogus` 长度 >80 +2、URL 更长 +1；
3. 输出 `window.__DY_PACK_URLS__` 数组供 `collect.js` 依次重试。

**别用 `sed` 把 URL 注入 JS**：`&` 在 sed 替换串里是「整个匹配」展开符，会把链接搅碎。

## 4. 三类图片的取法

### 4.1 详情图（不稳定，靠签名）

```js
fetch(PACK_URL, {
  method: 'POST',                        // GET 一定返回空 body
  credentials: 'include',
  headers: {'Content-Type': 'application/x-www-form-urlencoded'},
  body: 'promotion_id=' + promotionId    // 用 product_id → 14001006 参数不合法
})
```

| 写法 | 结果 |
|---|---|
| `POST` + `promotion_id` + 有效签名 | ✅ `detail_info.detail_imgs` |
| `POST` + `product_id` | ❌ `14001006 参数不合法` |
| `POST` + 页面原样 body（含 `enter_from=copy`） | ⚠️ 200，但只有 903 字节精简数据 |
| `GET` | ❌ 空 body |
| 签名已失效 / 缺 msToken / 短 `a_bogus` | ❌ **200 + 0 字节**，静默丢包 |

### 4.2 主图（稳定）

不是 `<img>`，是 CSS 背景图：

```js
[...document.querySelectorAll('.head-figure__media-view__content')]
  .map(e => getComputedStyle(e).backgroundImage.match(/url\("(.+)"\)/)[1])
```

正则要保留 `ecom-shop-material/` 前缀，和接口 uri 同构，否则下载器拼出的 URL 会缺一段。轮播显示「1/6」但只有 5 张时，多的那格是**商品视频**。

### 4.3 买家秀（稳定）

```js
[...document.querySelectorAll('[class*=buyershow] *')]
  .map(e => getComputedStyle(e).backgroundImage)
  .filter(b => b.includes('commentpic'))
```

页面只渲染前 5 张缩略图，「买家秀 (51)」是评论总数，不是图数。站内跳转（进店逛逛 / 底部「店铺」）都会被「打开抖音APP」拦住，走不出分享落地页，别浪费时间。

## 5. 下载模板

| 类型 | 模板 | 说明 |
|---|---|---|
| 详情图 | `~tplv-5mmsx3fupr-image.png` | **无损 PNG**，1.1MB vs JPEG 154KB，文字边缘更净 |
| 主图 | `~tplv-5mmsx3fupr-resize_q:1080:1080:q90.webp` | 源图仅 800×800 |
| 买家秀 | `~tplv-fceoirpogb-re_cp:360:0:q100.heic` | 只有 360×480，改尺寸/去模板一律 403 |

裸素材地址（不带 `~tplv-...`）→ 400。请求需带 `User-Agent` + `Referer: https://haohuo.jinritemai.com/`。CDN 节点 `p26-item` 最稳。

## 6. 失败排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面 53 个字，无 `pack/detail` | 长链被裁剪 / 直连非分享 URL | 换 `v.douyin.com` 短链或完整分享长链 |
| 200 + 空 body | 签名失效：缺 `msToken` 或短 `a_bogus`(≈44) | 预热主站、`MAX_TRY` 加大、隔几分钟重跑 |
| `14001006 参数不合法` | 用了 `product_id` / 空 body / GET | 改 `POST` + `promotion_id` |
| 200 + 903 字节 | 请求带了 `enter_from=copy`，服务端只给精简数据 | 用极简 body |
| `SyntaxError: Invalid or unexpected token` | URL 里 `&` 被 shell / sed 破坏 | 用 `build_payload.py` + `eval --stdin` |
| 只有 1 条候选、无 msToken | 没预热主站，或页面还没加载完 | 先开 douyin.com 再进商品页 |

## 7. 其他坑位

- 页面主体在内部滚动容器里（`.detail-container__body`，内容高度约 1518px），`window.scrollY` 恒为 0，`mouse wheel` 也无效；整页截图直接 `set viewport 1440 2600`。
- `agent-browser network requests` 的输出**可能截断 URL、可能漏 `msToken`**；HAR（`network har start`）里的 URL 是准确的，也是拿到请求 body 的唯一途径（`network request <id>` 只回 URL，不回收/发 body）。
- `agent-browser eval` 支持 await Promise；带 `&` 的脚本一律 `eval --stdin < file.js`。
- 该版本（0.27.0）没有 `addinitscript`；`open --init-script <path>` 可用。
- 详情图宽度统一 750，高度 308~1630 不等，按接口顺序编号即可，不用拼。
