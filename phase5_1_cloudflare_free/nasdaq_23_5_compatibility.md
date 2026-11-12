# Nasdaq 23/5与收盘日线

保留Brisbane周二至周六10:00，UTC Cron候选`0 0 * * TUE-SAT`。Brisbane全年UTC+10；这对应纽约前一天19:00 EST或20:00 EDT，距离16:00常规收盘3或4小时。只设计，配置中未创建Cron。

Nasdaq官方宣布计划2026-12-06周日21:00 ET开始23/5，夜间段21:00–04:00，20:00–21:00维护；核心09:30–16:00及开/收盘cross保留。夜间21:00至午夜交易归次日trade date。其余交易所、Nasdaq其他市场及指数不能据此一概更换日历。[Nasdaq hub](https://www.nasdaq.com/23-5-trading)、[Nasdaq explains](https://www.nasdaq.com/newsroom/nasdaq-explains-what-is-23-5-trading)。

保持原规则：常规交易日、16:00 ET或已公布提前收盘13:00 ET，2024–2028明确日历，America/New_York DST。calendar-data.json由原Python逐日生成UTC开/收盘时刻；TS对每个交易日做收盘前后边界检查，并验证3月/11月夏令时切换。不是将Nasdaq夜盘trade date静默塞进现有自然日期规则。

Yahoo官方将Adj Close定义为经拆股与分红调整的收盘价，但未找到对23/5上线后Chart日线发布时间、日期标签及Close/Adj Close保持常规收盘口径的明确保证。[Yahoo adjusted close](https://in.help.yahoo.com/kb/adjusted-close-sln28256.html)。这些项目均NOT_VERIFIED；本阶段没有向Chart端点发出请求。不能从Nasdaq保留Closing Cross推导出Yahoo供应口径必然不变。

上线前后需独立授权，在固定时刻保存9股/3指数原始日线，对照Yahoo日线标签、常规收盘/close、调整因子、市场元数据及权威exchange/index基准。确认regular session定义、指数发布时间和symbol identity后再放行；不能把指数close单独变化用于改变Adj Close指标。

遇到夜间timestamp或新trade-date映射，当前验证器会拒绝常规时段外时间戳；若供应口径可能变化，应增加来源策略版本，阻断受影响事件自动确认，保留原证据并报告。不得自动推迟至23小时交易结束，也不得自动改价格基础。

节假日与提前收盘仍按原已核日历；突发停市无法预测，需显式更新。2028-07-01开始到期预警，2028-12-31之后纽约日期直接拒绝；下一份日历须查交易所官方发布、加入突发停市并重新做跨语言验收后授权切换。
