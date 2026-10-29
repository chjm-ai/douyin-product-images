# douyin-product-images

> 从一条抖音商品分享链接，提取**主图轮播 / 详情长图 / 买家秀**。一个 WorkBuddy / Claude Code 可用的 Skill。

## ⚠️ 先说可靠性

| 图片 | 依赖 | 可靠性 |
|---|---|---|
| 主图（5 张，800×800） | DOM + CDN | ✅ 稳定 |
| 买家秀（前 5 张，360×480） | DOM + CDN | ✅ 稳定 |
| **详情长图（20+ 张，750 宽）** | 回放页面签名接口 | ⚠️ **不稳定** |

详情图那条路是「抢一个新鲜签名」，成败取决于 `msToken` 是否存在、`a_bogus` 是否够长且没被消费。**换机器 / 换 IP / 换浏览器 profile 都可能直接失效**，失败时接口返回 `200 + 空 body`——不报错，静默丢包，最难查。

`run.sh` 内置了预热和多轮重试，但**不保证成功**。只要主图和买家秀就用 `SKIP_DETAIL=1`，那条是确定的。

## 为什么详情图这么麻烦

分享落地页自己的请求：

```
POST /aweme/v2/shop/promotion/pack/detail/?is_h5=1&origin_type=detail_share_v2&a_bogus=...
body: promotion_id=3843019061009187217&enter_from=copy&meta_param=<7KB JSON>
→ 响应只有 ~903 字节（空 detail_imgs）
```

**根因是 `enter_from=copy` + `meta_param`**：这两个参数告诉服务端「这是分享落地页」，于是只返回精简数据。所以页面 DOM 里永远找不到「商品图文详情」——不是抓不到，是服务端压根没给。

把 body 换成极简的 `promotion_id=<promotion_id>`，同一接口会返回 **21KB 完整数据**（实测 21 张详情图）。但这一步要绕过签名校验，于是就有了上面的不稳定。

## 用法

```bash
# 全部（详情图尽最大努力）
./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_山趣橡果灯

# 只要主图 + 买家秀（稳）
SKIP_DETAIL=1 ./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_山趣橡果灯

# 详情图多试几轮
MAX_TRY=6 ./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_山趣橡果灯
```

```
抖音图片_山趣橡果灯/
├── 主图_01~05.jpg
├── 详情图/详情_01~21.png
└── 详情页_买家秀/买家秀_01~05.jpg
```

## 安装

```bash
git clone https://github.com/chjm-ai/douyin-product-images.git \
  ~/.workbuddy/skills/douyin-product-images
```

依赖：`agent-browser`（`npm i -g agent-browser && agent-browser install`）、`python3`、macOS `sips`（可选）。

## 脚本分工

| 文件 | 职责 |
|---|---|
| `scripts/run.sh` | 编排：链接体检 → 预热 → 抓签名 → 收集 → 失败重试 → 下载 |
| `scripts/build_payload.py` | 解析请求日志，按签名完整度打分排序，生成 JS 安全的候选数组 |
| `scripts/collect.js` | 页面内执行：主图 / 买家秀 / 详情图（依次重试候选签名） |
| `scripts/summarize.py` | 把收集结果转成人能读的诊断，退出码区分「有详情/只有主图/全失败」 |
| `scripts/download_all.py` | 按类型选最优模板下载，webp/heic 自动转 jpg |

## 坑位备忘

- **链接要完整**。长链缺 `ug_share_id`/`detail_schema`/`alkey` 会落到「检测到当前环境存在安全风险」页，只有 53 个字，连 `pack/detail` 都不会发。短链变长链不需要——302 一跳自动完成。
- **必须预热 `www.douyin.com`**。`msToken` 由主站环境产生，缺了它签名回放必然空 body。
- **重跑前必须 `network requests --clear`**。旧签名会排进候选列表。
- **别 `tr -d '\n'`**。多条候选 URL 会被拼成一个废链接。
- **别用 `sed` 注入 URL**。`&` 在 sed 替换串里表示「整个匹配」，会把链接搅碎；用 `build_payload.py` 生成 JSON 数组。
- **轮播「1/6」只有 5 张**：多出来那格是商品视频。
- **「买家秀 (51)」是评论总数**，页面只渲染前 5 张。
- **站内跳转走不出去**：「进店逛逛」「店铺」都被「打开抖音APP」拦住，别指望从店铺页绕开分享模式。
- 买家秀只有 360×480，改尺寸参数或去模板一律 403。
- 裸素材地址（不带 `~tplv-...`）返回 400。

## 免责

仅供个人学习与素材备份。请遵守抖音用户协议与 `robots.txt`，不要用于批量采集或商业分发。图片版权归原作者与品牌方所有。

## License

MIT
