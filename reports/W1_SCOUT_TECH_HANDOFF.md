# W1_SCOUT 技术员交接清单

**日期**: 2026-06-17
**一句话**: 大脑(分析师闭环)已建好并跑通,**现在只缺真因子数据**。技术员的核心任务=**扩抓 api-football 真因子,写到 `data/scout/<fixture_id>.json`**;其余我已就绪。

---

## A. 已完成(不要重做)

| 模块 | 状态 | 关键文件 |
|---|---|---|
| W1 底座(市场反解 λ/比分矩阵) | ✅ 不动 | `w1_score_engine.py`(红线,勿改) |
| FiveDim Lite 0/A/B | ✅ | `w1_fivedim_lite.py`、`check_w1_fivedim_lite.py`、dashboard 五维就绪度 |
| 因子历史验证 C | ✅(结论:常见因子打不过市场) | `w1_factor_*`、`W1_FIVEDIM_HISTORICAL_VALIDATION.md` |
| Confidence 软用 D | ✅ | `w1_confidence_adjustment.py` |
| Primary Read F + 接入展示 | ✅ | `w1_primary_read_*`、dashboard"研究结论"行 |
| Ledger 审计闭环 | ✅ | `w1_forward_post_match_audit.py`(已跑) |
| **W1_SCOUT 大脑骨架** | ✅ 全绿 | 见下表 |

**W1_SCOUT 已建好的部分(`check_w1_scout.py` PASS):**
- `schemas/w1_scout_bundle_schema.json` — 数据包 schema
- `config/w1_scout_policy.json` — 中间档敢敢策略 + 诚实/禁词/防泄漏/成长
- `scripts/w1_scout_fetch_api_football.py` — api-football 真因子抓取器;只写 `data/scout/<fixture>.json`
- `scripts/w1_scout_bundle.py` — 组装 bundle(**已含 `data/scout/<fixture>.json` 自动合并**)
- `scripts/check_w1_scout.py` — call/bundle 合同 + 反向测试
- `scripts/w1_scout_ledger.py` — 赛前锁定 + 赛后审计 + 回填战绩
- `state/scout_track_record.json`、`state/scout_lessons.md` — 成长引擎(冷启动)
- 第一批 9 个 call 已锁定(`state/w1_scout_calls.json`、`state/scout_lock.jsonl`)

---

## B. 技术员待办(开展工作)

### T1 ★核心★ 扩抓真因子 → `data/scout/<fixture_id>.json`
对每场(先世界杯)用 api-football 拉以下,**只写 `data/scout/<fixture_id>.json`**(已 gitignored):

| endpoint | 取字段 → 映射到 bundle |
|---|---|
| `/teams/statistics?team=&league=1&season=2026` | 近5/10场 W-D-L、场均进/失球、ppg、主客分项 → `form_home`/`form_away` |
| `/fixtures/statistics?fixture=`(取**该队过往场**,滚动) | xG_for/against、shots、sot → `xg_roll_home`/`xg_roll_away` |
| `/fixtures/lineups?fixture=` | confirmed、阵型、缺阵 → `lineup` |
| `/injuries?fixture=`(或 league) | 伤停名单+重要度 → `injuries_home`/`injuries_away` |
| `/fixtures/headtohead?h2h=A-B` | 近 N 次交手 → `h2h` |
| `/standings?league=1&season=2026` | 排名/积分差 → `standings` |
| (按赛程算) | 距上场天数 → `rest_days` |

**文件格式**:键名对齐 `schemas/w1_scout_bundle_schema.json`;每维带 `availability: available/partial/missing`。**抓不到的标 `missing`,绝不造值。**
**边界**:只用 `APIFOOTBALL_KEY`;只写 `data/scout/`;**不改** `w1_score_engine`/`DEFAULT_RHO`/`build_w1_dashboard_data.py` 的 λ·矩阵底座。

已落地脚本:

```bash
python3 scripts/w1_scout_fetch_api_football.py          # 默认只抓未开赛 dashboard 场次
python3 scripts/w1_scout_fetch_api_football.py --limit 1 # 小范围验证
```

真机验证已写入 1 场 gitignored 样本:

```text
data/scout/1539003.json
availability: form/xg_roll/standings/rest_days = available; lineup/injuries = partial; h2h = missing
```

无 `APIFOOTBALL_KEY` / `OPENCLAW_APIFOOTBALL_KEY` 时脚本直接退出,不写假数据。

### T2 跑通链路并自检
```
python3 scripts/w1_scout_bundle.py          # 合并 data/scout/ → state/w1_scout_bundles.json
python3 scripts/check_w1_scout.py           # 必须 PASS;factor 覆盖应从 missing→available 上升
```
验收点:bundle 里 `form/xg_roll/lineup` 的 availability 不再全 missing。

### T3 提交 SCOUT(新文件 + 一行 gitignore)
```
git add schemas/w1_scout_bundle_schema.json config/w1_scout_policy.json \
        scripts/w1_scout_fetch_api_football.py scripts/w1_scout_bundle.py \
        scripts/check_w1_scout.py scripts/w1_scout_ledger.py \
        reports/W1_SCOUT_EXECUTION_SPEC.md reports/W1_SCOUT_MVP_RESULT.md \
        reports/W1_SCOUT_TECH_HANDOFF.md .gitignore
git commit -m "W1_SCOUT MVP + data/scout factor fetch (bundle/policy/checker/ledger/growth)"
git push origin main
```
> 注:`state/`、`data/scout/` 均 gitignored,不进库(本地运行态)。

### T4(可选)每日定时跑闭环
`scripts/w1_scout_ledger.py lock`(赛前)+ 完赛后 `... audit` → 自动锁定+审计+回填战绩。可挂每日定时。

### T5(可选/后续)自动化 AI 分析师
目前"分析师"是我手动产 call。长期可挂一个每日 LLM 调用:读 `bundle + track_record + lessons` → 生成 call(格式对齐 `check_w1_scout` 合同)。这步等数据稳了再做。

---

## C. 验收口径(完成后我来复核)

1. `data/scout/<fixture>.json` 字段对齐 schema;抓不到标 missing(无造值)。
2. `w1_scout_bundle.py` 合并后,`check_w1_scout.py` **PASS**;factor availability 覆盖明显上升。
3. **防泄漏**:bundle/call 无任何当场赛后统计(checker 硬断言)。
4. 赛后 `w1_scout_ledger.py audit` 能回填 `scout_track_record.json`(准度 + 逆市场谁对)。
5. **底座未改**;无投注/资金/命中词;每条 call 带 honesty_label + `independent_edge=false`;FADE 仍受 conviction=HIGH 门控。

---

## D. 红线(规则变更后)

✅ **允许**联网抓取(api-football,你 pipeline)。
❌ 不改 `w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵 的市场底座;❌ 不造值(抓不到=missing);❌ 赛后数据不进赛前判断;❌ 不输出投注/资金/命中承诺;❌ 不声明"独立优势/稳赢"。SCOUT 全叠在底座上层,输出落 gitignored。

---

## E. 数据喂上之后会发生什么

bundle 变厚 → 我(或 T5 的自动分析师)重判 → **call 从"多数跟市场"变成"有据地敢分歧(LEAN/FADE)"** → 赛后审计 → 战绩+教训累积 → 下一轮 AI 带着经验判断,**越跑越懂自己**。这就是闭环开始转起来。
