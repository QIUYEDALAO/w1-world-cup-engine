# W1_SCOUT 自动驾驶 + dashboard 可见性 — 技术员任务清单 & 方向

**日期**: 2026-06-17
**背景**: DeepSeek 已接通(`provider=deepseek, model=deepseek-v4-pro, api_ok`)。本文件解决三件事:
(1) 把"抓→组装→DeepSeek重判→校验→锁定→审计"做成**自动驾驶**(替代手动"开始预测");
(2) dashboard 上**能看到 DeepSeek 的分析**(目前看不到);
(3) 先让 DeepSeek **真跑一次**全量重判(技术员目前只 dry-run 过)。

---

## 0. 设计判断(回应"开始预测"该不该手动)

**老板的直觉对:生产级系统不该靠手点。** 现状:
- "开始预测" = 手动 POST `/predict` → 现场抓+预测**一场**;那几个时间档(T-48h…T-30m)现在**只是显示,不驱动抓取**。
- 但底层零件齐:`w1_watcher.sh`/`w1_odds_snapshot_collector.py`(抓+快照)、`config/w1_odds_movement_thresholds.json`(盘口异动阈值)、SCOUT 全链。**只缺编排。**

**方向**:做**调度驱动 + 变化触发(delta)**的自动驾驶;"开始预测"**降级为手动强刷/调试**用,不再是常态入口。三条硬约束:
- **省配额**:只轮询 kickoff 在未来 48h 内的场,按时间档(非连续)触发;
- **守赛前纪律**:未来 fixture 在赛前抓齐;已开赛/完赛只允许赛后 audit,不允许伪赛前补因子;
- **变了才重判**:用已有盘口异动阈值 + 首发确认 + 伤停更新判定"有意义的变化",否则不调 DeepSeek(省钱)。

---

## 1. 技术员任务清单

### SC0 ★先做★ 让 DeepSeek 真跑一次(去掉 dry-run)
```bash
DEEPSEEK_API_KEY=... python3 scripts/w1_scout_analyst.py    # 真写 state/w1_scout_calls.json
python3 scripts/check_w1_scout.py                            # 必须 PASS
python3 scripts/w1_scout_ledger.py lock                      # 赛前锁定
```
验收:`state/w1_scout_calls.json` 出现 DeepSeek 产的全量 call(stance/why/factors 齐),checker PASS。

### SC1 自动驾驶循环(已给脚本)
我已写好 **`scripts/run_w1_scout_cycle.sh`**(抓→组装→delta→变了才重判→校验→锁定→审计,含配额保护)。技术员:
- 在**有 key 的机器**上 cron 它(沙箱无 key)。建议:赛前 48h 内每 2h 一次,临近(T-2h/T-1h/T-30m)加密。
- 例:`*/120 * * * *  APIFOOTBALL_KEY=.. DEEPSEEK_API_KEY=.. bash /…/scripts/run_w1_scout_cycle.sh >> /…/state/scout_cron.log 2>&1`

### SC2 delta 触发做扎实(替换脚本里的临时 hash 门)
脚本 v1 用 bundle 整体 hash 判变化。升级为**有意义变化**才重判:
- 赔率:复用 `config/w1_odds_movement_thresholds.json` 的阈值(动超阈值才算变);
- 首发:`lineup.confirmed` 由 false→true;
- 伤停:injuries 列表变化。
任一触发 → 重判;否则跳过省配额。

### SC3 ★dashboard 显示 DeepSeek 分析★(回应"在哪看到")
现状:页面"研究结论"是 **W1 市场读数**,**不是 DeepSeek**。新增一块 **"AI 分析师 · DeepSeek"** 面板(纯展示、不改概率):
- 数据源:`state/w1_scout_calls.json`(或经 predict server `/scout-call` 端点)按 fixture 取该场 call。
- 显示:**stance 徽章**(跟市场 AGREE / 偏 LEAN / 逆 FADE,颜色区分)、`call`(方向+比分倾向+信心)、`why_cn`、`key_factors_cn`(2-3 条)、`conviction`、`honesty_label`。
- **溯源戳(关键,让你一眼看出 DeepSeek 真读了数据)**:
  `DeepSeek(deepseek-v4-pro) 已于 {decided_at} 读取 {可用因子数}/7 维 → {stance}`,并标"独立于市场底座的 AI 观点·未验证·非推介"。
- 与 W1"研究结论"**并列但分开标注**:一边是"市场读数(W1)",一边是"AI 分析师(DeepSeek)"——你能直接对比两者一不一致。
- 边界:只读展示;不改 λ/概率;无投注词;`honesty_label` 必须显示。
- checker:在 `check_w1_scout.py` 或 `check_w1_visual_dashboard.py` 加 token 断言("AI 分析师"/"DeepSeek"/honesty 标),只增不减。

### SC4 "开始预测"降级为手动强刷
保留按钮(调试/按需有用),但文案/定位改为"手动强制刷新本场";常态由 SC1 调度驱动。可选:页面顶栏显示"上次自动刷新 {time} · 下次 {band}"。

### SC5 提交
新增 `scripts/run_w1_scout_cycle.sh` + dashboard 改动 + checker 强化,按 SCOUT 红线提交(state/、data/scout/ 仍 gitignored)。

---

## 2. 方向 / 原理(为什么这样)

- **调度 + delta** = 既自动又省配额;赔率随时间动本身是信号,多档快照正好喂给 SCOUT。
- **DeepSeek 面板 + 溯源戳** = 让"AI 真读了数据并表态"**可见、可对比市场**——这正是你要的"敢说敢干看得见"。
- **锁定/审计照常** = 每次重判的 call 赛前锁定,完赛审计;DeepSeek 的战绩(尤其逆市场谁对)随轮次累积 → 它越跑越懂自己。
- **底座不动** = SCOUT/DeepSeek 全叠在 W1 市场底座之上;市场读数永远在,AI 观点并列呈现,不互相覆盖。

---

## 3. 边界 / 红线(不变)

✅ 允许联网抓取(api-football)+ 调 DeepSeek(你 key)。
❌ 不改 `w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵底座;❌ 赛后数据不进赛前判断(fetcher 的 `xg_roll/form` 只取过往场);❌ 不造值(抓不到=missing);❌ 不输出投注/资金/命中承诺;❌ DeepSeek 产出必须过 `check_w1_scout` 才入库/上屏;每条 call 带 `honesty_label`+`independent_edge=false`。

---

## 4. 验收口径(我复核)

1. SC0:DeepSeek 全量 call 真写入,checker PASS。
2. SC1/SC2:cron 周期能跑;无意义变化时**不重判**(日志显示跳过);有变化才调 DeepSeek。
3. SC3:dashboard 出现"AI 分析师·DeepSeek"面板 + 溯源戳;与市场读数并列、分开标注;无投注词;`check_*` PASS。
4. 锁定/审计:`scout_lock.jsonl` 随调度增长;完赛后 `scout_track_record.json` 回填(准度 + 逆市场谁对)。
5. 底座未改;state/、data/scout/ 仍 gitignored。

---

## 5. 关于"自动 vs 手动"的最终建议

**默认自动**(SC1 调度驱动,按时间档抓+变了才判),**手动强刷保留**(SC4)。这既满足你"不用手点、按时间段自动刷新、变了才重分析"的设想,又留了调试/按需的口子。配额和成本靠 delta 门控住。**这就是合逻辑的生产形态。**
