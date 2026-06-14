# W1 rho 校准套件 集成说明(交付 Codex)

> 目标:把 Dixon-Coles rho 校准这一套接入项目, 作为**离线研究/校准工具**——它不参与
> live dashboard 构建, 唯一的生产副作用是:在严格闸门通过后, 由人工把
> `w1_score_engine.DEFAULT_RHO` 这**一个常数**改成拟合值。
>
> 核心安全目标:**任何情况下都不能把合成数据拟合出的 rho 写进生产**(已做成机制, 见 §7)。
>
> 边界:研究/校准工具, 不构成投注、下注或资金操作意见, 不承诺命中率。

---

## 1. 进入项目的文件(PROD)

| 文件 | 角色 | 说明 |
|---|---|---|
| `scripts/w1_rho_calibration.py` | 校准工具 | 读历史 CSV → 市场反解 λ → 全局 rho 的 MLE → 报告(含机器可读生产闸门) |
| `scripts/check_w1_rho_calibration.py` | checker | 5 类不变量, 含"防合成进生产"闸门, 入 CI |
| `config/w1_rho_provenance.json` | rho 出处 | 把生产 rho 与一份达标报告绑死的审计记录; 初始为**占位态** |
| `data/historical/rho_calibration_template.csv` | schema 锁 | 字段定死的空表头, 既是规范也被 checker 校验 |

依赖:`w1_score_engine.py`(已在项目)。新增**可选**依赖 `matplotlib`(仅画可靠性图, 缺失自动跳过)。`numpy/scipy` 项目已有。

> `w1_score_engine.py` **不改**(rho 校准不动引擎逻辑)。引擎里的 `DEFAULT_RHO` 仍是占位值, 只有 §5 的流程能改它。

---

## 2. 仅 DEV/TEST 的东西(不得当真实/生产)

| 文件 | 处置 |
|---|---|
| `scripts/make_synthetic_history.py` | **保留在 `scripts/`**(checker 的还原冒烟要导入它), 但它是 [DEV/TEST]。它生成的数据带 `competition=SYNTH` 标记, 会被自动识别为合成。 |
| 合成 CSV(如 `SYNTHETIC_demo_*.csv`) | **不要提交**, 或只放 `tests/fixtures/` 并保留 `SYNTHETIC_` 前缀。绝不放进 `data/historical/`。 |
| 合成数据生成的 `W1_RHO_CALIBRATION_REPORT.md` / `.png` | **不要**作为项目的"校准报告"提交。它头部会标 `PRODUCTION_READY: NO / INPUT_SYNTHETIC: YES`。真实报告等真实 CSV 跑出来再提交。 |

关键约束:**`data/historical/` 目录只放真实历史数据 + 模板**, 合成数据一律不进该目录。这是 §7 防线之一。

---

## 3. 真实 CSV 放哪里

- 路径:`data/historical/rho_calibration_real.csv`(或带日期 `..._2026xxxx.csv`)。
- 字段**必须**严格匹配 `rho_calibration_template.csv` 的表头(checker 会校验模板与脚本 schema 一致)。
- **必需列(拟合 rho 严格只要这 11 个)**:`match_date, home_team, away_team, closing_home_odds, closing_draw_odds, closing_away_odds, closing_ou_main_line(半盘如2.5), closing_over_odds, closing_under_odds, home_goals, away_goals`。
- **可选列(现在一起记, 不进 rho 拟合, 缺只 WARN)**:`market_snapshot_lead_minutes, competition, neutral_venue, lineup_completeness, closing_ah_main_line, closing_fair_total_override, bookmaker_count`。
- **`competition` 列对真实数据请填真实赛事名**(如 `intl_friendly` / `wc_qualifier`)。**保留字 `SYNTH` 仅供合成数据**——真实数据写 `SYNTH` 会被误判为合成而拒绝写生产。
- **建议 gitignore 真实赔率 CSV**(盘口数据可能有授权限制 + 体积大), 但**必须提交** `config/w1_rho_provenance.json` 和真实报告作为审计证据。

`python3 scripts/w1_rho_calibration.py --print-schema` 可随时打印锁定字段。

---

## 4. 跑真实 CSV 的命令

```bash
python3 scripts/w1_rho_calibration.py \
  --csv data/historical/rho_calibration_real.csv \
  --report reports/W1_RHO_CALIBRATION_REPORT.md \
  --bootstrap 200 \
  --min-prod-sample 500
```

- `--bootstrap 200`:95% CI(慢, 几百场约数分钟); 日常迭代可省, 出正式结论时开。
- `--min-prod-sample 500`:允许写生产 rho 的最小有效样本(与 checker 阈值一致)。
- 跑完看报告 **§0 生产可用性** 段:`PRODUCTION_READY: YES/NO` + 机器可读的 `INPUT_SYNTHETIC / VALID_SAMPLE / RPS_GAP_MODEL_MINUS_MARKET / RHO_HAT`。
- stdout 末行直接打印 `PRODUCTION_READY=YES/NO`。

---

## 5. 什么时候才允许改 DEFAULT_RHO

**只有当报告 §0 给出 `PRODUCTION_READY: YES` 时**, 才允许改。脚本判 YES 的全部条件(同时满足):

1. `INPUT_SYNTHETIC: NO`(非合成);
2. `VALID_SAMPLE >= 500`(建议 1000–2000 更稳);
3. `RPS_GAP_MODEL_MINUS_MARKET < 0.01`(模型 1X2 RPS ≈ 市场, 否则反解/去水有问题, rho 无意义);
4. `rho_hat` 未顶到搜索边界 `[-0.20, 0.05]`。

