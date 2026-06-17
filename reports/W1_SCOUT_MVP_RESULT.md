# W1_SCOUT MVP — 结果(会学习的 AI 分析师闭环·第一版)

**日期**: 2026-06-17
**做了什么**: 把"大脑"骨架建好并跑通第一批 call。底座 W1 不动;新增文件全 untracked + 一行 `.gitignore`。

---

## 1. 大脑骨架(全部建好,checker PASS)

| 文件 | 作用 |
|---|---|
| `schemas/w1_scout_bundle_schema.json` | 每场赛前数据包 schema |
| `config/w1_scout_policy.json` | **中间档**敢敢旋钮 + 诚实标注 + 禁词 + 防泄漏 + 成长回灌 |
| `scripts/w1_scout_fetch_api_football.py` | api-football 真因子抓取器;只写 gitignored `data/scout/<fixture_id>.json` |
| `scripts/w1_scout_bundle.py` | 本地组装 bundle,自动合并 `data/scout/` 真因子(缺失如实标 missing,不造值) |
| `scripts/check_w1_scout.py` | 防泄漏 + call 合同(stance 必填/拒纯翻译/FADE 需 HIGH/诚实标注/禁词)+ 反向测试 |
| `scripts/w1_scout_ledger.py` | 赛前锁定(不可变·拒 hindsight)→ 赛后审计(准度 + **逆市场谁对**)→ 回填战绩 |
| `state/scout_track_record.json` · `scout_lessons.md` | 成长引擎(冷启动空,随审计长大) |

---

## 2. 第一批 call(我当分析师,冷启动)

**stance 分布:AGREE 7 · LEAN_DIFFERENT 2 · FADE 0。** 9 场全部赛前锁定(0 hindsight)。

**诚实的关键结果**:本地**只有市场维**(form/xG/伤停**还没抓**),所以——
- 大热/明显强弱(西班牙、挪威、阿根廷、乌拉圭…)→ **AGREE 跟市场**(没有独立因子可逆,逆了就是瞎赌)。
- 两处**敢说敢干**(基于足球常识的弱依据,已标注):
  - **英格兰 vs 克罗地亚**:市场主推英格兰 54%、克罗地亚客胜仅 18% → 我 **LEAN 平/克罗地亚不败**:"克罗地亚赛会型强队被低估,强强对话 54% 偏高"。
  - **巴西 vs 摩洛哥**:市场摩洛哥客胜仅 17% → 我 **LEAN 平**:"摩洛哥上届四强、防守强,客胜给低了"。
- **没有 FADE**:中间档要求"真因子明显背离 + conviction 高"才逆市场;现在没抓取因子,**高信心逆市场被 checker 挡住**——这是旋钮在正确工作,不是怂。

> 这恰好把问题摆明:**只喂市场数据,再聪明的 AI 也只能多数跟市场。** 想让它大胆 LEAN/FADE,缺的就一样东西——**真实因子数据**。机器已就绪,是"数据饿着"。

---

## 3. 成长闭环(已接线,冷启动)

- 9 场已**赛前锁定**(`state/scout_lock.jsonl`);赛果出来后 `w1_scout_ledger.py audit` 会评:准不准 + **它 LEAN 的两场到底对没对**,回填 `scout_track_record.json`。
- 现在战绩=空(还没完赛),**和 prospective 纪律一致——不能无中生有,只能跑出来**。
- 下一轮:AI 开口前先读战绩 + 教训 → 带着经验判断。**这就是"变聪明"。**

---

## 4. 验证 / 红线

- `check_w1_scout` **PASS** + 反向测试(FADE@LOW 拒 / 纯翻译拒 / 禁词抓 / bundle 塞赛果抓)。
- 防泄漏:bundle 与 call 只用赛前;赛果只在审计;锁定拒 hindsight。
- 每条 call 带 `honesty_label(AI 观点·未验证·仅研究·可能错)` + `independent_edge=false`;无投注/资金/命中承诺。
- **底座未碰**:`w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵/市场底座一字未改;SCOUT 全叠在上层,输出 gitignored。

---

## 5. 数据层进展

已补 `scripts/w1_scout_fetch_api_football.py`,复用现有 api-football key bridge,只写 **`data/scout/<fixture_id>.json`**(已 gitignored)。无 key 时直接失败并说明,不会写假数据。

真机试抓 1 场成功:

```text
WROTE data/scout/1539003.json availability={'form': 'available', 'xg_roll': 'available', 'lineup': 'partial', 'injuries': 'partial', 'standings': 'available', 'h2h': 'missing', 'rest_days': 'available'}
```

合并后覆盖从纯 bootstrap 上升为:

```text
{'market': 24, 'lineup': 24, 'injuries': 24, 'form': 1, 'xg_roll': 1, 'standings': 1, 'rest_days': 1}
```

后续有 key/配额时可继续跑:

```bash
python3 scripts/w1_scout_fetch_api_football.py
python3 scripts/w1_scout_bundle.py
python3 scripts/check_w1_scout.py
```

`w1_scout_bundle.py` 会自动合并,bundle 变厚 → AI 重判时就有真凭据去 LEAN/FADE。

**提交**:SCOUT 全是新文件 + 一行 gitignore:
```
git add schemas/w1_scout_bundle_schema.json config/w1_scout_policy.json \
        scripts/w1_scout_fetch_api_football.py scripts/w1_scout_bundle.py \
        scripts/check_w1_scout.py scripts/w1_scout_ledger.py \
        reports/W1_SCOUT_EXECUTION_SPEC.md reports/W1_SCOUT_MVP_RESULT.md \
        reports/W1_SCOUT_TECH_HANDOFF.md .gitignore
git commit -m "W1_SCOUT MVP: AI analyst loop (bundle+policy+checker+ledger+growth); cold start, data-gated"
```

---

## 6. 一句实话

你要的"AI 读数据、敢说敢干、会成长"——**机器我建好了、也跑通了**。但它现在**只有市场数据可读**,所以暂时多数跟市场(那两处 LEAN 是常识弱依据)。**喂它真因子,它才真敢分歧。** 这不是它没用,是它还饿着。先把数据喂上,我们就能看它在赛后审计里到底有几斤几两——而且它会越跑越知道自己几斤几两。
