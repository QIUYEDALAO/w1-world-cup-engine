# W1 Ledger 审计闭环 — 结果

**日期**: 2026-06-17
**做法**: **复用已有的 forward-ledger 预测审计系统闭环**(赛前锁定 → 赛后审计 → 校准),**未新建平行账本**。
**性质**: 研究校准审计(RPS/logloss/Brier),**不是投注盈亏**;账本文件 gitignored;无外部抓取。

---

## 1. 关键认知:闭环机制本就存在,只是没跑

仓库里已有完整一套(全部 gitignored):

| 脚本 | 作用 |
|---|---|
| `w1_forward_lock_pre_match_view.py` | 赛前**不可变**锁定每场 1X2 读数(`lock_as_of_utc`、`snapshot_phase`) |
| `w1_forward_post_match_audit.py` | 对"已锁定 **且** 有本地赛果 **且** 锁定早于开赛"的场次评分,**逐字复制锁定值**,append-only,**拒绝事后诸葛(hindsight)** |
| `w1_forward_prospective_report.py` | 汇总 prospective 校准 |
| `check_w1_forward_ledger.py` / `check_w1_forward_prospective_run.py` | 守护 |

`w1_post_match_audit.jsonl` 之前为空,是因为"真正 prospective 样本=仅赛前锁定 + 已有赛果"的纪律——样本随完赛累积,**这是正确,不是缺陷**(系统自己的注释如此写)。我这次只是**在赛果到位后把审计跑出来**。

---

## 2. 闭环跑通结果

- **审计新增 1 场:法国 vs 塞内加尔。**

| 项 | 值 |
|---|---|
| 赛前锁定 1X2(主/平/客) | 0.66 / 0.22 / 0.12 |
| 实际 | 3:1(主胜 H) |
| p(实际结果) | 0.66 |
| RPS_1x2 | 0.134 |
| logloss_1x2 | 0.423 |
| Brier_1x2 | — |

- 其余 11 条锁定:**跳过(无本地赛果=11)**——它们要么未完赛、要么不在 round1_results,**等结果到位会自动纳入**。
- **拒绝 hindsight=0**:没有把"锁定晚于开赛"的伪赛前混进来。
- 校准汇总:`views_locked=12 · audited=1 · mean_rps_1x2=0.1337`。

**读法**:法国这场,赛前锁定的市场读数给主胜 66%,结果主胜——校准良好(RPS 0.134 远优于无信息)。但 **n=1,只是闭环跑通的单点**,不能当成"模型准"的证据;样本要随完赛累积才有统计意义。

---

## 3. 验证 / 红线

- `check_w1_forward_ledger` / `check_w1_forward_prospective_run` **PASS**。
- 审计**逐字复制锁定预测**,从不修改赛前锁定(不可变);**拒绝 hindsight**;赛果仅作评分对照。
- 账本文件(`data/forward_ledger/*`)**gitignored**——本次闭环**无被跟踪文件改动**(除本报告);未接 API;未改引擎/λ/概率/dashboard。
- 边界不变:研究校准,非投注平台、不输出资金/命中率。

---

## 4. 提交说明

闭环产物全部 gitignored,**只需提交本报告**:

```
git add reports/W1_LEDGER_PROSPECTIVE_AUDIT_RESULT.md
git commit -m "W1 ledger prospective audit: close the loop (France 3-1 audited; honest n=1, no hindsight)"
```

---

## 5. 让闭环持续(建议)

prospective 样本要**随完赛累积**才有意义。最干净的方式是**定时**:每天锁定当日赛前场次 + 跑赛后审计,样本自动长大。
> 可选:我可以建一个**每天定时任务**——`lock_pre_match_view` + `post_match_audit` + `prospective_report` 串跑,你早上看累积的校准。需要你说一句。

整体仍守住:0/A/B/C/D/F + 展示接入 + 审计闭环全部完成;E 封锁;一切市场复述、非独立、不改 λ、不接 API、非投注。
