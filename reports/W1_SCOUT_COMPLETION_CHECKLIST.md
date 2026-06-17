# W1_SCOUT 完成清单(到"最初设定"为止)

**日期**: 2026-06-17
**最初设定**: 一个 AI(DeepSeek)读 W1 数据 + 真因子 → **敢说敢干**的研究判断 → **dashboard 看得见** → **自动刷新** → **随战绩成长**。
**现状一句话**: 全链已跑通,且**本轮起 DeepSeek 的判断已显示在 dashboard 上**(之前的缺口)。剩下的主要是"把 24 场因子抓齐 + cron 上线",闭环就完整转起来。

---

## ✅ 本轮已完成(我,纯展示层,已验证)

- dashboard 新增 **"AI 分析师 · DeepSeek"** 面板(`pScoutAnalyst`):候选共识下方显示 stance(跟市场/偏离/逆市场,颜色区分)+ 判断(方向·比分·信心)+ why + 依据(2-3 条)+ 诚实标注。
- `scripts/w1_scout_embed.py`:把 `state/w1_scout_calls.json` 注入 dashboard `<script id="w1-scout-calls">`(idempotent);已接进 `run_w1_scout_cycle.sh`(每轮自动刷新上屏)。
- `check_w1_visual_dashboard` 强化:要求 `pScoutAnalyst` 面板存在 + 保持"预测控件最后渲染"的顺序断言。
- 验证:`node --check` OK;`check_w1_visual_dashboard / check_w1_scout / check_w1_recommendation_output_policy / check_w1_opportunity_phase_a / check_w1_dashboard_data_binding` **全 PASS**;底座(`w1_score_engine`/λ/矩阵)未碰。

> 打开 dashboard 即可看到 DeepSeek 对每场的判断;现在 24 场多为"跟市场"——当前合法 pre-match 抓取覆盖 **4/24** 场真因子(未来未开赛 3 场 + 既有 1539003),已开赛/完赛场不做赛后伪赛前回填(见 R2)。

---

## 🔧 剩余清单(到完整闭环)

| # | 任务 | 谁 | 说明 |
|---|---|---|---|
| **R1** | 提交本轮可见性改动 | 真机 | dashboard + checker + `w1_scout_embed.py` + `run_w1_scout_cycle.sh`(见 §提交) |
| **R2 ★关键★** | **把 24 场真因子抓齐** | 技术员 | fetcher 已加**重试/退避**(SSL/超时重试 2-3 次)和单场失败不中断;本机当前合法 pre-match 抓取为 **4/24**(未来未开赛 3 场已抓齐 + 既有 1539003)。剩余 20+ 场需要在赛前由 cron 持续抓,不要对已开赛/完赛场做赛后伪赛前回填。抓齐后重判,才更可能出现有据 LEAN/FADE。 |
| **R3** | cron 上线自动驾驶 | 技术员(有 key 机器) | cron `run_w1_scout_cycle.sh`(已含 抓→组装→delta→重判→校验→**embed 上屏**→锁定→审计)。建议赛前 48h 内按时间档(每 2h,临近加密)。dashboard 随之自动刷新。 |
| **R4** | 让审计累积(成长) | 自动 | 完赛后 cron 里的 `ledger audit` 回填 `scout_track_record.json`;下一轮 DeepSeek prompt 带战绩 → 校准更准。**这步会自动发生,只需 R3 在跑。** |
| **R5** | (可选)打磨 | 技术员 | 面板加"已读 N/7 因子"溯源戳;"开始预测"按钮文案改"手动强制刷新"(常态交给 cron)。 |

---

## 诚实预期(别神化)

- R2 抓齐后,因子与市场明显背离的场,DeepSeek 会给 LEAN/甚至 FADE(中间档,FADE 需 conviction=HIGH)——**页面就能看到它"敢分歧"**。
- 但阶段 C 已证明常见因子**难系统性赢市场**;所以它的价值是:**有据、敢表态、可审计、随战绩自我校准**,不是"稳赢"。这点不变。

---

## 红线 / 验收口径(不变)

- 抓取只写 gitignored `data/scout/`;`xg_roll/form` 只取赛前过往场(防泄漏);抓不到=missing 不造值。
- DeepSeek 产出必须过 `check_w1_scout` 才入库/上屏;每条带 `honesty_label`+`independent_edge=false`;无投注/资金/命中词。
- 底座 `w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵未改;SCOUT 全叠在上层;`state/`、`data/scout/` gitignored。

---

## 提交(R1,真机)

```
cd <repo>
git add reports/dashboard/W1_VISUAL_DASHBOARD.html scripts/check_w1_visual_dashboard.py \
        scripts/w1_scout_embed.py scripts/run_w1_scout_cycle.sh \
        reports/W1_SCOUT_AUTOPILOT_TASKS.md reports/W1_SCOUT_COMPLETION_CHECKLIST.md
git commit -m "W1_SCOUT: DeepSeek analyst panel visible on dashboard + embed step in autopilot cycle"
git push origin main
# 复核
python3 scripts/check_w1_visual_dashboard.py && python3 scripts/check_w1_scout.py
# 打开 dashboard:候选共识下方应出现 'AI 分析师 · DeepSeek' 面板
```

完成 R2+R3 后,这套就是你最初要的形态:**DeepSeek 读数据、敢表态、页面看得见、自动按时间档刷新、随赛果成长。**
