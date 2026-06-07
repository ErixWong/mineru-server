# Task 005: 面向 LLM 调用者的 MCP 产品化改进

## 目标

从一个 LLM 驱动应用调用当前 MCP 的视角，跟踪当前产品仍需补齐的产品化能力，并为后续改进建立任务边界、优先级和实施清单。

本任务的前提修正如下：

- 不假设 LLM 会“胡乱组合工具”
- 实际使用中，客户端会先定义状态机、每个状态调用哪个工具、对应提示词怎么写
- 因此本任务重点不是做一个超级组合接口，而是让“状态明确、默认主结果明确、其他产物可发现”

## 背景

当前项目已经具备一条可用的 OCR MCP 主链路：

- 可发现 MCP tools
- 可提交文件并创建任务
- 可轮询任务状态
- 可获取 Markdown 结果
- 可获取图片与图文关联信息

从“能不能用”的角度看，这已经是一个可用的 OCR MCP。

但从“一个通用 LLM 应用能否稳定集成并拿到图文混编结果”的角度看，仍然存在产品层契约不够完整的问题。

## 本轮分析结论

当前系统已经足够支撑：

- 文档 OCR
- Markdown 主结果返回
- 图片独立获取
- 图文混编的基础还原

但围绕“如何拿图文混编结果”仍有几个需要补齐的点：

1. `get_task_result` 默认返回图文混编主结果是对的，但其他结果产物还缺少统一清单
2. 调用方目前可以拿到图片清单与图片内容，但还缺少一个明确的“结果发现”层
3. 其他格式结果没有统一入口按类型获取
4. 图片作为独立产物的职责是清楚的，但需要把这一契约进一步制度化

## 建议状态机

从客户端设计角度，建议固定为三个主要状态：

1. `processing`
   - 使用：`get_task_status`
   - 目标：检查任务是否完成

2. `result_ready`
   - 使用：`get_task_result`
   - 目标：获取图文混编的 Markdown 主结果

3. `image_resolve`
   - 使用：`get_task_images`
   - 目标：根据图片清单、图片引用位置和图片内容补齐图文混编结果

这个状态机的关键原则是：

- 每个状态只调用一种工具目标
- 不在一个工具里混合多种场景
- 客户端负责状态编排，MCP 负责提供清晰产物

## 优先级建议

### 第一优先级

1. 明确 `get_task_result` 的默认语义
   - 默认返回图文混编 Markdown 主结果
   - 不再额外塞入其他中间结果或图片内容

2. 增加统一结果清单
   - 新增：`list_task_results`
   - 列出当前任务的可用产物：
     - `markdown`
     - `middle_json`
     - `model_json`
     - `content_list`
     - `content_list_v2`
     - `images`

3. 支持 `get_task_result` 按逻辑格式获取特定结果
   - 例如：`format=markdown`
   - 例如：`format=content_list`
   - 例如：`format=middle_json`
   - 不建议主契约直接按原始文件名暴露

4. 继续保持图片独立获取
   - `get_task_images` 继续承担图片清单和图片内容职责
   - 文本结果和图片结果不混成一个超大接口

### 当前实现进展

当前已开始落地并验证：

1. `get_task_result` 默认继续返回图文混编 Markdown
2. `get_task_result(format=...)` 已支持按逻辑格式获取：
   - `markdown`
   - `middle_json`
   - `model_json`
   - `content_list`
   - `content_list_v2`
3. `list_task_results` 已新增，用于列出任务可用产物
4. `get_task_images` 继续保持图片独立获取

### 第二优先级

1. 增加适合 agent 的结果摘要字段
   - `page_count`
   - `image_count`
   - `has_tables`
   - `has_equations`
   - `language`
   - `warnings`

2. 增强错误对象
   - `retryable`
   - `suggested_action`
   - `fallback_backend`
   - `install_hint`

3. 进一步细化结果契约的主次层级

### 暂不优先

1. 高保真页面复刻能力
2. 页级 / bbox 级坐标能力
3. 直接把 `content_list_v2` 升为稳定公开主契约
4. 新增 bundle 工具
5. 新增 block 化图文混编对象

## 当前推荐的工具安排

如果现在就按最稳的客户端方式设计，推荐这样调用：

1. `create_task_from_file`
   - 创建任务

2. `get_task_status`
   - 轮询进度

3. `get_task_result`
   - 获取图文混编 Markdown 主结果

4. `get_task_images`
   - 获取图片清单、图片 URL / base64、图片引用位置

客户端应将：

- Markdown 视为“图文混编主骨架”
- 图片视为“补全层”
- `items[].references[]` 视为“图片和正文的索引层”

## 对图片提供方式的结论

当前项目已经具备两种图片提供方式：

1. base64
   - 适合 MCP / agent 内部消费

2. 静态 URL
   - 适合前端、浏览器、文档查看器

本任务后续需要做的不是重新发明图片接口，而是让调用方更容易知道：

- 任务有哪些结果
- 哪些结果是主结果
- 图片应该通过独立接口获取

## 为什么需要单独建任务

这不是单纯的代码重构问题，而是“产品化接口如何让调用方稳定拿到图文混编结果”的一组改进。

它和：

- 上游 MinerU 对齐
- 依赖策略
- 输出契约

是相关但不同层级的问题，因此单独立任务更清晰。

## 预期输出

1. 明确每个改进项的产品目标
2. 明确每个改进项是否需要新增 MCP tool / REST 字段 / artifact 清单
3. 给出实现优先级
4. 逐步把“可用的 OCR MCP”演进成“结果契约清晰、适合客户端状态机消费的 OCR MCP”

## 建议分支

- `feature/005-llm-mcp-product-improvements`

## 状态

- [x] 任务已创建
- [ ] 形成正式实施方案
- [ ] 开始实现
- [ ] 审查
- [ ] 归档
