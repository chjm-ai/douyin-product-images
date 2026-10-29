# douyin-product-images

> 从一条抖音商品分享链接，把**主图轮播 / 详情长图 / 买家秀**三类图片全部扒下来。一个 WorkBuddy / Claude Code 可用的 Skill。

## 为什么需要它

抖音商品页的 H5 是**精简版**，`商品详情` 那一段根本不渲染进 DOM——在页面里怎么滚都看不到详情长图。很多人（包括写这个 skill 的人）第一步就误判成「网页版没有详情图」。

实际上数据一直都在接口里：

```
POST /aweme/v2/shop/promotion/pack/detail/
body: promotion_id=xxxxxxxx
→ detail_info.detail_imgs[]   # 全部详情长图
```

三个反直觉的点：

| 直觉 | 实际 |
|---|---|
| GET 请求 | **必须 POST**，GET 返回空 body，看起来像「没数据」 |
| 传 `product_id` | **必须传 `promotion_id`**，否则 `14001006 参数不合法` |
| 详情图在 DOM 里 | 只在接口里，DOM 里永远没有 |

## 它做了什么

| 图片类型 | 来源 | 输出 |
|---|---|---|
| 主图 | DOM 里 `.head-figure__media-view__content` 的 `background-image` | 800×800 JPEG |
| 详情长图 | `pack/detail` 接口的 `detail_imgs` | 宽 750 无损 PNG |
| 买家秀 | `[class*=buyershow]` 的 `background-image` | 360×480 JPEG |

详情图还有个额外红利：`~tplv-5mmsx3fupr-image.png` 给的是**无损 PNG**，比同图 JPEG 版大 7 倍，文字边缘干净得多。

## 安装

```bash
git clone https://github.com/chjm-ai/douyin-product-images.git \
  ~/.workbuddy/skills/douyin-product-images
```

依赖：

- [`agent-browser`](https://github.com/vercel-labs/agent-browser) —— 处理 JS 渲染与接口签名
- `python3`（仅标准库）
- macOS 的 `sips`（可选，用于 webp / heic → jpg）

## 用法

一条命令：

```bash
./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_山趣橡果灯
```

```
→ 打开页面 ...
→ 捕获签名接口 ...
→ 收集图片清单 ...
→ 下载 ...
商品: product_id=3843019061009187217 promotion_id=3843148481350992329
主图 5 / 详情图 21 / 买家秀 5

完成 → ~/Desktop/抖音图片_山趣橡果灯
  主图   5/5
  详情图 21/21
  买家秀 5/5
```

分步执行：

```bash
# 1. 必须走短链，直连长 URL 会被风控
agent-browser network requests --clear
agent-browser open "https://v.douyin.com/XXXXXX/"
agent-browser wait --load load

# 2. 抓签名接口地址（URL 含 & ，必须 JSON 序列化，别用 sed 拼字符串）
agent-browser network requests --filter "pack/detail" \
  | python3 scripts/build_payload.py > /tmp/prelude.js

# 3. 收集三类图片
cat /tmp/prelude.js scripts/collect.js | agent-browser eval --stdin > raw.json

# 4. 下载
python3 scripts/download_all.py raw.json ~/Desktop/抖音图片_山趣橡果灯
```

产出：

```
抖音图片_山趣橡果灯/
├── 主图_01~05.jpg
├── 详情图/详情_01~21.png
└── 详情页_买家秀/买家秀_01~05.jpg
```

## 坑位备忘

- **直连长 URL 会风控**。`&is_pc=1`、`&is_web=1`、`&show_detail=1` 都救不回来，`--headed` 也不行，只有短链能拿到完整数据。
- **重跑前必须 `network requests --clear`**。旧会话遗留的过期签名会排进候选列表，回放只得到空 body。
- **签名有时效**。`msToken` + `a_bogus` 拿到后要立刻在同一会话里回放。
- **别把带 `&` 的 URL 塞进 `agent-browser eval "..."` 或用 `sed` 注入**。`sed` 替换串里的 `&` 表示「整个匹配」，会把链接搅碎；用 `build_payload.py` 生成 JSON 数组。
- **同一次加载可能有多条 `pack/detail`**，有的不带 `msToken`，回放必然空。`collect.js` 会依次重试。
- **软限流**：同一 IP 短时间内反复回放 `pack/detail`，会返回 `200 + 空 body`（不报错，静默丢包）。停几分钟、换会话即可，别高频重跑。
- **轮播写「1/6」但只有 5 张**：多出来那格是商品视频，不是漏图。
- **「买家秀 (51)」是评论总数**，页面只渲染前 5 张缩略图。
- 买家秀只有 360×480，改尺寸参数或去掉模板一律 403，这是抖音的下限。
- 裸素材地址（不带 `~tplv-...`）返回 **400**，必须带模板。
- 请求要带 `User-Agent` 和 `Referer: https://haohuo.jinritemai.com/`。

## 免责

仅供个人学习与素材备份使用。请遵守抖音的用户协议与 `robots.txt`，不要用于批量采集或商业分发。图片版权归原作者与品牌方所有。

## License

MIT
