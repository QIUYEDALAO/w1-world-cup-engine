# W1_SCOUT — 数据抓取清单 + T5 自动分析师 & 全量重判接法

**日期**: 2026-06-17
**两部分**:Part 1 = 技术员精确抓取清单(每场 `data/scout/<fixture>.json` 的字段契约 + 防泄漏);Part 2 = T5 自动分析师 + 全量重判的接法(prompt 模板 + 两种实现 + 每日闭环)。
**不变红线**:只读抓取写 gitignored `data/scout/`;不改 `w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵底座;赛后数据不进赛前;无投注/资金/命中词;每条 call 带 `honesty_label` + `independent_edge=false`。

---

# Part 1 · 技术员精确抓取清单

技术员已建 `scripts/w1_scout_fetch_api_football.py` 并真机抓通 1 场。这里把**字段契约 + 防泄漏规则**钉死,照此把全部世界杯场次抓齐。

## 1.1 每场 `data/scout/<fixture_id>.json` 目标结构(键名对齐 schema)

```json
{
  "fixture_id": "1539003",
  "fetched_at_utc": "2026-06-17T..Z",
  "form_home":  {"last5_wdl":"WWWD","gf_avg":1.5,"ga_avg":0.5,"ppg":2.5,"home_away_split":{"home_ppg":..,"away_ppg":..},"availability":"available"},
  "form_away":  {"last5_wdl":"LDW","gf_avg":1.0,"ga_avg":0.67,"ppg":1.33,"home_away_split":null,"availability":"partial"},
  "xg_roll_home":{"xg_for":null,"xg_against":null,"shots":11.0,"sot":4.5,"window_n":4,"availability":"available"},
  "xg_roll_away":{"xg_for":null,"xg_against":null,"shots":10.0,"sot":4.0,"window_n":1,"availability":"partial"},
  "lineup":     {"confirmed":false,"formation_home":null,"formation_away":null,"key_absences":[],"availability":"partial"},
  "injuries_home":[{"player":"X","importance":"key"}],
  "injuries_away":[],
  "standings":  {"rank_home":1,"rank_away":2,"pts_gap":0,"availability":"available"},
  "h2h":        {"last_n":5,"home_wins":2,"draws":2,"away_wins":1,"availability":"available"},
  "rest_days":  {"home":6,"away":8,"diff":-2,"availability":"available"},
  "api_pred":   {"...": "api-football /predictions 原样,仅对照"},
  "availability":{"form":"available","xg_roll":"available","lineup":"partial","injuries":"partial","standings":"available","h2h":"available","rest_days":"available"}
}
```
> `market` 维不用抓——由 W1 底座提供,`w1_scout_bundle.py` 自动填。`data/scout/` 只放**因子**。

## 1.2 endpoint → 字段映射

| endpoint | 入参 | 取 → 写入 |
|---|---|---|
| `/teams/statistics` | `team, league=1, season=2026` | `form.fixtures(W/D/L)`、`goals.for/against.average`、推 ppg → `form_home/away` |
| `/fixtures?team=&last=N` + `/fixtures/statistics?fixture=<过往场>` | 该队**过往已完赛**场 | 滚动 shots/sot/(xG 若有)→ `xg_roll_home/away`,记 `window_n` |
| `/fixtures/lineups?fixture=<本场>` | 本场 | confirmed/阵型/缺阵 → `lineup`(开赛前通常未公布=partial) |
| `/injuries?team=&league=1&season=2026` | 两队 | 名单+重要度 → `injuries_home/away` |
| `/fixtures/headtohead?h2h=H-A` | 两队 | 近 N 交手 → `h2h` |
| `/standings?league=1&season=2026` | — | 名次/积分差 → `standings` |
| 赛程推算 | — | 距上场天数 → `rest_days` |
| `/predictions?fixture=` | 本场 | 原样 → `api_pred`(仅对照,**不直接采信**) |

## 1.3 ★防泄漏(最重要,checker 之外也要守)★

- **`xg_roll` / `form` 只能取该队【本场 kickoff 之前已完赛】的场次滚动。**
  - ⚠️ 陷阱:`/fixtures/statistics?fixture=<本场>` 返回的是**本场**统计——若本场已开赛/完赛,这就是赛后数据,**绝不能**作 `xg_roll`。
  - 正确:先 `/fixtures?team=&last=N&status=FT` 取**过往**场 id,再对那些 id 取 statistics 滚动。fetcher 应断言所有取数场次 `date < 本场 kickoff`。
- 抓不到 → 该维 `availability:"missing"`,值留 `null`;**绝不造值、不插补**。
- `data/scout/<fixture>.json` 里**不得**出现本场 `actual_score / fulltime / ft_score`(checker 会抓)。

## 1.4 跑法 + 自检(技术员)

```bash
python3 scripts/w1_scout_fetch_api_football.py        # 抓全部未开赛场 → data/scout/*.json
python3 scripts/w1_scout_bundle.py                    # 合并 → state/w1_scout_bundles.json
python3 scripts/check_w1_scout.py                     # 必须 PASS;form/xg_roll 覆盖应明显上升
```
验收点:`非missing覆盖` 里 form/xg_roll/standings/rest_days 从 1 升到接近场次数。

---

# Part 2 · T5 自动分析师 + 全量重判

让"分析师"从我手动 → **自动对全部 24 场重判**,并每日随数据/赛果自学。

## 2.1 分析师 I/O 契约(必须过 `check_w1_scout`)

**输入(每场)**:`bundle[fixture]`(含真因子)+ `scout_track_record.json` 相关切片 + `scout_lessons.md`。
**输出(每场)**:一个 call 对象,字段/规则**严格对齐** `config/w1_scout_policy.json` 的 `call_required_fields` 与敢敢门槛(`check_w1_scout.validate_call` 是唯一闸门)。

## 2.2 Prompt 模板

**System(分析师人格 + 硬规则)**:
```
你是足球研究分析师。读"赛前因子包 + 你自己的历史战绩 + 教训",对这场给出有据判断。
规则(中间档 boldness):
- 默认 AGREE 跟市场;只有真因子(form/xG/伤停/首发/排名)明显背离市场、且你有把握,才 LEAN_DIFFERENT;
  只有背离很强、conviction=HIGH 才 FADE_MARKET。
