#!/usr/bin/env bash
# run.sh —— 一条命令跑完：预热 → 打开商品页 → 抓签名 → 收集 → 下载
#
# 用法：
#   ./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_商品名
#
# 环境变量：
#   MAX_TRY=3      详情图抓取的最大重试次数（每次重载页面会得到新签名）
#   SKIP_DETAIL=1  跳过详情图，只要主图 + 买家秀（最稳，不依赖签名）
#
# 依赖：agent-browser、python3

set -uo pipefail

SHORT_URL="${1:?用法: run.sh <抖音链接> <输出目录>}"
OUT_DIR="${2:?用法: run.sh <抖音链接> <输出目录>}"
MAX_TRY="${MAX_TRY:-3}"
SKIP_DETAIL="${SKIP_DETAIL:-0}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

command -v agent-browser >/dev/null || { echo "✗ 缺少 agent-browser。安装：npm i -g agent-browser && agent-browser install" >&2; exit 1; }
command -v python3 >/dev/null || { echo "✗ 缺少 python3" >&2; exit 1; }

# ---- 链接体检：被裁剪过的长链接只会落到风控页，白白浪费一轮 ----
case "$SHORT_URL" in
  *v.douyin.com*)   : ;;
  *douyin.com/video*|*iesdouyin.com*)
      echo "✗ 这是视频链接，不是商品页。本 skill 只处理商品分享链接。" >&2; exit 1 ;;
  *haohuo.jinritemai.com*)
      if ! printf '%s' "$SHORT_URL" | grep -qE 'ug_share_id|detail_schema|alkey'; then
        echo "✗ 这个长链接缺分享参数（ug_share_id / detail_schema / alkey），只会落到『检测到当前环境存在安全风险』页。" >&2
        echo "  请在抖音里重新复制分享短链（v.douyin.com/...），或粘贴带完整参数的长链接。" >&2
        exit 1
      fi ;;
esac

echo "→ 预热主站（让 msToken 生效，这步缺失会导致签名回放失败）"
agent-browser open "https://www.douyin.com/" >/dev/null 2>&1 || true
sleep 2

DETAIL_OK=0
for attempt in $(seq 1 "$MAX_TRY"); do
  echo "→ 第 $attempt/$MAX_TRY 轮：打开商品页"
  # 必须先清空请求日志：上一次遗留的旧签名会被排进候选列表，回放只会拿到空 body
  agent-browser network requests --clear >/dev/null 2>&1 || true
  agent-browser open "$SHORT_URL" >/dev/null 2>&1 || true
  agent-browser wait --load load >/dev/null 2>&1 || true
  sleep 2

  agent-browser network requests --filter "pack/detail" \
    | python3 "$DIR/build_payload.py" > "$TMP/prelude.js"

  if ! grep -q "https" "$TMP/prelude.js"; then
    echo "  · 没抓到 pack/detail 请求（页面可能还在风控或没加载完）"
    continue
  fi

  # 由 build_payload.py 生成 JSON 安全的数组赋值，再拼上 collect.js。
  # 绝不用 sed 注入 URL —— 里面的 & 会被 sed 当成"整个匹配"展开。
  cat "$TMP/prelude.js" "$DIR/collect.js" > "$TMP/run.js"
  agent-browser eval --stdin < "$TMP/run.js" > "$TMP/raw.json" 2>/dev/null

  set +e
  python3 "$DIR/summarize.py" "$TMP/raw.json" | sed 's/^/  /'
  rc=${PIPESTATUS[0]}
  set -e

  if [ "$rc" -eq 0 ]; then DETAIL_OK=1; break; fi
  if [ "$SKIP_DETAIL" = "1" ]; then break; fi
  [ "$attempt" -lt "$MAX_TRY" ] && echo "  · 详情图未拿到，换一轮新签名重试…"
done

set -e
if [ "$SKIP_DETAIL" != "1" ] && [ "$DETAIL_OK" -ne 1 ]; then
  echo
  echo "⚠ 详情图没有拿到。这是已知的高概率失败点：签名回放依赖 msToken / a_bogus 的新鲜度，"
  echo "  换机器、换 IP、换浏览器 profile 都可能失效。主图与买家秀不受影响。"
  echo "  可尝试：加大 MAX_TRY=6；或隔几分钟重跑；或换网络环境。"
fi

echo
echo "→ 下载 ..."
python3 "$DIR/download_all.py" "$TMP/raw.json" "$OUT_DIR"
