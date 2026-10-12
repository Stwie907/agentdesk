# AgentDesk 项目演示指南

适用：当前 AgentDesk 本地展示版本。本文是演示路线，不是已经完成的正式发布公告。

AgentDesk 把任务执行、工具调用、历史记录和记忆依据放进一个可检查的本地工作台。
重点展示“执行过程如何留下证据”，而不仅是聊天框的最终回复。

- [架构和设计取舍](architecture-overview.md)
- [简历描述与面试说明](resume-guide.md)
- [Docker 配置详细说明](docker-compose-demo.md)
- [执行报告格式](execution-reports.md)
- [历史记忆依据导出](execution-report-memory-evidence.md)

## 先选演示路线

| 路线 | 适合谁 | 数据影响 |
| --- | --- | --- |
| A：已有记录的只读展示 | 当前保留 Agent、会话和验收检查点的用户 | 查看、手动读取历史依据和导出文件；不提交任务或改数据库记录 |
| B：独立 Mock 演示 | 新评审者、没有 Ollama 的同学、需要现场运行新任务的面试 | 独立 Compose 项目会初始化演示 Agent；任务、Replay、评估会写入它自己的数据库 |

当前已有数据的用户优先使用 A。不要在原有项目上直接运行 Mock 初始化、评估或
“清理数据库”来准备截图。B 使用单独的项目名和数据卷，但仍占用相同的本机端口；
端口已被当前工作台占用时，先完成 A，或在另一台环境演示 B，不强行关闭正在用的服务。

## A：5～10 分钟只读展示

前提：现有工作台已经运行。只查看容器状态：

```bash
docker compose -f docker-compose.yml ps
```

打开 http://localhost:5173 。以下导航名称与当前侧栏一致。

| 建议用时 | 点击位置 | 展示重点 |
| --- | --- | --- |
| 1 分钟 | 选择 Agent / 任务 → 选择已有 Agent | Agent 有自己的模型和工具权限；本轮不点击 Submit task |
| 1 分钟 | 运行配置 → Show runtime configuration | 当前 Provider、规划模型、记忆模式和向量缓存设置 |
| 2 分钟 | 执行历史 → Execution 编号；侧栏执行详情 | 执行输入、输出、状态、Trace、Snapshot 和 Replay History |
| 2 分钟 | 执行详情 → Show memory retrieval | 这次历史执行保存的记忆内容、范围、分数和上下文 |
| 1～2 分钟 | 执行报告区域 → Export JSON / Export Markdown | 可带走的完整执行证据和 schema version 2 |
| 1 分钟 | 会话聊天 → 选已有会话 | 消息历史、搜索、上下文查看，以及未发送草稿 |

### 1. 当前配置与历史记录

在 **选择 Agent / 任务** 中选择一个已有 Agent。展开 **运行配置**，说明这是当前
设置。可选点击 **检查本地 Ollama 模型**：它读取本地模型列表，不做推理或向量生成。
“已安装”是安装元数据，并不代表已经证明模型推理能力或输出质量。

随后点击 **执行历史** 中已有的 **Execution <ID>** 按钮，再点侧栏 **执行详情**。
也可在 **Execution ID** 输入已有编号，再点击 **Load Execution**。

当前保留验收数据的工作台已核实执行 **116**、Agent **1**。它的输入是
`Keep it brief.`，输出是保存的 Mock 回复。这个编号是已有数据的例子，不是新安装的
固定默认编号。新用户应选择自己的已有记录。

### 2. 执行证据

展示 **Execution Summary** 的状态、输入/输出、失败信息和重放来源。
向下展示 **Runtime V4 Trace**：解释 plan_started、step_started、step_completed、
plan_completed；失败执行则查看实际保存的失败事件，不假设所有记录都有相同事件。

展示 **Snapshot** 中的版本和保存的计划。没有 Snapshot 的历史记录可以正常显示。
**Replay History** 是已有重放记录的只读列表。只读路线不点击 Replay execution、
Retry execution 或 Cancel execution。

> Replay execution 会创建新执行并重新调用工具，不是只打开旧输出；写工具可能再次
> 执行写操作。要现场演示 Replay，请使用 B 的独立 Mock 项目和 Calculator。

### 3. 历史记忆依据

在 **Memory retrieval** 中点击 **Show memory retrieval**。
它读取该执行保存的捕获记录，不重新计算当前记忆的相似度。

执行 116 的已核实例子包含 Agent 记忆 13 和用户记忆 3，相似度均为 0.96；
其历史 Provider 为 Mock，模型为 mock-fixtures-v1，属于固定测试向量。
当前配置显示 Ollama，不会改写这条 2026-10-09 的历史依据，也不能把它作为真实
Ollama 检索质量的测量结果。

展示 Requested mode、Used mode、检索 Query、Captured at，以及两个记忆范围。
展开 **Memory context sent to Runtime** 查看原始上下文。如果出现 No memory retrieval
evidence was recorded，说明该执行没有保存依据，不能解释为“检索过但没有命中”。
有保存依据但零条匹配时，记录仍可用，context 可为空字符串。

### 4. 导出报告

回到 **Export execution report** 区域，点击 **Export JSON** 和 **Export Markdown**。
会话聊天区也有同名备份按钮；演示时请使用执行摘要下面的报告按钮。

