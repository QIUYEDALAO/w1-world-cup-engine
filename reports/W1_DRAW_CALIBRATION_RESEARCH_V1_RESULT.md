# W1_DRAW_CALIBRATION_RESEARCH_V1 — RESULT

**类型**: 纯研究 / diagnostic backtest（`research_only=true`、`production_wired=false`）
**日期**: 2026-06-16
**基线 HEAD**: `701511f`
**范围**: World Cup 2018+2022 FULL 子集，n=128（含 OU ladder）。**不外推 1081 / 预选赛 / AH / 2014**。

> 结论先行：**无候选在样本外稳定优于 baseline；11/128 的 Draw 残差是 market-reproduction 工件，不是预测缺陷。不推荐进入下一阶段，更不接生产。** 生产保持 fixed-`DEFAULT_RHO` Dixon-Coles 不变。

---

## 1. Baseline 指标（B0 = 生产现状 fixed ρ）

| 指标 | 值 |
|---|---|
| RPS | 0.4027 |
| logloss (1X2) | 0.9787 |
| Brier | 0.5739 |
| draw calibration ECE | 0.0281 |
| draw-specific logloss | 0.5219 |
| exact-score logloss | 2.8762 |
| OU O2.5 ECE | 0.0807 |
| market reproduction mean abs err | 0.0091 |
| market reproduction pass@0.02 | 0.9141（117/128） |
| **draw-tension 超阈值场次** | **11/128**（与 anomaly review 一致） |

> B0 RPS 与既有 `w1_backtest_full_pipeline_v1.json`（0.4027）一致 → 方法学口径一致。

## 2. 候选指标

| 候选 | RPS | draw ECE | draw logloss | exact logloss | OU2.5 ECE | repro mean | repro pass |
|---|---|---|---|---|---|---|---|
| B0 baseline (fixed ρ) | 0.4027 | 0.0281 | 0.5219 | 2.8762 | 0.0807 | 0.0091 | 0.914 |
| C1 draw-fit ρ（oracle 上界） | 0.4020 | 0.0323 | 0.5177 | 2.8720 | 0.0807 | 0.0006 | 1.000 |
| C2 draw layer | 0.4020 | 0.0319 | 0.5173 | 2.8716 | **0.0842** | 0.0046 | 0.969 |
| C3 parametric WF | 0.4024 | 0.0331 | 0.5198 | 2.8743 | 0.0807 | 0.0045 | 1.000 |

- C1 `rho_draw_fit` 范围 `[-0.30, 0.08]`，均值 `-0.0348`（即需逐场大幅变动 ρ 才能吸收 Draw 残差）。
- C1 标记 `oracle_like=true / market_reconciliation_only=true`——**逐场后验上界，不是生产候选**。

## 3. Draw tension 是否改善？

- **market reproduction**：C1/C3 把 pass 打到 1.000、mean err 降到 ~0.0006/0.0045——复述市场更好了。
- **outcome draw skill**：draw-specific logloss 仅从 0.5219 → 0.5173~0.5198（微弱），draw ECE 反而略**变差**（0.0281→0.0319~0.0331）。
- 即"把市场复述得更准"≠"对真实平局预测更准"。

## 4. 是否牺牲其它指标？

- **C2 有明确 tradeoff**：draw 对齐市场后 **OU O2.5 ECE 0.0807 → 0.0842 变差**（draw 后处理扰动了总进球结构）。
- C1/C3 在 exact-score/OU/BTTS 上大致中性，RPS 改善 ≤ 0.0007。

## 5. 是否通过 walk-forward？

**否。** C3（唯一具泛化形式的候选）chronological 60/20/20：
- test RPS **0.4671** vs baseline 同段 **0.4680** → 仅领先 **0.0009**（< 噪声阈值 0.005）。
- test 上 **draw_logloss 未同向改善**。
- `robust_out_of_sample_signal = false`。

