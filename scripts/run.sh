#!/usr/bin/env bash
# run.sh —— 一条命令跑完全流程：打开短链 → 抓签名接口 → 收集 → 下载
#
# 用法：
#   ./scripts/run.sh "https://v.douyin.com/XXXXXX/" ~/Desktop/抖音图片_商品名
#
# 依赖：agent-browser、python3

set -euo pipefail

SHORT_URL="${1:?用法: run.sh <抖音短链> <输出目录>}"
OUT_DIR="${2:?用法: run.sh <抖音短链> <输出目录>}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ 打开页面 ..."
# 必须先清空请求日志：上一次会话遗留的旧签名会被排到候选列表前面，回放只会拿到空 body
agent-browser network requests --clear >/dev/null 2>&1 || true
agent-browser open "$SHORT_URL" >/dev/null
agent-browser wait --load load >/dev/null 2>&1 || true
sleep 2

echo "→ 捕获签名接口 ..."
agent-browser network requests --filter "pack/detail" \
  | python3 "$DIR/build_payload.py" > "$TMP/prelude.js"

if ! grep -q "https" "$TMP/prelude.js"; then
  echo "✗ 没抓到 pack/detail 请求。" >&2
  echo "  常见原因：短链被风控、页面还没加载完、链接不是商品页。" >&2
  exit 1
fi

# 由 build_payload.py 生成 JSON 安全的数组赋值，再拼上 collect.js。
# 绝不用 sed 注入 URL —— 里面的 & 会被 sed 当成"整个匹配"展开。
cat "$TMP/prelude.js" "$DIR/collect.js" > "$TMP/run.js"

echo "→ 收集图片清单 ..."
agent-browser eval --stdin < "$TMP/run.js" > "$TMP/raw.json"

echo "→ 下载 ..."
python3 "$DIR/download_all.py" "$TMP/raw.json" "$OUT_DIR"
