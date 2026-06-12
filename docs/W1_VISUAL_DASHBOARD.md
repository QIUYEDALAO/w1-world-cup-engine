# W1 可视化 Dashboard 原站 UI 复刻版

**入口:** `reports/dashboard/W1_VISUAL_DASHBOARD.html`  
**数据:** `reports/dashboard/assets/w1_dashboard_data.json`

## 定位

W1_VISUAL_DASHBOARD 是给老板直接查看的中文静态总控台。页面可以直接双击打开，不需要 Web 服务，不调用外部 API。

本版根据 `https://worldcup.youliaoyun.com/` 真实站点截图复刻视觉风格，而不是仅参考 README / skill / TUTORIAL。临时截图保存在 `/tmp/w1_original_site_capture/`，不提交到仓库。

复刻范围包括深绿球场背景、大号 WHO WINS 标题、编号区块、今日焦点赛程卡、对阵预测台、霓虹绿色边框、黄色行动按钮和结果卡片层级。底层仍完全使用 W1：watcher v2、W1_PLAY_GUARD_V1、match cards、ledger、odds_movement、supporting_factors / counter_factors 与 dashboard_data.json。

交互结构也按原站复刻：今日焦点卡可点击并带入主客队，下拉框可选择 48 支球队，阶段按钮可切换，点击“开始预测”后动态展开结果区。W1 版不调用原站 `/api/predict`，而是用本地 W1 数据生成等待状态、参考倾向、参考比分、理由和风险提示。

## 第一屏信息

- 当前状态：24 场等待关键数据
- 第一场：墨西哥 vs 南非
- 参考倾向：墨西哥不败
- 参考比分：2-0 / 2-1
- 当前动作：等待正式首发，不下最终结论
- 正式判断：6月12日 02:00 / 02:30 CST
- 说明：参考比分只作为外部参考，不绕过 W1 风控

## 页面模块

- 今日焦点：按原站横向赛程卡展示首轮重点比赛
- 对阵预测台：按原站左右主客队 + 中间 VS + 阶段按钮展示
- W1 赛前卡：比赛、倾向、参考比分、理由、风险提示、关键缺口、当前动作、W1 风控状态
- 神算战绩：按原站结构保留战绩/复盘区域，等待赛后由 W1 ledger 做验证
- 页脚声明：明确不构成投注建议、下注建议、资金建议或收益承诺

## 边界

页面可以展示参考倾向和参考比分，但它们只是外部参考信号，不是 W1 正式结论。W1_PLAY 仍必须通过 W1_PLAY_GUARD_V1；只要 confirmed_lineup 等关键数据缺失，页面必须保持等待数据。

页面不提供投注、下注、资金或收益建议，也不接入接口密钥教程、聊天群自动化或付费社群。

## 校验

```bash
python3 scripts/check_w1_visual_dashboard.py
```

预期输出：

```text
W1 visual dashboard self-test PASS
```