## 6. 过拟合迹象

- C3 train→test RPS gap = **0.0742**（test 明显差于 train）→ 小样本不稳定。
- C1 是逐场后验**上界**，天然乐观；其 RPS 相对 baseline 也只 **+0.0007**——这是"完美 draw 复述"的理论天花板，说明可改善空间本就极小。
- n=128、finals-only、含 knockout/neutral，结构特殊、样本小，任何 <0.001 的差异都在抽样噪声内。

## 7. 是否推荐进入下一阶段？

**不推荐。** `next_stage_recommended = null`，`production_change_recommended = false`。
理由：oracle 上界证明 draw 残差是 **market-reproduction 工件**而非预测缺陷；最具泛化形式的 C3 在样本外不稳定且仅噪声级领先，C2 带 OU tradeoff。在当前 128 场 finals-only 数据下**没有可操作的信号**。

## 8. 何时可重启

仅当**数据规模/结构改变**时值得重跑（例如本地拿到更多赛事或预选赛 OU、样本量显著增大）——届时仍只能进入 `W1_DRAW_CALIBRATION_PROTOTYPE_V2`（research/prototype），**不得直接接生产、不得改 `DEFAULT_RHO`、不得替换 score engine**。

---

## 9. 红线确认

| 红线 | 状态 |
|---|---|
| 未改 `scripts/w1_score_engine.py` | ✅ |
| `DEFAULT_RHO` 仍为 `-0.057766` | ✅ |
| 未改 `config/w1_decision_policy.json` / `w1_odds_movement_thresholds.json` | ✅ |
| 未接 dashboard / predict / build（research 脚本无生产 import/写入；build/predict 不引用本脚本） | ✅ |
| 未抓数据 / 不接 API / 不爬取 / 不采购 | ✅ |
| 不外推 1081 / 预选赛 / AH / 2014 | ✅ |
| 无投注 / 资金 / 命中率承诺表达 | ✅ |
| 全量 checker：41 PASS / 1 FAIL（仅 watcher 沙箱路径，真机 PASS） | ✅ |
| 工作树：研究阶段只新增 5 个文件，未改任何被跟踪生产文件 | ✅ |

## 10. 是否回滚

**否。** 纯研究产物，给出明确"不进生产"结论，作为决策证据保留。

---

## 11. 本机收尾命令（沙箱 .git 锁 + SSH 限制，commit/push 在真机完成）

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune

# commit 1/3：研究 spec + 脚本
git add docs/W1_DRAW_CALIBRATION_RESEARCH_V1.md scripts/w1_draw_calibration_research.py
git commit -m "W1_DRAW_CALIBRATION_RESEARCH_V1 (1/3): research spec + diagnostic backtest script"

# commit 2/3：研究产物 + checker
git add reports/w1_draw_calibration_research_v1.json reports/W1_DRAW_CALIBRATION_RESEARCH_V1.md scripts/check_w1_draw_calibration_research.py reports/W1_EXPERT_PROJECT_REPORT.md
git commit -m "W1_DRAW_CALIBRATION_RESEARCH_V1 (2/3): research outputs + checker + §7"

# commit 3/3：RESULT
git add reports/W1_DRAW_CALIBRATION_RESEARCH_V1_RESULT.md
git commit -m "W1_DRAW_CALIBRATION_RESEARCH_V1 (3/3): RESULT — no robust signal, no production change"

git push origin main

# 复核（真机应 PASS）
python3 scripts/check_w1_draw_calibration_research.py
python3 scripts/w1_draw_calibration_research.py   # 确定性，重跑产物不变
```

> 研究脚本无随机、无 wall-clock 输出，重跑产物逐字节稳定，可安全入仓（不会反复跑脏）。

边界不变：W1 是概率建模与赛前/赛后研究系统；不是投注平台，不输出资金建议，不承诺命中率，不把模型-市场分歧表述为投注机会。
