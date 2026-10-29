---
name: douyin-product-images
description: 从抖音商品分享链接（v.douyin.com 短链 / haohuo.jinritemai.com 商品页）批量提取商品主图、详情长图、买家秀实拍并保存到本地。适用于「提取抖音商品图片」「下载抖音商品详情图」「这个链接的图保存下来」等需求。
agent_created: true
---

# 抖音商品图片提取

从一条抖音商品分享链接里，把**主图轮播**、**详情长图**、**买家秀**三类图片全部扒下来。

核心难点在于：抖音商品 H5 是精简版（`partial-detail-wrapper`），**详情图根本不会渲染进 DOM**——但这不代表没有，数据在 `pack/detail` 接口里，只是该接口要 **POST + promotion_id** 才返回。只看 DOM 会得出「网页版没有详情图」的错误结论。

## 快速开始

```bash
./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_商品名
```

跑完得到：

```
抖音图片_商品名/
├── 主图_01~05.jpg
├── 详情图/详情_01~21.png
└── 详情页_买家秀/买家秀_01~05.jpg
```

下面是它内部做的事，出问题时按顺序排查。

## 0. 前置

- `agent-browser`（真实浏览器，处理 JS 渲染与接口签名）
- `python3`（仅标准库）
- macOS 的 `sips`（可选，用于 webp / heic → jpg）

## 1. 判定链接类型

```bash
curl -sIL "https://v.douyin.com/XXXX/" -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" --max-time 30 | grep -i location
```

| 跳转目标 | 类型 |
|---|---|
| `haohuo.jinritemai.com/ecommerce/trade/detail/index.html?...` | **电商商品**（本 skill 场景） |
| `douyin.com/video/...` / `iesdouyin.com` | 视频，不适用 |

从跳转 URL 里取两个 ID：

- `&id=<product_id>` → 商品 ID
- `promotion_id=<promotion_id>` → **详情接口的钥匙**（可能藏在 `detail_schema` 的双重编码里，`collect.js` 会自动解码解析，兜底还能从 `alkey` 的 `1128_<author>_<item>_<promotion>_011` 第 4 段取）

## 2. 打开页面（必须走短链）

```bash
agent-browser network requests --clear      # 清掉上一次会话的旧签名
agent-browser open "https://v.douyin.com/XXXX/"
agent-browser wait --load load
```

> **不要直接打开长 URL。** 脱离短链的分享参数会触发「检测到当前环境存在安全风险」，页面只剩 50 来个字。加 `&is_pc=1`、`&is_web=1`、`&show_detail=1` 都救不回来；`--headed` 也不行。
>
> `network requests --clear` 不能省：旧会话遗留的过期签名会被排进候选列表，回放只会拿到空 body。

## 3. 抓签名接口地址

```bash
agent-browser network requests --filter "pack/detail" | python3 scripts/build_payload.py
```

输出形如 `window.__DY_PACK_URLS__ = ["https://...a_bogus=xxx&msToken=yyy"];`

两个注意点：

- 同一次加载可能出现**多条** `pack/detail`，其中有的**不带 `msToken`**，回放必然空 body。`build_payload.py` 会把候选全部收齐、带 `msToken` 的排前面，`collect.js` 依次重试直到拿到 JSON。
- **绝不能用 `sed` 把 URL 注入 JS**。URL 里的 `&` 在 `sed` 替换串中是「整个匹配」的展开符号，会把链接搅碎；正确做法是 JSON 序列化成数组变量，或直接 `cat prelude.js collect.js | agent-browser eval --stdin`。

## 4. 取三类图片

```bash
agent-browser network requests --filter "pack/detail" \
  | python3 scripts/build_payload.py > /tmp/prelude.js
cat /tmp/prelude.js scripts/collect.js | agent-browser eval --stdin > raw.json
```

### 4.1 详情图（关键）

```js
fetch(PACK_URL, {
  method: 'POST',                        // 必须 POST
  credentials: 'include',
  headers: {'Content-Type': 'application/x-www-form-urlencoded'},
  body: 'promotion_id=' + promotionId    // 必须用 promotion_id
})
```

