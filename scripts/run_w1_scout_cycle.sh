#!/usr/bin/env bash
# W1_SCOUT 自动驾驶 · 一个周期
# 抓 → 组装 → delta 检测(变了才重判,省 DeepSeek/api 配额)→ 校验闸门 → 赛前锁定 → 赛后审计
#
# 用法(cron 在【有 key 的机器】上跑;沙箱无 key):
#   APIFOOTBALL_KEY=... DEEPSEEK_API_KEY=... bash scripts/run_w1_scout_cycle.sh
# 建议 cron:赛前 48h 内的日子,按时间档(如每 2 小时)跑一次。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

echo "[$(date -u +%FT%TZ)] W1_SCOUT cycle start"

# 1) 抓真因子(无 key 会自行失败退出,不写假数据)
python3 scripts/w1_scout_fetch_api_football.py || { echo "fetch failed/again later"; }

# 2) 组装 bundle(合并 data/scout/ 真因子)
python3 scripts/w1_scout_bundle.py || exit 1

# 3) delta 门:bundle 没变就不重判(省 DeepSeek 调用)
NEW=$(python3 -c "import hashlib;print(hashlib.sha1(open('state/w1_scout_bundles.json','rb').read()).hexdigest())")
PREV=$(cat state/.scout_bundles.sha 2>/dev/null || echo "")
if [ "$NEW" != "$PREV" ]; then
  echo "bundle changed -> DeepSeek 全量重判"
  if ! python3 scripts/w1_scout_analyst.py; then
    echo "analyst failed (key/quota/validation?) -> 不更新指纹/不 embed/不 lock"
    python3 scripts/w1_scout_ledger.py audit
    exit 1
  fi
  # 4) 闸门:不过就不锁(set -e 风格手动判)
  if python3 scripts/check_w1_scout.py; then
    echo "$NEW" > state/.scout_bundles.sha
    python3 scripts/w1_scout_embed.py     # 把 DeepSeek call 注入 dashboard(可见)
  else
    echo "check_w1_scout FAIL -> 不更新指纹/不锁/不上屏,待修"; exit 1
  fi
else
  echo "bundle 未变 -> 跳过重判(配额已省)"
fi

# 5) 赛前锁定(不可变·拒 hindsight)+ 赛后审计(回填战绩)
python3 scripts/w1_scout_ledger.py lock
python3 scripts/w1_scout_ledger.py audit

echo "[$(date -u +%FT%TZ)] W1_SCOUT cycle done"
