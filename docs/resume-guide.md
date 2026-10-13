# AgentDesk 简历描述与面试说明

本指南以已实现代码和现有验证为依据。建议将 AgentDesk 列为个人项目，并能解释
关键实现、测试与取舍；使用了协作开发辅助时，不把未亲自理解的部分包装成独立掌握。

- 项目演示：[5～10 分钟路线](project-showcase.md)
- 技术说明：[架构与设计取舍](architecture-overview.md)
- 仓库：https://github.com/Stwie907/agentdesk

## 中文简历版本

**AgentDesk｜本地 Agent 执行与记忆工作台**

技术栈：Python、FastAPI、SQLAlchemy、SQLite、React、TypeScript、Vite、Ollama、
MCP、Docker Compose、GitHub Actions。

- 实现任务执行与检查工作台，统一展示执行状态、结构化 Trace、版本化 Snapshot
  和基于保存计划的 Replay，并处理工具权限、失败元数据及重试。
- 实现按 Agent/用户范围组织的记忆与会话能力，支持关键词/语义检索、SQLite
  向量缓存和执行时记忆捕获，便于核对历史执行实际使用的上下文。
- 提供 JSON/Markdown 执行报告，将步骤证据与已加载的历史记忆依据一起导出；
  区分读取状态并防止切换执行后的迟到响应混入当前报告。
- 使用 Docker Compose、确定性 Mock、自动化测试与 GitHub Actions 验证执行、
  MCP 工具、导出和持久化流程，无需付费 LLM API 即可运行演示。

版面有限时保留前三条；不要堆砌全部 Issue 编号。项目链接放在简历可点击的位置。

## English resume version

**AgentDesk — Local Agent Execution and Memory Workbench**

Stack: Python, FastAPI, SQLAlchemy, SQLite, React, TypeScript, Vite, Ollama,
MCP, Docker Compose, GitHub Actions.

- Built an execution workbench with structured traces, versioned snapshots and
  stored-plan replay, including tool permissions and persisted failure metadata.
- Added scoped Agent/user memory, conversation history, keyword and semantic
  retrieval, SQLite vector caching and captured execution memory context.
- Implemented JSON/Markdown execution reports with explicitly loaded historical
  memory evidence, read-state handling and protection against stale responses.
- Used deterministic Mock demonstrations, automated tests and Docker/CI checks
  to validate runtime behavior and persistence without paid LLM APIs.

## 30 秒介绍

“AgentDesk 是我参与实现的本地 Agent 工作台，使用 FastAPI、React 和 SQLite，
模型可以选择本地 Ollama，也能用 Mock 运行演示。我关注的不只是最后一句回复，
而是把执行计划、工具步骤、失败、Snapshot、Replay 和当时使用的记忆保存下来。
工作台可以查看这些记录，也能导出报告，方便排错和演示。”

根据实际参与程度，将“参与实现”改成能准确描述自己的措辞。

## 可以展示的证据

| 论点 | 展示位置/证据 | 表述边界 |
| --- | --- | --- |
| 可以检查执行过程 | Inspector、Trace、Snapshot；相关 runtime/API 测试 | 不是任意任务都执行成功 |
| 可以重放保存计划 | Replay API、执行关联和权限测试 | 会重新执行工具，不保证外部状态相同 |
| 记忆范围与检索可核对 | Memory retrieval 捕获、范围/相似度/上下文校验 | Mock 分数是固定夹具，不是实际模型质量 |
| 切换与导出保留草稿 | frontend/tests/ExecutionReportMemoryEvidence.test.tsx 及人工验收 | 浏览器保留需按草稿开关设置 |
| 数据跨服务重新创建保留 | 保留数据卷的验收报告、检查点和两轮导出对比 | 不等于已有灾备或数据库恢复能力 |
| 具备自动化验证 | GitHub Actions、backend/tests/、frontend/tests/、evaluation/ | 查看对应提交 Checks，不猜运行结果 |

可引用的历史验证：Issue #163 本地前端 903 项测试、47 个文件通过，TypeScript
和构建通过；该数字是 2026-10-12 的实现验证。提交后 CI 的结果需以实际 Checks
为准。简历更适合解释测试覆盖了什么，而不是只放一个很大的数量。

八个固定 Runtime 评估用例的通过率，只能描述对应数据集和实测版本。
没有统一测量前，不写“提升 X%”“毫秒响应”“高并发”“零幻觉”或“生产级”。

## 常见面试问题

| 问题 | 回答要点 |
| --- | --- |
| 为什么提供 Mock？ | 脱离模型和 API Key 验证工具、Trace、Snapshot 与 Replay；真实模型效果另行评估 |
| Replay 与 Retry 有什么不同？ | Replay 从保存计划创建新的关联执行；Retry 重置同一失败记录后重新尝试 |
| 如何避免前端显示错执行？ | 请求代次、作用域校验及卸载/切换后的迟到结果保护；导出再次校验证据范围 |
| 为什么保存记忆捕获？ | 当前记忆会变化；历史执行需要知道当时选中了哪些记忆及发送了什么上下文 |
| 为什么 SQLite？ | 当前目标是容易运行的本地项目；没有假装已解决分布式部署与高并发 |
| MCP 工具是否连接真实业务？ | 订单/物流是明确标注的夹具；工单写本地独立存储，保留真实 stdio 协议调用 |
| 项目下一步是什么？ | 完整演练和版本发布收尾；公网部署、文档知识库 RAG、分布式任务队列需独立规划 |

## 提交或分享前

检查报告中的聊天文本、记忆内容和工具结果；不要直接把私人工作台数据库或捕获
文件提交到公开仓库。对外示例优先使用 B 路线的独立 Mock 数据。

说明可运行的命令、实际测试版本及已知限制。版本标签与正式发布尚未创建时，
使用“本地展示版本”或“v1.0 候选”，不把它写成已经正式发布。