满足后的**写入流程(单 commit, 二者同改, 否则 checker 报错)**:

```
1) 改 scripts/w1_score_engine.py:
     DEFAULT_RHO = <报告里的 RHO_HAT>
   并在该行加溯源注释: # calibrated 2026-xx-xx, n=<VALID_SAMPLE>, report=<path>

2) 改 config/w1_rho_provenance.json:
     {
       "default_rho": <同上 RHO_HAT>,
       "calibrated": true,
       "source_report": "reports/W1_RHO_CALIBRATION_REPORT.md",
       "valid_sample": <VALID_SAMPLE>,
       "input_synthetic": false,
       "calibrated_at": "2026-xx-xx",
       "note": "fitted on real history"
     }

3) 提交真实报告 reports/W1_RHO_CALIBRATION_REPORT.md(作为背书证据)。

4) 重跑 checker(见 §6)全绿。

5) 因比分矩阵依赖 rho, 重跑 score-matrix 相关 checker 与 dashboard 构建, 确认无回归。
```

**绝不允许**:绕过闸门手改 `DEFAULT_RHO`; 用世界杯进行中的 64 场拟合 rho; 分桶拟合多个 rho(只拟合一个全局 rho)。

---

## 6. 需要的 checker

**新增并入 CI:`scripts/check_w1_rho_calibration.py`**(已交付), 守 5 类不变量:

- **A schema 锁**:模板 CSV 表头 == 脚本 `REQUIRED+OPTIONAL`(防字段悄悄漂移)。
- **B 还原冒烟**:用已知 `rho_true=-0.10` 生成 n=1000 → 拟合应还原(|diff|<0.06)、未顶界、DC 优于独立 Poisson。**这是防有人改坏拟合代码的回归闸**(约 7s)。
- **C 合成守卫**:`is_synthetic` 必须能识别 `competition=SYNTH`。
- **D 生产 rho 出处闸门(核心)**:`provenance.calibrated=true` 时, 必须有非合成、`VALID_SAMPLE>=500`、`PRODUCTION_READY: YES`、rho 值与 `DEFAULT_RHO` 一致的报告背书; 占位态则放行。
- **E 源码守卫**:新脚本不得含违禁词 / fixture_id 硬编码。

```bash
python3 scripts/check_w1_rho_calibration.py
```

**改 rho 后必须连带重跑**(矩阵依赖 rho):`check_w1_score_matrix_batch.py`、`check_w1_score_matrix.py`、`check_w1_dashboard_data_binding.py`、`check_w1_visual_dashboard.py`。

> 反向验证已做:把 provenance 改成 `calibrated=true` 却指向合成报告 → checker FAIL(背书报告 `PRODUCTION_READY != YES`); 样本 120<500 → FAIL。闸门确实拦得住。

---

## 7. 如何防止把合成 rho 写进生产(四层, 机制性)

1. **脚本自动识别合成**:生成器给合成数据写 `competition=SYNTH`; 校准脚本 `is_synthetic()` 检测到即把报告标 `INPUT_SYNTHETIC: YES` 并强制 `PRODUCTION_READY: NO`——**不依赖操作者记得加任何标志**。
2. **出处文件绑定**:生产 rho 的唯一合法来源是 `config/w1_rho_provenance.json`, 它把 `DEFAULT_RHO` 与一份具体报告 + 样本量 + 非合成标记绑死。
3. **checker D 闸门**:CI 强制——`calibrated=true` 而无非合成达标报告背书, 直接 FAIL。**合成报告永远是 `PRODUCTION_READY: NO`, 所以永远无法背书生产 rho。**
4. **目录隔离**:`data/historical/` 只放真实数据; 合成 CSV/报告不进生产目录(进 `tests/fixtures/` 且带 `SYNTHETIC_` 前缀)。

记忆口诀给 Codex:**合成数据 → 永远 PRODUCTION_READY=NO → 永远过不了出处闸门 → 永远进不了 DEFAULT_RHO。**

---

## 8. 验收顺序

```
1. python3 scripts/check_w1_rho_calibration.py          # 占位态应 PASS
2. (真实 CSV 到位后) 跑 §4 命令 → 看报告 §0
3. 若 PRODUCTION_READY=YES → 按 §5 流程改 DEFAULT_RHO + provenance + 提交报告
4. 重跑 §6 全部 checker(含 score-matrix 系列)→ 全绿
5. 重跑 dashboard 构建 → 抽查矩阵数值随新 rho 合理变化, 无其它回归
```

当前状态:`provenance.calibrated=false`(占位), `DEFAULT_RHO=-0.10`(占位), checker PASS。**等真实历史 CSV。**

---

## 9. 一句话给 Codex

rho 校准是离线工具, 不碰 live 链路; 进项目的是校准脚本+checker+出处文件+模板, 合成生成器是 DEV/TEST(留 scripts/ 供 checker 冒烟用); 真实 CSV 放 `data/historical/`(可 gitignore)、字段须匹配模板; **只有报告 `PRODUCTION_READY: YES` 才能改 `DEFAULT_RHO`, 且必须同步更新 provenance 并附报告**; 合成数据因 `competition=SYNTH` 永远判 NO、永远过不了 checker D 闸门, 从机制上进不了生产。
