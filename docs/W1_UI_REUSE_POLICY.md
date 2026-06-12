# W1 UI Reuse Policy

## 复用目标

W1 允许借鉴公开项目 `worldcup2026-prediction-skill` 的中文 UI 与交互风格，包括普通人可读的表达、分组清晰的页面组织、比赛卡片、风险提醒、当前动作提示、世界杯分组展示、晋级规则说明和教程式解释口吻。

执行口径：只复用中文 UI、卡片组织和解释风格，不复用其底层预测方法。

## 禁止复用

W1 不复用该项目的 prompt 预测逻辑，不把胜平负概率作为 W1 结论，不把外部参考比分作为正式结论，不把外部口径作为正式置信度，不接入接口密钥教程、聊天群自动化、付费社群，也不提供投注、下注、资金或收益建议。

## W1 保留项

页面底层必须继续使用 W1 的 watcher v2、W1_PLAY_GUARD_V1、match cards、ledger、odds_movement、supporting_factors / counter_factors 和 dashboard_data.json。任何参考倾向或参考比分都不能绕过 W1_PLAY_GUARD_V1。

## License Note

参考项目使用 MIT License。本仓库只做 UI 风格借鉴和独立实现；如未来复制其代码或大段文本，必须保留其许可证与版权声明。