返回 JSON 的 `detail_info.detail_imgs[]` 就是全部详情长图（实测某露营灯 21 张）。

参数对照，别踩：

| 写法 | 结果 |
|---|---|
| `POST` + `promotion_id=xxx` | ✅ 正常返回 `detail_imgs` |
| `POST` + `product_id=xxx` | ❌ `status_code: 14001006 参数不合法` |
| `POST` + 空 body | ❌ 同上 |
| `GET`（任意参数） | ❌ 返回空 body（最容易被误判成「接口没数据」） |

### 4.2 主图

主图**不是 `<img>`**，是 CSS 背景图：

```js
[...document.querySelectorAll('.head-figure__media-view__content')]
  .map(e => getComputedStyle(e).backgroundImage.match(/url\("(.+)"\)/)[1])
```

提取时保留 `ecom-shop-material/` 前缀，和接口 uri 保持同构。轮播指示器写「1/6」但只有 5 张时，多出来那格是**商品视频**，不是漏图。

### 4.3 买家秀

```js
[...document.querySelectorAll('[class*=buyershow] *')]
  .map(e => getComputedStyle(e).backgroundImage)
  .filter(b => b.includes('commentpic'))
```

页面通常只渲染前 5 张缩略图，「买家秀 (51)」是评论总数，不是图数。

## 5. 下载

```bash
python3 scripts/download_all.py raw.json ~/Desktop/抖音图片_<商品名>
```

同一份 `<uri>` 换模板即可，各类型最优模板：

| 类型 | 模板 | 说明 |
|---|---|---|
| 详情图 | `~tplv-5mmsx3fupr-image.png` | **无损 PNG，优先**。首图 1.1MB vs JPEG 154KB，文字边缘明显更净 |
| 主图 | `~tplv-5mmsx3fupr-resize_q:1080:1080:q90.webp` | 源图仅 800×800，这是最清晰档 |
| 买家秀 | `~tplv-fceoirpogb-re_cp:360:0:q100.heic` | 只有 360×480，改尺寸或去掉模板一律 403 |

- 裸素材地址（不带 `~tplv-...`）→ **400**
- 请求必须带 `User-Agent` 和 `Referer: https://haohuo.jinritemai.com/`
- CDN 节点用 `p26-item.ecombdimg.com` 最稳，`p3-item` / `p9-item` 同源可换

## 6. 失败排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `status=200` 但 body 为空 | **软限流**。同一 IP 短时间内反复回放 `pack/detail` 会被静默丢包 | 停几分钟再试、关掉浏览器换新会话、别对同一链接高频重跑。重跑前务必 `network requests --clear` |
| `14001006 参数不合法` | 用了 `product_id` / 空 body / `GET` | 改 `POST` + `promotion_id` |
| `` evaluation error: Invalid or unexpected token `` | URL 里的 `&` 被 shell 或 sed 破坏 | 用 `build_payload.py` + `eval --stdin`，别拼字符串 |
| 抓不到 `pack/detail` | 短链被风控 / 页面没加载完 / 不是商品页 | 重新打开短链，确认 innerText 里有商品标题 |
| 页面只有「检测到当前环境存在安全风险」 | 用了长 URL | 换回 `v.douyin.com` 短链 |

## 7. 其他坑位

- `agent-browser eval` **支持 await Promise**，可以直接 `fetch(...).then(r=>r.text())`。
- 页面主体在内部滚动容器里（`.detail-container__body`，内容高度约 1518px），`window.scrollY` 恒为 0，`mouse wheel` 也无效——想整页截图直接 `set viewport 1440 2600`。
- `agent-browser network request <id>` 只回 URL，不回 body；HAR 录制也不含 body。要 body 只能回放接口。
- 该版本（0.27.0）没有 `addinitscript` 命令；`open --init-script <path>` 可用。
- 详情图宽度统一 750，高度不等（实测 308~1630），按接口顺序编号即可，无需拼接。