新报告的 `schema_version` 为 2。四个原有部分为 execution、trace、snapshot、replays；
新增 memory_retrieval。有意先不点击 Show memory retrieval 导出一次，可以展示
not_loaded；读取成功后再导出会显示 loaded 或 unavailable。读取失败为 failed，
等待期间导出为 loading。导出本身不发起额外请求。

文件包含真实保存的输入、工具结果和记忆内容，公开展示前检查内容。报告是多次
读取到的显示状态，不是原子数据库备份，也不是可导入的会话备份。

### 5. 会话与草稿

点击 **会话聊天**，选择已有会话。现有验收例子为 Agent 1、会话 16；如果列表中
找不到，将 **Conversations per page** 改为 20，再找实际编号。

使用 **填写标题草稿**、**填写聊天草稿** 定位输入框，可输入测试文字但不 Rename
或 Send。回到执行详情读取或导出，再回到聊天，说明草稿和会话选择仍保留。
如需浏览器刷新后保留，先勾选 **Keep this Agent's drafts on this browser**。

搜索消息、查看周围上下文都使用现有读取入口。修改/删除记忆、重命名、导入、发送
聊天属于写操作，不纳入只读路线。

## B：独立 Mock 演示

在未占用 localhost:5173 和 localhost:8000 的独立环境或新克隆目录中执行。
Git Bash、Docker Desktop 的 Linux containers 和 Docker Compose v2 已可用。
所有命令从仓库根目录执行。首次构建需要下载基础镜像和依赖；Mock 运行不需要
LLM API Key 或安装 Ollama。

每条命令都显式指定 `agentdesk-showcase` 项目，使用单独的数据卷。不要省略项目名
后在已有数据上运行下面的初始化和评估。

```bash
COMPOSE_PROJECT_NAME=agentdesk-showcase MEMORY_RETRIEVAL_MODE=keyword sh deployment/start-demo.sh
```

该脚本创建或复用演示 Agent 并启动服务。打开 http://localhost:5173 ：

1. **选择 Agent / 任务** 中选择 **Demo Agent**。
2. **Task** 输入 `Calculate 40 + 2`，点击 **Submit task**。这会创建执行记录。
3. 在执行详情确认输出 42、Calculator 工具事件和 Snapshot。
4. 点击 **Replay execution**。它使用保存的计划创建新执行，再调用 Calculator。
   查看新的执行 ID、Replay of execution 和原记录的 Replay History。
5. 可提交 `Hello AgentDesk`，说明带 [MOCK] 的回复是固定演示回复，未调用语言模型。
6. 若展示 MCP，选择 MCP Order Agent，提交 `Get order DEMO-1001`；或选择
   MCP Logistics Agent，提交 `Track order DEMO-TRACK-1001`。查询数据标注 demo_fixture，
   不代表连接了真实订单或快递平台。

MCP Ticket Agent 的 create_ticket 会写入本地工单库；如非演示重点，可跳过。
新 Mock 数据没有已有工作台的历史记忆依据时，Show memory retrieval 显示实际状态。
不为展示强行声称已有记忆；完整记忆流程见 [Docker 指南](docker-compose-demo.md)。

### 固定数据集评估（演示之外可选）

```bash
COMPOSE_PROJECT_NAME=agentdesk-showcase sh deployment/evaluate-demo.sh
```

评估器运行八个固定用例，检查 Calculator、Mock 回复、工具选择、Trace、Snapshot
和 Replay。成功运行创建八条执行，并覆盖本地 evaluation/reports/report.json 与
report.md。此前报告需要保留时，先复制到另外位置。

这些指标反映该次固定数据集的运行结果，不是开放问题回答质量、RAG 质量或模型
幻觉评估。延迟取自本次实测，不能在没有相同测试条件的情况下宣称性能提升。

结束独立演示后，停止该项目并保留其卷：

```bash
docker compose -p agentdesk-showcase -f docker-compose.yml -f docker-compose.mock.yml down
```

恢复/启动自己原有的 Ollama 工作台时，回到原仓库和原 Compose 项目配置，按
[Docker 指南](docker-compose-demo.md) 使用已有参数。不要把独立 Mock 项目的
初始化命令或数据库清理命令用于原工作台。

## 动作与数据影响速查

| 动作 | 是否写入数据库/创建执行 |
| --- | --- |
| 查看配置、模型列表、已有执行、Trace、Snapshot、已有 Replay 列表 | 不写记录 |
| Show/Refresh memory retrieval | 只读保存的历史捕获，不做新检索 |
| 导出执行报告 | 浏览器下载文件，不额外请求、不写数据库 |
| 提交任务、发送聊天、Replay execution | 创建执行；工具或聊天可能写入其他记录 |
| Retry execution | 重置同一失败执行并开始新的尝试 |
| Cancel execution | 修改 pending 执行状态；不能强制终止已 running 的工具 |
| Rename/Delete conversation、导入、编辑/删除记忆 | 写操作 |
| start-demo.sh | 初始化或复用演示 Agent |
| evaluate-demo.sh | 写入评估执行，覆盖本地评估报告 |

## 如何收尾这个展示版本

当前功能可以用于本地项目展示。下一轮需要完成一次完整演练、核对发布分支和 CI，
再通过明确的发布流程创建版本标签与发布说明。本文不表示 v1.0 已经发布。