- 必须 stance 表态,必须给 why_cn(引具体因子)+ key_factors_cn;禁止只复述赔率(纯翻译会被拒)。
- 缺数据(availability=missing)别假装有依据;首发未确认要降信心。
- 禁止任何投注/资金/命中/稳赢词。confidence 用你历史校准过的尺度。
- 只输出 JSON,字段:fixture_id, call{outcome_lean,scoreline_lean,confidence},
  market_divergence{stance,where_cn,why_cn}, key_factors_cn[], conviction(LOW|MEDIUM|HIGH),
  track_record_context_cn, honesty_label("AI 观点·未验证·仅研究·可能错"), independent_edge(false)
```
**User(每场)**:
```
[市场读数] p_home/p_draw/p_away = ...
[因子包] {bundle 的 form/xg_roll/lineup/injuries/standings/h2h/rest_days,含 availability}
[你的战绩] overall x-y;by_stance FADE n/beat_market;相关场景切片...
[教训] {scout_lessons.md 摘要}
按上面规则给出这场的 call(JSON)。
```

## 2.3 实现:两条路(任选,可先 A 后 B)

### 路 A — 定时 Claude(最省事,推荐起步)
挂一个**每日 Cowork 定时任务**,提示词=「读 `state/w1_scout_bundles.json` + 战绩 + 教训,对全部场按 SCOUT 规则产出 `state/w1_scout_calls.json`,再 `w1_scout_ledger.py lock`,完赛的 `audit`」。由我(Claude)当分析师,无需额外 API key。

### 路 B — Headless 脚本(可无人值守,生产化)
新增 `scripts/w1_scout_analyst.py`,默认固定调 DeepSeek-V4-Pro(API model id: `deepseek-v4-pro`; OpenAI-compatible chat completions) 自动产 call;需要换供应商时用 `W1_SCOUT_LLM=openai` 或 `W1_SCOUT_LLM=custom`。

```bash
# 默认固定 DeepSeek-V4-Pro
DEEPSEEK_API_KEY=... python3 scripts/w1_scout_analyst.py

# OpenAI-compatible 切换
W1_SCOUT_LLM=openai OPENAI_API_KEY=... python3 scripts/w1_scout_analyst.py

# 任意 OpenAI-compatible endpoint
W1_SCOUT_LLM=custom \
W1_SCOUT_BASE_URL=https://example.com/v1/chat/completions \
W1_SCOUT_MODEL=your-model \
W1_SCOUT_API_KEY=... \
python3 scripts/w1_scout_analyst.py
```

**关键**:
- 模型产出**必须过 `check_w1_scout.validate_call` 才入库**;不过就带报错重试/丢弃。
- `honesty_label` 与 `independent_edge=false` 在代码里强制写死,不交给模型自由发挥。
- 无 key 直接退出,不产假数据。
- 输出只写 gitignored `state/w1_scout_calls.json`。

## 2.4 全量重判 + 每日闭环(一条龙)

```bash
# 1) 抓数据(技术员)            data/scout/*.json
python3 scripts/w1_scout_fetch_api_football.py
# 2) 组装                        state/w1_scout_bundles.json
python3 scripts/w1_scout_bundle.py
# 3) 全量重判(路A定时Claude 或 路B脚本) → state/w1_scout_calls.json(全部24场)
python3 scripts/w1_scout_analyst.py        # 路B
# 4) 闸门校验(必须PASS)
python3 scripts/check_w1_scout.py
# 5) 赛前锁定 + 完赛审计 + 回填战绩
python3 scripts/w1_scout_ledger.py lock
python3 scripts/w1_scout_ledger.py audit
```
**每日定时**串这 5 步:数据→重判→校验→锁定→审计。完赛累积 → `scout_track_record.json` 长大 → 下一轮分析师 prompt 带着战绩 → **越跑越懂自己**。

## 2.5 成长怎么"真发生"(别神化)

- **校准**:audit 累积后,把"实测 confidence vs 命中率"写进 `track_record.calibration`;分析师 prompt 用它把过度自信压下去。
- **教训**:每轮 audit 后,把"FADE 在哪类场景 beat_market、哪类翻车"蒸馏一两条写进 `scout_lessons.md`;下轮自动读。
- 这是**经验累积 + 置信校准**,不是重训权重——诚实、可追溯。能学到"well-calibrated + 知道何时该逆/该跟",**不保证赢市场**(阶段 C 已证明难)。

---

## 验收口径(我复核)

1. `data/scout/*.json` 字段对齐 §1.1;`xg_roll/form` 确为**赛前过往场**滚动(无当场泄漏);抓不到=missing。
2. 全量重判后 `state/w1_scout_calls.json` 覆盖全部场;**`check_w1_scout` PASS**(闸门生效)。
3. call 有据(why+factors)、stance 合规、FADE 仅 HIGH;honesty_label + independent_edge=false;无禁词。
4. `w1_scout_ledger.py audit` 能回填战绩(准度 + 逆市场谁对);校准/教训随轮次更新。
5. 底座未改;输出 gitignored;无投注语言。
