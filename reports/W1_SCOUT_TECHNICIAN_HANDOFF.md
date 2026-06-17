# W1_SCOUT 技术员交接清单

**日期**: 2026-06-17
**一句话**: AI 分析师的"大脑"我已建好并验证通过;**技术员负责把未来 fixture 的赛前真实因子数据喂进来**(数据层),喂上之后 AI 才能从"多数跟市场"变成"有据地敢分歧"。
**底座红线不变**:不改 `scripts/w1_score_engine.py` / `DEFAULT_RHO` / build λ·矩阵 / 受保护 config / dashboard 的市场底座。SCOUT 全叠在上层。

---

## A. 已完成(我做的,已验证,技术员勿重做)

**"大脑"骨架 —— `check_w1_scout.py` PASS(含反向测试):**

| 文件 | 状态 | 作用 |
|---|---|---|
| `schemas/w1_scout_bundle_schema.json` | ✅ | 每场赛前数据包 schema(技术员产出要对齐它) |
| `config/w1_scout_policy.json` | ✅ | 敢敢旋钮=MEDIUM、诚实标注、禁词、防泄漏、成长回灌 |
| `scripts/w1_scout_bundle.py` | ✅ | 组装 bundle:**自动合并** `data/scout/<fid>.json` 里技术员抓到的真因子 |
| `scripts/check_w1_scout.py` | ✅ | 防泄漏 + call 合同 + 反向测试(技术员产出必须过它) |
| `scripts/w1_scout_ledger.py` | ✅ | 赛前锁定(拒 hindsight)→ 赛后审计(准度+逆市场谁对)→ 回填战绩 |
| `state/scout_track_record.json` · `scout_lessons.md` | ✅ | 成长引擎(冷启动空,随审计长大) |
| `reports/W1_SCOUT_EXECUTION_SPEC.md` | ✅ | 完整规格(字段细节看这份 §2) |

**已跑通**:24 场 bundle、DeepSeek call、赛前锁定与赛后审计。当前合法赛前真因子只覆盖部分仍未开赛/已提前抓取 fixture;已开赛/完赛场不做伪赛前回填。

---

## B. 技术员任务(数据层 —— 解锁"敢说敢干"的唯一前提)

### T1 — 扩抓真因子,写入 `data/scout/<fixture_id>.json`(核心)

复用现有 api-football 桥(`w1_local_predict_server.py` / `w1_watcher.sh` 的 `x-apisports-key` 模式),对**每场仍未开赛的 fixture**新增抓取:

| api-football endpoint | 抽取 → bundle 字段 |
|---|---|
| `/teams/statistics?team=&league=1&season=2026` | 近况 → `form_home/away`: last5_wdl, gf_avg, ga_avg, ppg, home_away_split |
| `/fixtures/statistics?fixture=`(取该队**过往**场,滚动) | → `xg_roll_home/away`: xg_for, xg_against, shots, sot, window_n |
| `/fixtures/lineups?fixture=` | → `lineup`: confirmed, formation_home/away, key_absences |
| `/injuries?league=1&season=2026`(按队过滤) | → `injuries_home/away`: [{player, importance}] |
| `/fixtures/headtohead?h2h=A-B` | → `h2h`: last_n, home_wins, draws, away_wins |
| `/standings?league=1&season=2026` | → `standings`: rank_home, rank_away, pts_gap |
| 赛程推算 | → `rest_days`: home, away, diff |

**输出**:每场一个 `data/scout/<fixture_id>.json`,字段名对齐 `schemas/w1_scout_bundle_schema.json`;每维填 `availability: available/partial/missing`;顶层 `asof_pre_kickoff: true`。
**抓不到的就如实 `missing`,不造值。**

> 🔴 **最重要的红线(防数据泄漏)**:bundle 只能放**赛前可得**数据。
> `xg_roll` = 该队**本场之前**历史场次的滚动值,**绝不是本场的赛后 xG**;**绝不放** actual_score / 本场 fulltime 统计。`check_w1_scout.py` 会扫泄漏并 FAIL。
> 已开赛/完赛 fixture 只允许进入赛后 audit,不允许为了覆盖率补写伪赛前因子。

**验收**:
1. `data/scout/<fid>.json` 为即将开赛场次生成;
2. `python3 scripts/w1_scout_bundle.py` → "非missing维度覆盖" 明显超过 {market}(form/xg_roll/lineup… 变 available);
3. `python3 scripts/check_w1_scout.py` **PASS**(无泄漏、无禁词)。

### T2 — 跑闭环

```
python3 scripts/w1_scout_bundle.py        # 合并真因子,重建 bundle
# (AI 分析师据此重判 → state/w1_scout_calls.json;MVP 阶段由我生成,长期可挂 LLM 定时)
python3 scripts/w1_scout_ledger.py lock    # 赛前锁定(只锁未开赛,拒 hindsight)
# …比赛结束、round1_results 有赛果后…
python3 scripts/w1_scout_ledger.py audit   # 评准度 + 逆市场谁对 → 回填 scout_track_record.json
python3 scripts/check_w1_scout.py          # 必须 PASS
```

### T3 — 提交(全新文件 + 一行 .gitignore;`state/`、`data/scout/` 已 gitignored)

```
git add schemas/w1_scout_bundle_schema.json config/w1_scout_policy.json \
        scripts/w1_scout_bundle.py scripts/check_w1_scout.py scripts/w1_scout_ledger.py \
        reports/W1_SCOUT_EXECUTION_SPEC.md reports/W1_SCOUT_MVP_RESULT.md \
        reports/W1_SCOUT_TECHNICIAN_HANDOFF.md .gitignore
git commit -m "W1_SCOUT: AI analyst loop (brain) + data-layer handoff"
```

### T4(可选)— 每日定时

把 T2 串成定时任务:每天抓当日赛前场次 → bundle → 锁定;赛后 → 审计 → 成长。样本自动累积。

---

## C. 红线汇总(技术员必须守)

- ✅ 现在**允许**联网抓 api-football;❌ 但**不改 W1 市场底座**(引擎/ρ/build λ·矩阵/受保护 config/dashboard)。
- 🔴 **防泄漏**:只放赛前数据;滚动 xG 取历史前场;**本场赛后统计/比分绝不进 bundle**。
- ❌ 不造假(抓不到=missing);❌ 不写投注/资金/命中承诺词;每条 call 留 `honesty_label` + `independent_edge=false`。
- 产出落 `data/scout/`、`state/`(均 gitignored);不碰底座被跟踪文件逻辑。
- 完成后由我(或定时 LLM)当分析师重判 + 验收。

---

## D. 完成后回到我这

技术员把 `data/scout/` 喂上 → 我重判生成有真凭据的 call(会出现 LEAN/FADE)→ 赛后审计 → 战绩累积。**那时再看它"敢说敢干"且"逆市场到底对不对"。**
