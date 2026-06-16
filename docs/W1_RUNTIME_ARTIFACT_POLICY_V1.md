# W1_RUNTIME_ARTIFACT_POLICY_V1

阶段：`W1_RUNTIME_ARTIFACT_TRIAGE_V1`（治本，修正版范围）
目的：把"每次 predict/watcher/build 都会变"的运行产物移出版本控制,改为 gitignored + 按需重建;读取它们的 checker 在产物缺失时 SKIP(给重建命令),产物存在时仍严格校验。**只移出被证明是运行生成物的文件,绝不移出源/模板/事实数据。**

## 1. 文件分类

| 类别 | 文件 | 处置 |
|---|---|---|
| **运行生成物(本阶段移出跟踪)** | `reports/dashboard/assets/w1_dashboard_data.json`、`state/`(全部) | `git rm --cached` + gitignore;本地保留,按需重建 |
| **源/模板/事实(必须保留跟踪)** | `reports/dashboard/W1_VISUAL_DASHBOARD.html`(手写模板+JS)、`data/results/round1_results.json`(赛果事实)、`data/processed/match_cards/group_stage_round1/*.json`(人工/快照源卡,无生成器) | 保持跟踪 |
| **本地/生成数据(一直 gitignored)** | `data/local_odds/*`、`data/processed/international/*`、`data/raw/*`、`data/forward_ledger/*` | 不入仓 |
| **证据报告(入仓)** | `reports/W1_LOCAL_ODDS_2026_QUALITY_CHECK.md`、`reports/W1_LOCAL_ODDS_HISTORICAL_QUALITY_CHECK.md`(聚合证据,非 runtime) | 入仓 |

## 2. 重建命令

```bash
W1_DISABLE_API_ENV_BRIDGE=1 python3 scripts/build_w1_dashboard_data.py   # 重建 w1_dashboard_data.json + state
```

## 3. checker skip-safe 语义

读取上述运行产物的 checker(visual_dashboard、dashboard_data_binding、watcher、report_templates 等,W1_RUNTIME_CHECKER_CLEANUP_V1 已改造)：

- 产物缺失(如新 clone 未重建)→ **SKIP**,输出重建命令,不 FAIL。
- 产物存在 → 继续严格校验结构/字段/合法状态域/安全断言(不因 ignore 而放松)。

新增 `scripts/check_w1_runtime_artifact_policy.py` 强制本政策:运行产物未被跟踪、源/模板/事实仍被跟踪、本地/生成数据未入仓、QC 证据在仓。

## 4. 为什么不再提交"最新 dashboard 快照"

dashboard_data.json 每次 build 都会变(含 `generated_at_utc` 等),提交它会让仓库被每次运行跑脏、并反复触发 checker。改为本地重建后,仓库只保留源/模板/配置/checker/报告,保持干净。要看最新 dashboard,本地跑一次 build 即可。

## 5. 已知未尽（需后续阶段,本阶段不做）

完整"运行后 git 仍 clean"还差两处真重构(已登记):

- **`W1_DASHBOARD_TEMPLATE_DATA_SPLIT`**：`build` 目前把数据 + `generated_at_utc` 内嵌进**被跟踪的 HTML**,每次 build 仍会改脏 HTML。治本=tracked HTML 模板运行时加载 gitignored 的 `assets/*.json`,模板不再内嵌数据。
- **`W1_PREDICT_OVERLAY_SPLIT`**：`predict`/`build` 会把 `live_refresh` 写回**被跟踪的源卡**。治本=运行态写到单独的 gitignored overlay,不碰源卡。

在这两步完成前,一次 build 仍会改脏 tracked HTML 和被刷新的 card——这是有意保留的源/模板,不在本阶段强行 untrack。

## 6. 边界

仓库卫生治理,不改模型:未改 `w1_score_engine`/`DEFAULT_RHO`/`decision_policy`/`thresholds`;未造假数据;未弱化 checker 安全断言;不抓取;无投注/资金/命中率表达。
