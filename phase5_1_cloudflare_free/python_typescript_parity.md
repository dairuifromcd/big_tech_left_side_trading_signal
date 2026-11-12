# 跨语言等效范围

Python reference HEAD为50e77ab5c2e29387efa2ca9772fdee979eccbbee，源码未修改。
Python完整测试271/271通过，0跳过，断网audit记录0次网络尝试。

Golden由cloudflare/scripts/golden.py调用原Python模块生成，TS逐字段递归对照；不从TS生成预期结果。现有15类修订场景×股票/指数=30组全部覆盖；还包括9股真实存档转移、12标的初始baseline、AVGO累计锚点、已pending/rejected、缺日、边界、多档、恢复/再入、自然高点滚出、短历史和幂等性，共76个核心fixture。Yahoo输入有效/无效验证32个，验证pass/block决定与原Python核对。

比较包括完整observations.evaluate模型，而非只对指标或change_event。离散结果、key集合、日期、WATCH、事件类型/状态、阈值、确认资格、pending保留和ID必须完全一致。浮点容差absolute=1e-12、relative=1e-12；实测11145个数值比较最大绝对差0。fsum使用非重叠partials及末尾半舍入修正，Wilder顺序不变；高点精确相等取最新日。标准化float64价格map和语义ID哈希另逐例精确比较。

新增价格map hash测试曾发现合成输入含Python int而非collector规范化float64，85与85.0 JSON不同。修正是明确把额外hash contract定义为collector的float64规范化，Python原指标/事件预期输出及输入仍保持不变。任意混合int/float证据没有被宣称哈希等效。

原有7条pending从正式账本只读复制，在独立SQL中验证记录完整一致；正式文件另做SHA256核对。测试不确认、不拒绝、不删除它们。

尚未完整等效的内容：Python文件v1/v2迁移、完整stock/index状态导入导出、一般Python原始证据JSON逐字节序列化、完整人工决定/rollback/reopen工作流、受信归档逐日应用runner、生产诊断字段全量映射。这些不因核心76组通过而变成PASS。当前只能报告核心规则等效PASS，整体移植PARTIAL。

详细逐例结果见parity_results.json；Python和TS测试数量分别记录在test_results.json。没有删除、跳过或修改既有Python测试。
