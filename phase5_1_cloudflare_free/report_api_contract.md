# Report API v1

本地已实现6类GET端点；无Dashboard页面。HTTP入口要求Bearer，缺少配置或凭据不匹配返回401；写方法405。只有namespace内部测试RPC具备写能力，并要求未在cf配置中启用的LOCAL_TESTING binding。正式配置无该binding。

统一envelope：schema_version=report-v1、mode=DRY_RUN_MOCK_OFFLINE、data_version、updated_at、data。DTO类型定义见cloudflare/src/report-dto.ts。输出只来自已提交state/history/event，不暴露history_prices、身份快照、账户ID、raw或evidence_versions内容。

| 路径 | 返回 |
|---|---|
| /api/overview | 固定12标的；未初始化标的明确NO_COMMITTED_BASELINE |
| /api/assets/:symbol | 当前提交的指标/质量/WATCH/confirmed/pending，symbol需URL编码 |
| /api/assets/:symbol/history | 成功提交的Report DTO历史；不是伪造的每天PIT快照 |
| /api/events | 市场事件、修订事实分event_type，状态、阈值、证据版本数 |
| /api/runs/latest | 最近运行和每标的claim状态、错误 |
| /api/health | 最近运行、pending数、备份数量、calendar到期；云资源用量NOT_VERIFIED |

history/events支持from/to、limit=1..200、cursor非负整数；日期受2024–2028保护，倒置范围拒绝，默认limit50。events另支持symbol/status。当前采用有上界的offset及内存投影，未来事件增长必须迁移到索引+游标SQL分页；不能视为无限扩展完成。

当前WATCH档位独立于确认事件。^SOX首次baseline可显示WATCH_30而事件列表为空；PENDING候选不得显示为已确认下跌。日回撤变化与累计锚点分别输出。系统运行COMPLETE仅表示所有task已终止，必须结合每task状态看成功/失败；不能据此显示全绿。

历史图表未来需要两条显式来源：已提交PIT报告历史，以及最新验证快照推导的历史指标分析。后者DTO需bar_date、capture_date、origin=LATEST_VALIDATED_SNAPSHOT_ANALYSIS、point_in_time_capture=false。本阶段定义了类型但未实现完整历史分析series端点/预计算表。不能把当前history API的单个baseline称为完整两年图表数据。

Phase5.2建议React+TS，以Static Assets托管；API继续私有，独立version，不把Python状态JSON直接展示。Overview/EventTimeline/SystemHealth基础DTO已就绪；完整HistoricalCharts查询、数据库索引和真实Access/JWT验证仍需实现/实测。

测试对API读取前后全部持久表取快照，无写入；另验证401/405/分页/非法symbol/日期范围及输出不含内部证据。
