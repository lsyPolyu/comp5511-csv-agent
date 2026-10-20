# COMP5511 技术规划与阶段任务

规划日期：2026-10-15；恢复验证及人工验收交接更新：2026-10-16（Asia/Shanghai）。依据：[HANDOFF](HANDOFF.md)、[intent](intent/project-intent.md)、[spec](spec.md)。用户已同意现有规格及D01–D08作为工程默认推进；保留已确定需求，不改变Proposal核心研究约束。

本文件是唯一计划及阶段任务索引，不另建TASKS、todo或progress副本。**P01/P02已done；P03当前in_progress：旧入口已重启消除，实际协议继续验证发现语言切换后客户端选项字符串未同步，正在修复验证；P04–P16仍todo。**本轮止于P03修复交接，不进入P04；阶段验收不表示全部33个场景通过，也不等于真实API联调或正式实验。

## 1 目标与最早可运行结果

先完成单CSV的本地可运行路径，再接入离线Agent、proposed修复、少量真实API及独立评测。保留8次工具/2次修复、40英文题×两版本×3次=240自然运行，以及10故障×两版本×3次=60独立故障运行计划。

**P01结束即可首次上传CSV、执行真实本地`inspect_dataset`并在英文Streamlit页面查看预览、行数/列类型/缺失摘要；不需要Key，不调用模型。**P02结束可在同一页面运行真实过滤/分组统计，手算核对0.75/0.25；P03加入图表。P05才是FakeProvider驱动的完整离线Agent，P09才首次安排少量真实DeepSeek联调与测费，P14才可能进入获预算确认的正式实验。

开发沟通/排错/教学中文，技术标识符英文；界面默认English，支持session内切换中文供操作与验收，新图默认标题/轴标签随界面语言，用户自填内容保留。课程展示、Agent生成答案、正式问题/实验配置及报告/slides/口头演讲保持英文。原始列名/值/alias/ID/schema/错误码不翻译，不增加Agent中文问答或双语实验。

## 2 简单组件与依赖方向

采用普通Python模块、Pydantic参数契约、Pandas计算、Matplotlib绘图、HTTPX适配及Streamlit UI；不引入Agent框架、独立Web后端、数据库、消息队列或向量库。

| 计划位置 | 职责与边界 |
| --- | --- |
| `app.py`、`comp5511/state.py` | 英文UI与session生命周期；只提交一次运行、显示结果/日志、取消；不复制统计逻辑 |
| `comp5511/config.py`、`contracts.py` | 环境变量与共同资源配置；工具schema、统一结果/错误/状态，两个版本共用 |
| `comp5511/datasets.py`、`analysis.py`、`plotting.py` | CSV/inspect、聚合、真实结果绘图；只执行预定义行为；不导入模型适配或评分器 |
| `comp5511/dispatch.py` | 三工具白名单、JSON/schema、共同执行保护、tool_call_id配对；不含proposed专用候选反馈 |
| `comp5511/validation.py` | proposed独立dataset-aware预检/限定反馈；不得改变共享工具统计语义 |
| `comp5511/controller.py` | 同一Controller按mode控制baseline首错停止/proposed修复；维护T/R、pending_error和终止状态 |
| `comp5511/providers.py`、`deepseek.py` | 小型ModelProvider契约、FakeProvider、直接HTTPX的DeepSeek适配；归一化content/tool_calls/usage，适配器不执行分析工具 |
| `comp5511/runtime.py`、`tool_worker.py` | 统一deadline、取消令牌、受监督工具执行和迟到结果拒收；不决定分析语义 |
| `comp5511/runlog.py` | 脱敏JSONL事件、运行manifest和产物引用；不保存密钥或隐藏思维过程 |
| `evaluation/` | 任务/数据manifest、独立reference、scorer、fault injection/comparability、runner、metrics；reference/scorer不导入Agent工具或validator |
| `tests/`、`data/`、`outputs/` | 开发/契约/集成测试与独立数据、逐次日志/图表/实验输出；开发fixture与正式评测集分开 |

依赖方向：config/contracts → data/tools → dispatch → Controller ← provider；runtime监督Controller及工具；UI只经共同入口读写自己的session；日志接收可观察事件。独立评分从冻结数据/任务/实际输出读取证据，不把答案回传Controller。

首次出现模块时只创建该阶段所需文件，后续增量演进，不先铺空模块。下述文件数按每个小任务约3–5个源码/配置/测试文件估算；数据/日志等产物及plan/HANDOFF状态维护另计。若超过一个专注会话或功能边界变大，先拆分该任务并在本文件更新依赖。

### 关键实现决定

- `session_id/dataset_id/run_id/generation`由服务端维护，原表不可变，结果只在当前上下文可引用。可选缓存仅缓存不可变内容，不全局共享用户状态。
- Controller运行与Streamlit重绘分离：session保留运行句柄/取消令牌，后台协调不调用`st.*`；UI刷新只消费事件。每次发布检查active及上下文令牌，旧响应不重新进入新session。
- HTTP用`AsyncClient`和外层整体请求超时，显式网络重试；不引入额外SDK隐藏重试。配置/工具schema/prompt等两版本共同，差异只在spec R09。
- Windows受控工具使用`multiprocessing`的`spawn`子进程；函数可导入、参数可序列化，worker不导入UI、不持有Key、不启动孙进程。父进程监督deadline/取消，终止并回收超时worker；产物先写run专用临时区，只有父进程校验通过才注册/发布。管道/文件句柄清理单独记录；不能把线程等待超时当作实际停止工具。
- 相同进程/序列化开销对两版本一致并计入实际延迟。工具超时监督在P04先验证，不等付费联调才发现不能取消。
- `plot_result`显式ISO日期和number/percent格式参数见spec R07；deadline覆盖请求/退避/工具/收尾见R12；故障`both_triggered`与`comparable`分开见R15/R17。选择理由分别是避免隐式猜测、避免绕过总预算、避免不同故障被错误归因。

## 3 Windows环境与依赖方案

### 3.1 实际核对与选择

规划轮核对：Windows 11 x64（10.0.26100）、PowerShell 5.1.26100.4061；`python`默认指向`D:\Python39\python.exe` 3.9.13。`py -0p`还登记了`F:\JavaAiNew\software\anaconda3\python.exe`，实际执行确认 **Python 3.12.4 x64**，具备venv/pip。2026-10-16恢复时确认项目`.venv\Scripts\python.exe`实际为3.12.4、`include-system-site-packages=false`；继续使用现有环境，不在全局3.9或Conda base里安装项目依赖。

项目外临时venv的历史验证和版本清单见附录A。2026-10-16磁盘恢复证据表明项目`.venv`已创建，但安装在下载阶段中断，已安装包仅pip24.0；本轮保留环境并补齐全部53项锁定依赖，版本逐项匹配、7个关键模块导入及`pip check`通过。硬件内存/峰值和20 MiB/100,000行资源极限、30/300秒限制仍须P04及真实联调实测。

直接依赖保持最少：streamlit、pandas、matplotlib、pydantic、httpx、python-dotenv；pytest用于开发。三个依赖文件均已保存：`requirements-lock.txt`与附录A的规范化SHA-256一致，`requirements.txt`为运行直接依赖，`requirements-dev.txt`包含pytest。锁定同一Windows/Python环境；跨平台需另建兼容环境并复核，不能直接套用未经验证的wheel组合。

现有3.12.4只是本机已测的引导候选，不是对最新补丁状态的承诺；如以后更换解释器补丁或依赖，先重建隔离环境并重验，记录版本，正式冻结后不静默升级。数据dtype/缺失语义按spec明确实现，不依赖Pandas默认推断。

### 3.2 P01及后续阶段的命令约定

以下是项目现有文件的运行命令；恢复轮已实际执行`pip check`、两组pytest测试及服务启动/HTTP检查，本次交接只复核端口和HTTP，未重跑测试，证据见P01。全部使用显式`.venv`解释器，无需更改PowerShell执行策略。环境完整时跳过安装，保留现有`.venv`；仅首次缺少整个环境时才用引导解释器创建venv。

```powershell
Set-Location -LiteralPath 'F:\JavaAiNew\agent_project\COMP5511'
# Only if locked dependencies are missing:
.\.venv\Scripts\python.exe -m pip --isolated install --no-cache-dir --progress-bar off --only-binary=:all: --index-url https://pypi.org/simple --disable-pip-version-check -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q tests/test_datasets.py tests/test_ui.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

P01先检查8501是否占用再选用，不结束陌生进程；本轮服务保留在`http://127.0.0.1:8501`。后续测试按阶段使用下列具体测试路径；新增测试才能执行对应命令，不虚构测试输出。当前目录仍无Git仓库，无法区分tracked/untracked/staged/unstaged；本轮未初始化Git，已盘点全部实际源码、测试、依赖及样例，并保存`outputs/dev/p01/recovery-source-manifest.json`。`.gitignore`已排除venv、Key、私人上传及输出。

恢复安装时默认缓存模式出现CPU持续占用；公开PyPI和文件URL探测均200，而禁用缓存后的同版本安装成功。只读源码检查支持“沙箱外默认pip缓存写入触发Windows临时文件重试”的推断，未直接证实具体系统调用；因此采用`--no-cache-dir`绕过，不升级pip、清缓存或重建环境。诊断stack文件中的20秒标记是主动抓栈，不是安装超时；最终安装退出0。

## 4 阶段任务与验收

每个阶段先对照spec；只有本阶段小任务、必要验证及交接在授权范围内。阶段依赖完成前不绕过；“done”须满足第5节共同完成条件，不能用本轮文档或临时环境检查代替。

### P01_LOCAL_CSV_SLICE 本地上传与真实摘要

状态：done（2026-10-16，已有自动验证及用户人工验收均完成，仅限P01范围）。依赖：无开发阶段依赖。输入：spec R01–R03/D01/D08、已测环境方案。输出：首个可运行英文页面及真实CSV摘要，无模型。

- [x] P01.1 项目venv、锁定依赖、`.gitignore`和英文`app.py`已保存；恢复轮补齐中断安装，显式解释器3.12.4、`pip check`通过、真实服务可启动、无Key的AppTest通过。
- [x] P01.2 `comp5511/__init__.py`、`datasets.py`、`tests/test_datasets.py`、`tests/test_ui.py`和八行fixture在关机前已保存；恢复轮新增英文`README.md`。自动化已验证8行、Age缺失2/0.25、失败不保留旧预览；用户于2026-10-16明确报告人工验收通过，结果见下。

2026-10-16恢复轮实际自动验证（本次文档交接未重跑pip或pytest）：

- `.venv\Scripts\python.exe -m pip check`：退出0，`No broken requirements found.`；53项版本与锁定文件逐项匹配，7个关键模块导入成功。
- `.venv\Scripts\python.exe -m pytest -q tests/test_datasets.py tests/test_ui.py`：退出0，**45 passed in 5.17s**。涵盖AC01–AC04的P01部分，包括UTF-8/BOM、坏CSV/表头、缩小限额边界、JSON null/5行/10类别截断、不可变原表，以及AppTest实际上传、失败替换清旧表、重绘、不同会话和同文件重传。没有新写一遍源码或测试；原文件哈希未变。
- 先以socket bind确认8501空闲，再启动Streamlit；`/`返回200 HTML、`/_stcore/health`返回200和`ok`。服务继续运行，启动器PID30976，监听PID29308；实际状态见`outputs/dev/p01/service.json`、服务stdout/stderr及`http-check.json`。
- 恢复轮未连接可用浏览器，未由自动化验证文件选择器及渲染布局；本次用户亲手操作后明确确认P01人工验收通过，证据来源为用户反馈，见下方记录。AppTest和用户人工验收分别记录。
- 证据位于`outputs/dev/p01/`：`recovery-install-no-cache.log`、`pip-check.log`、`pytest.log`、`environment-check.json`、`http-check.json`和源码manifest；保留原始`install.log`及第一次恢复安装日志。人工负例文件为`manual/header_only.csv`和`manual/malformed.csv`。

2026-10-16用户人工验收记录（依据本次用户消息）：

- 正常八行样例的行列数、预览、类型和缺失摘要正确；对应Rows=8、Columns=3、Age缺失2/0.25。
- `header_only.csv`返回`EMPTY_DATASET`，旧预览及摘要消失。
- `malformed.csv`返回`CSV_PARSE_ERROR`，无旧数据残留。
- 清除后重新上传正常，错误消失，Dataset ID已改变。

本次交接另于2026-10-16 17:01（Asia/Shanghai）实时核对：既有P01服务仍监听`127.0.0.1:8501`（监听PID29308，启动器PID30976），首页与健康检查均200，health为`ok`。证据`outputs/dev/p01/handoff-http-check.json`。同时观察到8502由PID37364监听，用途未确认，本轮未处理该进程。

P01于2026-10-16人工验收后交接至P02_STATS；P02当前状态见下。P01的完成只覆盖本地上传/inspect及相关P01验收，不将45项测试或当次人工验收写成全部33个场景通过。

### P02_STATS 统计与结果上下文

状态：done（2026-10-16，本轮实现、自动验收、相关回归与独立代码审查完成；用户本阶段体验尚未记录）。依赖：P01。输入：当前数据与spec R04–R06；输出：UI可直接运行过滤/分组统计并查看真实结果表。

- [x] P02.1 新增`contracts.py`、`analysis.py`、`tests/test_analysis.py`。严格Pydantic参数、AND过滤、row_count/count/sum/mean、多指标alias、分组和稳定多键排序均已验证；缺失/null/空结果遵循D02，手算8/6/160/80÷3和0.75/0.25通过。
- [x] P02.2 新增`state.py`、`statistics_ui.py`、`tests/test_state.py`、`tests/test_ui_stats.py`，定点连接`app.py`并更新英文README。result_id绑定session/dataset/run；换文件、同文件重传、失败加载、新提交均使旧引用失效，两会话隔离；普通rerun不新建run，P01已加载会话可迁移并保持Dataset ID。

2026-10-16本轮实际验证（全部使用项目`.venv\Scripts\python.exe`）：

- `-m pip check`：退出0，`No broken requirements found.`；53项安装版本逐项匹配原锁定文件，未安装/升级依赖。P01的`datasets.py`、原两组测试及依赖文件均保持源码基线哈希。
- `-m pytest -q`：退出0，**138 passed in 8.41s**，证据`outputs/dev/p02/pytest.log`。涵盖全部已有P01回归和本阶段分析、上下文、页面操作测试；预期来自spec和明确手算，不用被测函数生成预期答案。
- 数据/计算覆盖AC05–AC08、AC29及AC09聚合部分：四项手算、7种比较、AND、合法零行、null组、数值列全空组/unknown列、文本NA保留、列名/类型/alias/排序错误、多键稳定与双向null-last、非有限输出拒绝、原Dataset不变。当前统计按不可变typed记录用显式Python计算，Pandas仅构建显示副本，避免默认NA改变语义。
- AC11与AC12的本阶段部分：真实aggregate→注册→读取；跨session/dataset/run、迟到发布/旧引用拒绝；AppTest实际操作多指标/过滤/in/分组/排序/空结果、非法新提交清旧结果、上传失败/清除/重传、同文件与不同schema切换、两会话和普通rerun。完整异步取消、模型/答案/图表流程尚未实现，不声称这些完整场景通过。
- 排错证据：初次UI集成在分组薄片未完成时如实失败，依赖实现完成后通过；修复数值均值的可表示极小值下溢；新增回归先复现P01旧session热更新丢当前Dataset，再通过迁移旧键修复。保留`ui-slice1.log`和`p01-session-repro.log`，最终以正常完整回归日志为准。
- 按code-review-and-quality独立审查计算层与UI/state，未遗留阻断问题。审查时仅在独立进程内禁用上下文保护，跨会话测试按预期失败（1 failed）；恢复内存方法，源码未改变。该变异检查单独记录，不计作正常套件通过或产品故障。
- 服务沿用`http://127.0.0.1:8501`，2026-10-16 17:24（Asia/Shanghai）首页/health均200、health为`ok`；监听PID29308，启动器PID30976。8502另有PID37364监听，用途未确认，未终止/重启任何服务。证据`outputs/dev/p02/http-check.json`及`service.json`。
- 浏览器工具本轮inventory为空，IAB/Chrome创建均不可用；用AppTest完成可自动执行的实际页面逻辑，未覆盖原生文件选择器、真实渲染布局及浏览器特有事件。此限制单列，不宣称浏览器自动验收或用户已确认P02；用户可集中体验README的核心流程，无须重做自动测试清单。

本轮证据统一在`outputs/dev/p02/`：源码基线/最终manifest、`pip-check.log`、最终`pytest.log`、分片日志、实际分组结果`grouped-survival.json`、服务HTTP记录及`verification.json`。阶段已满足P02自动验收条件；真实最大输入资源、图表、Controller、模型及正式实验均未验证，不计入P02完成。

P02结束时的历史接续点为P03_PLOTS；该阶段现已完成，当前接续点见下方P03交接。不得重做P01/P02或把图表值写死。

阶段大小复估：P02于17:10（Asia/Shanghai）记录开始，完整回归及17:24服务复核已完成，具体收尾时间见manifest；这是代理自动执行的部分墙钟证据，不是用户开发/理解耗时。P01跨关机且无完整起止和人工投入记录，无法据此推算每周吞吐或总工时。暂维持P03两个薄片（绘图契约/实值测试→页面与引用集成），P04高风险监督/取消单独成阶段；每周8–10小时的投入目标保持，待补齐用户体验、理解与排错耗时再定量调整。

### P03_PLOTS 图表与显式格式

状态：done（2026-10-16，账号切换后恢复现场，完成边界回归、最终自动验收、独立审查和交接）。依赖：P02。输出：真实结果引用的英文bar/line、底层数据和格式元数据。

展示补充状态：done（2026-10-16，用户明确授权中英界面；已实现、自动验收、审查及交接，不重新访谈）。

- [x] P03.3 `comp5511/i18n.py`集中静态文案/错误解释、`tests/test_i18n.py`及现有UI/图表测试：顶部English / 中文，默认英文并保持session选择；固定key/枚举，切换保留参数/原始数据/全部引用和既有PNG，不重算、不调用模型；新图默认文本随语言且自填内容保留；实际本机中文字体及缺字验证。
- 验证顺序：文案单元验证→英文/中文上传统计绘图AppTest及切换生命周期→中文PNG实际生成/查看→P01–P03相关完整回归及独立审查。预期来自规格和手算，不改变正式英文任务或评测数量；本轮仅维护既有README/spec/plan/HANDOFF。

P03.3本轮实际证据：

真实运行故障修复（2026-10-16，以下为本次新增验证，265项为上一轮磁盘代码证据）：

- 用户报告app.py:110的`render_statistics() takes 1 positional argument but 2 were given`，旧服务stderr于18:56:30记录同文异常。当前磁盘与明确venv导入的统计/绘图定义均`(session, language='en')`，无keyword-only问题；app仅两个调用点。旧8501自16:40:58运行，真实HTTP/WebSocket协议用英文/中文各上传八行CSV（HTTP204）均复现同一单参TypeError，绝对main_script_path为本项目app.py。由此确认长驻服务拿到旧入口对象，与磁盘当前接口不一致；为何自动模块重新加载未生效尚无证据，不猜测watcher配置或事件原因。
- app.py:110/111统一显式`language=language`，保留语言参数与原定义，不吞异常、不改统计/绘图语义。该调用澄清不能修复旧单参对象；实际运行修复为重新加载已确认属于本项目的服务进程。
- 通过限定PID的CIM核对旧启动器30976→监听29308，命令行均为项目Streamlit8501。第一次Stop-Process内部NullReference失败、旧服务仍在；复核身份后仅用.NET进程API停止29308，其启动器30976自动退出。随后确认8501空闲，用原venv、明确工作目录和绝对app.py重启；新启动器17348→监听10460、地址仍http://127.0.0.1:8501、health200/ok。身份前后与新日志见`outputs/dev/p03/live-entry-fix/`，未停止其他进程或启动重复服务。
- 新增现有`tests/test_ui_charts.py`中en/zh真实上传入口回归，透传真实renderer，核对模块来源/实际签名绑定/当前language、上传后统计区域、手算0.75/0.25与percent、参数/完整ID/PNG切换保留，以及切换后继续统计/绘图。聚焦**2 passed, 21 deselected in 3.99s**（`entry-regression.log`）；`.\.venv\Scripts\python.exe -m pytest -q`退出0，**267 passed in 23.73s**（`pytest.log`）。严格keyword-only spy的修改前失败只证明新增命名调用约定的敏感性，不冒称原磁盘双位置参数调用错误。
- 重启后直接驱动新8501后台HTTP/WebSocket两语言完整流程，均无应用异常：上传204→统计0.75/0.25→bar百分比底层/元数据→HTTP200下载有效PNG→语言切换来源元数据与PNG hash保留→新统计清旧下载→新图绑定新run/result/chart，session/dataset保持。`live-before-restart-{en,zh}.json`与`live-after-restart-{en,zh}.json`保存实际前后证据，探针为outputs内开发脚本，不是正式评测或浏览器截图。
- 265项原先已覆盖真实app.py的AppTest上传/中文流程，不是完全没有入口测试；AppTest运行在测试解释器，未连接长驻8501，旧服务当时只验证首页/health且被复用。真正缺口是接口变更后的长期进程升级与实际上传验证。本轮把“磁盘回归”和“当前服务功能”分开验收；以后修改已导入UI接口，重启已核对身份的服务并验证上传，不能以刷新/首页200替代。
- 独立code-review-and-quality复核入口调用与新测试，无未处理必改问题。浏览器inventory仍为空，未验证原生选择器、真实浏览器布局/下载落盘；AppTest和真正服务后台协议均已执行。重启会结束内存session，用户刷新原地址后需重新上传CSV。本轮仍停P03、无付费模型/正式实验。

- `.\.venv\Scripts\python.exe -m pytest -q`：退出0，**265 passed in 21.88s**，`outputs/dev/p03/i18n/pytest.log`。分片实际结果：文案16 passed、绘图53 passed、原P01/P02页面26 passed、新语言页面7 passed（14 deselected）；全套包含所有既有P01–P03回归，不将数量作正式评测或AC数量。
- AppTest执行英文/中文上传→统计→百分比图→下载、未提交控件跨语言保留、独立session默认English、错误解释/原错误对象、原始CSV/alias保真及换文件/失败清图。计数断言load/aggregate/plot各仅1次，切换前后dataset/run/result/chart ID、完整结果与PNG字节不变；仅明确Generate chart生成新图，默认标签随语言而自填标签保留。
- 实际本机字体Microsoft YaHei，`C:\Windows\Fonts\msyh.ttc`，FT2Font字形覆盖核对；仅渲染rc_context使用DejaVu Sans +中文fallback并恢复。中文类别与中文标题轴标签图，以及原始female/male加中文默认标题图，均实际生成并按原始分辨率查看，无缺字警告。证据`chinese-percent-bar.png/json`、`chinese-ui-percent.png/json`位于`outputs/dev/p03/i18n/`。
- code-review-and-quality两路独立只读审查，无未处理必改问题；进程内禁用中文默认同步/反转语言校验，相关测试均捕获故障并恢复；额外验证自填为旧默认字面值仍保留，新统计清旧图和默认元状态。中文渲染故障保留旧产物且恢复rcParams。汇总`outputs/dev/p03/i18n/verification.json`，最终源码哈希`source-manifest.json`。
- 浏览器inventory仍为空，IAB明确不可用；AppTest不替代原生文件选择器、浏览器页面布局与真实下载落盘。锁定Streamlit上传器内部Browse files/拖放提示无公开翻译接口，中文标签和help解释操作；如实保留此框架边界，不改框架/DOM或升级依赖。
- 8501既有服务复用，首页/health200/ok，仍监听PID29308；8502未监听。未启动重复服务、遗留测试任务、付费模型或正式实验；`.venv`、三个依赖文件、datasets/analysis/state及原八行fixture哈希不变。服务记录`outputs/dev/p03/i18n/http-check.json`。本轮只新增i18n源码及其测试，无重复文档。

- [x] P03.1 `plotting.py`、`contracts.py`、`tests/test_plotting.py`：落实x_kind、严格ISO日期、y_format/decimal_places/unit；验收AC09/AC10/AC31和非法参数。
- [x] P03.2 `chart_ui.py`连接`app.py`、`state.py`，配套`tests/test_state.py`/`tests/test_ui_charts.py`：展示/下载真实图与底层表，关闭Figure、拒过期引用；验收0.75→75.00%只改显示、日期稳定排序、无null伪0图。

验证：`python -m pytest -q tests/test_plotting.py tests/test_state.py`；由代理自动完成英文统计→图表的实际操作，核对真实计算值、底层绘图数据、标签和结果来源。无任意生成代码、无模型调用。

2026-10-16恢复轮实际证据（与中断前231项历史日志分开）：

- 现场没有`.git`，`git status`仍返回not a git repository；未初始化/清理目录。对照P03基线哈希，已有P03实现确实保存，HANDOFF仍停在P02；本轮复用全部源码，仅在现有`test_plotting.py`补边界验证，再更新README/plan/HANDOFF。P01/P02计算源码、原测试、样例、`.venv`和三个依赖文件保留。
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_plotting.py`：退出0，**49 passed in 3.73s**；日志`outputs/dev/p03/recovery-plotting-pytest.log`。补入最小正浮点值、百分比舍入上下界/半偶舍入/负边界、日期null x；直接断言转换后日期坐标间距60/228天。元数据、坐标轴formatter和柱高分别核对，底层0.75/0.25不缩放；预期来自规格、固定十进制手算和日历计算。
- `.\.venv\Scripts\python.exe -m pytest -q`：退出0，**238 passed in 17.65s**；日志`outputs/dev/p03/recovery-pytest.log`。包括P01/P02全部相关回归，以及bar保序/line稳定排序、严格日期/非法格式/null/空结果、真实来源、跨session/dataset/run隔离、失败发布、Figure清理、普通rerun、下载字节、换文件/失败加载/合法或非法新统计后旧图与下载入口清除。开发测试不计作正式实验或全部AC验收。
- `.venv`仍为Python3.12.4，`pip check`退出0，No broken requirements found；`recovery-pip-check.log`。依赖SHA-256与历史基线一致，未安装/升级包。未新增业务源码或测试文件。
- 通过真实AppTest上传/统计/绘图/下载表单另行生成三张代表PNG及底层JSON，位于`outputs/dev/p03/recovery-examples/`。bar特意使用统计降序验证保序：male0.25/female0.75显示25.00%/75.00%；数值线为2020/2021/2022与10/20/30；日期线为2026-01-01/03-02/10-16与10/20/30且保持真实间距。已实际按原始分辨率查看图：标题/标签完整、布局可读、日期刻度唯一；下载点击不新建run，来源统计保持不变。
- 按code-review-and-quality作绘图与UI/state两条独立审查，并复核本轮测试增量：无未处理阻断问题。仅在内存中反转百分比判断、绕过上下文校验，测试均捕获故障，finally恢复且源码未改；另计数确认普通rerun的aggregate/plot各仅调用1次。审查摘要见`outputs/dev/p03/recovery-verification.json`。
- 浏览器inventory为空，IAB与Chrome均明确不可用；AppTest已覆盖页面逻辑及下载控件，不冒称浏览器验收。未覆盖原生文件选择器、实际浏览器页面布局、下载落盘及浏览器特有事件。仅请用户集中体验一次上传→百分比图→下载→换文件清图，不需重跑自动测试。
- 17:59（Asia/Shanghai）核对既有`http://127.0.0.1:8501/`及health均200/ok；netstat为127.0.0.1:8501监听PID29308，启动器PID30976的路径/16:40:58启动时间匹配历史记录。8502当前无监听。CIM命令行读取权限不足，未停止/重启任何进程或启动重复服务；没有留存测试任务。证据`outputs/dev/p03/recovery-http-check.json`与恢复/最终manifest。

**next_task_id：`P04_RUNTIME`，状态todo；本轮停止，不实施。**下一轮先核对本交接和磁盘，再按P04验证Windows实际工具监督、deadline/取消与迟到结果；不重做P03，不调用付费模型或启动正式实验。

### P04_RUNTIME deadline与取消的早期验证

状态：todo。依赖：P03。输出：受监督的本地工具执行、统一deadline、取消/迟到隔离。

- [ ] P04.1 `runtime.py`、`tests/test_runtime.py`：monotonic deadline、generation和可取消等待；验收剩余5秒不能等待30秒，取消后不发起新工作。
- [ ] P04.2 `tool_worker.py`、`app.py`、`tests/test_worker.py`：Windows spawn工具worker、父进程发布/回收；验收慢工具在deadline/取消后实际停止，原始数据不变、迟到产物不注册，无残留worker或文件句柄。

验证：`python -m pytest -q tests/test_runtime.py tests/test_worker.py`，用可控时钟及短时限测试，不为测试真实等300秒；补一个实际spawn终止/回收集成案例，覆盖AC32。记录最大输入的耗时/峰值资源测量可用范围及清理耗时；未测极限继续标未验证，不擅改D01/D06。

### P05_BASELINE_OFFLINE 离线baseline闭环

状态：todo。依赖：P04。输出：标记Offline demo的完整工具Agent，不需要Key。

- [ ] P05.1 `providers.py`、`dispatch.py`、`contracts.py`、`tests/test_dispatch.py`：FakeProvider响应/白名单/schema及tool_call_id；验收正常调用、非法JSON/工具、安全保护相同。
- [ ] P05.2 `controller.py`、`app.py`、`tests/test_baseline.py`：问题→模型请求→真实本地工具→结果→英文最终回答；验收baseline首错立即停、批内后续skipped，不给修复机会。

验证：`python -m pytest -q tests/test_dispatch.py tests/test_baseline.py`；由代理自动操作完整离线路径并核对实际结果，覆盖AC12–AC15/AC25。FakeProvider脚本只用于开发验证，不标成真实模型推理效果。

### P06_PROPOSED 校验与有界修复

状态：todo。依赖：P05。输出：同一Controller的proposed增量及可观察错误反馈。

- [ ] P06.1 `validation.py`、`tests/test_validation.py`：当前列/dtype/值/结果预检与有限候选；验收共享工具未混入proposed逻辑，合法空集不触发修复。
- [ ] P06.2 `controller.py`、`app.py`、`tests/test_repair.py`：pending_error与整任务R计数；验收错误后模型改参、inspect-only消耗机会、第二次成功后可普通继续、无第三修复。

验证：`python -m pytest -q tests/test_validation.py tests/test_repair.py`，按AC13/AC14/AC16–AC19/AC22复核实际trace。恢复执行仍不等于原问题正确，由独立评分后判定。

### P07_BUDGET_PROTOCOL 调用预算与协议边界

状态：todo。依赖：P06。输出：统一8/2/10边界与显式网络重试计数。

- [ ] P07.1 `controller.py`、`contracts.py`、`tests/test_budget.py`、`tests/test_protocol.py`：多调用顺序/首错/skipped、T8、R2、禁tools收尾；验收AC15–AC24/AC30，协议关闭无遗漏。
- [ ] P07.2 `providers.py`、`runtime.py`、`tests/test_transport.py`：使用内存transport/慢响应验证整体HTTP超时、1/2秒退避、Retry-After和重试上限；验收逻辑/物理请求分开，无隐藏重试或工具重放。

验证：`python -m pytest -q tests/test_budget.py tests/test_protocol.py tests/test_transport.py`；此阶段仍不访问真实模型。共同配置和预算两版本一致。

### P08_LOG_UI 持久日志与稳定操作

状态：todo。依赖：P07。输出：脱敏JSONL、运行manifest、稳定英文UI及配置说明。

- [ ] P08.1 `runlog.py`、`config.py`、`controller.py`、`.env.example`、`tests/test_logging.py`：将Controller事件接入持久JSONL，记录attempt/skipped、first/pending error、T/R、请求数、真实/离线、usage/null和产物；验收一次实际离线完整run的日志能复算T/R/请求及终态，无Key/隐藏思维泄漏，不只测试logger单元函数。
- [ ] P08.2 `app.py`、`state.py`、`tests/test_ui.py`、`README.md`：rerun不重复运行、取消/换CSV拒迟到、partial/Unknown正确显示；验收AC11/AC12/AC25/AC30/AC32。

验证：`python -m pytest -q tests/test_logging.py tests/test_ui.py`；由代理优先自动执行两个独立会话的操作与隔离案例，浏览器不可用时用AppTest等可行方式验证并记录未覆盖行为；仅确有必要的自动化缺口交用户集中检查。日志路径统一`outputs/dev/<run_id>/`，只保存必要数据摘要和脱敏事件。

### P09_REAL_SMOKE 少量真实API与费用测算

状态：todo。依赖：P08；用户已有Key须在本机配置。输出：真实联调证据和预算测算，**不是正式实验**。

- [ ] P09.1 `deepseek.py`、`config.py`、`tests/test_deepseek.py`、`README.md`：依据当时官方文档实现HTTPX适配，MockTransport先测协议/错误/超时；验收三工具schema、tool_call_id和usage归一化，不把SDK字段当算法。
- [ ] P09.2 在受控少量英文开发题真实调用，记录准确model ID、thinking/生成参数、usage、延迟、物理请求和失败。执行前列明题数/调用上限及预估小额费用，按已有少量测算安排进行，不自动扩为正式题集；无法测得时如实停留未联调。

验证：先`python -m pytest -q tests/test_deepseek.py`；再在用户配置Key后少量真实正常/工具/修复路径。输出到`outputs/smoke/<measurement_id>/`，按当时官方价格及日期、输入/输出/缓存计费规则给出300次规模估算和余量，未知项单列；**用户明确确认总预算之前不得正式批量运行**。

### P10_DATA_TASKS 正式数据与40英文任务

状态：todo。依赖：P03契约稳定；可在其后独立准备，尚不依赖付费API。输出：官方来源数据manifest与20+20个可回答英文任务。

- [ ] P10.1 `data/`内Titanic train/Bike day原CSV及`evaluation/data_manifest.json`：核对来源、许可/访问方式、字段/缺失和SHA-256；Kaggle若需账户，由用户在本机完成必要获取，不用不明镜像替换已约定数据。
- [ ] P10.2 `evaluation/natural_tasks.json`、`evaluation/task_io.py`、`tests/test_task_io.py`：题目/所需输出/评分字段，覆盖过滤/分组/比较/bar/line；验收各20题、英文、能由现有工具回答，与spec开发样例隔离。

验证：`python -m pytest -q tests/test_task_io.py`；由代理逐题审阅可回答性并自行执行可自动完成的验证；本阶段不声称模型任务成功，也不将expected_outputs发给Agent。

### P11_REFERENCE_SCORING 独立参考与评分

状态：todo。依赖：P10及R04–R07语义稳定。输出：独立reference与可重复scorer。

- [ ] P11.1 `evaluation/references.py`、`tests/test_references.py`：直接基于原数据计算，不导入Agent工具/validator；由开发代理用独立手算或独立参考抽核缺失/count/分组/单位/图表数据。
- [ ] P11.2 `evaluation/scoring.py`、`tests/test_scoring.py`：按整题所需答案/表/图判分；验收整数/null、1e-6、键/行数、标签/单位和缺图，故意改0.75为0.25必须失败。

验证：`python -m pytest -q tests/test_references.py tests/test_scoring.py`，覆盖AC26/AC30。书面评分协议集中本计划的冻结记录及正式任务字段，不另建任务/进度副本。

### P12_FAULT_COMPARABILITY 故障协议与可比性

状态：todo。依赖：P07、P11。输出：10个冻结候选故障、注入器和独立可比性判定。

- [ ] P12.1 `evaluation/fault_cases.json`、`evaluation/faults.py`、`tests/test_faults.py`：同入口/工具/匹配条件/字段值，原合法性前提；验收未匹配或原错误不凑注入、不增加额外模型调用。
- [ ] P12.2 `evaluation/comparability.py`、`tests/test_comparability.py`：记录工具/字段/语义错误/规范化参数及数据lineage和必要上下文；验收AC33，both_triggered不自动comparable，随机result_id不直接判不同，结果差不能事后剔除。

验证：`python -m pytest -q tests/test_faults.py tests/test_comparability.py`；预故障规则、不可比/证据不足原因及分母可重算，尚未跑正式故障实验。

### P13_RUNNER_FREEZE dry-run与实验门槛

状态：todo。依赖：P08、P10–P12；真实启动另须P09/预算。输出：可恢复runner、metrics、冻结manifest及无付费dry-run。

- [ ] P13.1 `evaluation/runner.py`、`tests/test_runner.py`：枚举240自然+60故障、按task/run配对交替、每次重置上下文；验收resume不静默重复已完成运行，原失败和补跑均保留。
- [ ] P13.2 `evaluation/metrics.py`、`tests/test_metrics.py`、`configs/frozen.json`：冻结题/数据/代码/模型/prompt/schema/评分/故障/可比性/分母/超时/价格/预算；验收缺项、无预算确认记录或无Key时硬拒绝真实批量。

计划CLI（P13实现后才可运行）：`python -m evaluation.runner --config configs/frozen.json --dry-run`。用离线事件测试各版本120分母、故障各30计划状态、各自触发率与可比配对分母；0分母N/A。正式开关必须引用用户明确总预算确认及金额/日期，不能仅由程序自填一个approved布尔值。

### P14_FORMAL_RUN 冻结后的正式实验

状态：todo。依赖：P09、P13，**费用测算完成且用户明确确认总预算**，冻结配置经核对。输出：真实240+60运行记录及可审计评分，不承诺一定改善。

- [ ] P14.1 记录代码Git提交/tag或源码哈希、数据和完整配置；再dry-run核对题数、顺序、预算及冻结缺项。正式参数两版本一致，只保留R09机制差异。
- [ ] P14.2 按冻结协议运行/恢复，日志写`outputs/experiments/<experiment_id>/`；每请求前核对剩余额度，实际usage缺失、预计超预算或基础设施故障时暂停并记录，不自动增预算/减样本/换prompt。保留原失败、取消、未触发和不可比，补跑按预定规则执行。

验收：清单完整为240+60个计划状态，实际执行/未完成逐项清楚，独立评分和可比性可复算。真实用量与价格估算分开；远程取消可能仍计费，不能承诺网络断开就零成本。此阶段不得由本轮文档编写自动触发。

### P15_ENGLISH_DEMO 结果分析与英文演示

状态：todo。依赖：P14结果；无结果的方法/演示草稿可提前准备但明确状态。输出：真实结果图表、完整英文demo、slides和演讲/Q&A。

- [ ] P15.1 从日志复算成功/恢复/latency/调用/token，分别呈现自然与故障、波动、失败及不可比案例；配对结论仅用可比子集，不以未触发样本凑改善。
- [ ] P15.2 完成英文示例问题→英文答案/表/图/动作日志演示、slides及演讲；正常演示不强造故障，offline备用明确标签。讲述时长按教师最终安排（PDF暂定5–7分钟+1–2分钟问答）。

验收：代理先完成每项数字的日志溯源、英文图表单位及结果一致性核验，再交用户完整亲手演练以准备演示；失败/无改善也可解释。优先在slides截止前完成，不用伪造实测顶替。

### P16_REPORT_PACKAGE 英文报告与代码交付

状态：todo。依赖：P14、P15；可提前整理真实方法/来源，结果只能引用实测。输出：英文报告、复现README/锁定依赖/样例/代码ZIP、个人贡献与AI/外部资源声明。

- [ ] P16.1 报告覆盖课程Motivation/Description/Implementation/Data/Experiment/Discussions，解释整体机制与局限；报告页数8/10冲突仍须教师明确，不自行定成规则。
- [ ] P16.2 在干净环境按README复现代表流程及结果分析，检查源码与报告一致、敏感信息排除、ZIP可打开、引用与贡献对应实际证据。slides、报告和代码各自按Canvas页面核对截止/时区。

验收：另一环境可复现操作与日志分析，交付清单完整且无Key；发送/提交作业或公开部署另按用户明确指令执行，不因“打包完成”自动上传。

## 5 每阶段完成、交接与并行规则

- 阶段内按小任务连续实现和验证；每项仅在其具体AC满足、必要针对性测试及真实功能路径通过后标done。未验证写明，已有相关测试回归；不为低风险文档变更建立镜像实现的测试。
- 阶段结束先在本文件更新任务/阶段状态与实际证据路径，再更新`docs/HANDOFF.md`：实际目录/Git/环境、改动文件/接口、运行命令及结果、日志位置、未验证/卡点、服务/端口、下一阶段ID与验收。完成后停止，适合换新对话；详细教学安排验收后。
- 提前交接时保存文件及可恢复状态，保持in_progress并给出阶段内精确接续任务，说明后台任务是否结束；旧对话停止写入后才让新对话接续。上下文很长或阶段变大时提前拆分，仍只维护此计划及HANDOFF。
- 检查点：P02后重估时间；P04后确认Windows超时/取消可执行；P08后核对完整离线系统；P13后核对冻结与预算门槛；P14后核对真实结果，之后才写正式结论。
- P10/P11的数据和独立评分准备可在P03后提前，前提是契约已定、编辑目录独立且有单一负责人维护状态；共享contracts/controller/UI修改串行。并行不绕过阶段依赖或用户预算条件，不同时让两个对话修改同一工作区文件。

### 5.1 主动测试与阶段交付约定

2026-10-16用户明确约定，自后续阶段起默认执行。每个阶段由开发代理主动设计测试、实际执行、排错和回归，向用户交付可验收结果；不把能够自动完成的验证逐项转交用户。新对话读取本计划与HANDOFF后继续遵守，先核对当前阶段与授权范围，不因读取下一任务而自动跨阶段实施。

1. **规格与独立预期**：根据spec需求ID和本阶段AC设计测试，覆盖正常、异常、边界及相关回归，记录所覆盖的需求与预期来源。期望值来自规格、明确手算或独立参考；不得调用被测实现生成“正确答案”，也不得将当前输出直接复制成期望值后宣称通过。开发代理、被测Agent和独立reference的职责须区分；正式reference/scorer继续遵守独立性要求。
2. **实际执行与修复**：使用项目`.venv`的明确解释器运行相关测试，记录实际命令、退出状态和结果。发现实际故障时先复现、保留证据、定位根因，再修复并验证，持续到本阶段完成条件满足或遇到明确外部阻塞。外部阻塞须说明证据、影响范围、已经尝试的可行替代及解除所需条件；受阻或未满足完成条件的阶段不得标done。
3. **页面实际操作**：启动与HTTP检查只是基础检查，还须操作页面并核对结果。浏览器自动化可用时，代理自动完成本阶段相关的上传、错误文件替换、清除、重新上传及其他真实交互；不可用时，使用现有AppTest等方式验证实际页面逻辑，准确列出未覆盖的原生文件选择器、真实浏览器渲染或其他浏览器行为。不得把AppTest/HTTP通过写成浏览器操作通过，也不因浏览器不可用就跳过可自动完成的验证。
4. **统计与图表实值**：核对真实计算值、缺失/空结果、排序、底层数据、标签、单位和结果来源；按阶段验证dataset/run/result关联及过期引用。展示舍入、百分比和日期格式应与底层值及规格一致；不能仅凭图表存在、截图外观或模型文字判断正确，也不能用候选结果自身充当独立参考。
5. **相关回归与适度规模**：修改后运行受影响功能及已有相关回归，保护已经通过验收的路径；按风险决定是否扩大范围。测试规模与风险相称，不为凑数量重复测试，不在代码和风险均无变化时反复运行已通过的同一检查。纯文档更新以内容、链接、状态和改动范围核对为主，无需为其新增业务测试或重跑无关套件。
6. **证据与状态分开记录**：阶段汇报及plan/HANDOFF须列测试范围、实际结果、未验证事项和必要证据路径；证据按风险保留日志、截图、底层结果等。自动化通过、用户人工确认、少量真实API联调和正式实验分别标明来源、日期与范围。旧运行记录不得冒充本轮执行，测试数量不等于AC数量，本阶段通过不等于全部33个场景或正式实验完成。
7. **用户参与集中在必要事项**：用户主要在阶段结束体验核心流程、确认关键决定和准备演示；代理应先完成可自动化的验证。只将自动化确实无法覆盖且对验收必要的检查交给用户，并尽量集中为少量明确步骤，说明具体缺口；不把整套测试或逐项排错交给用户。需要人工确认的事项和阶段状态据实记录，不为没有必要的人工步骤增加完成门槛。
8. **费用与阶段边界不变**：API调用、少量测费和正式实验继续遵守既有阶段、费用及预算约定；自动化验证授权不扩大付费调用或正式实验权限。正式批量实验仍须先测费并获得用户明确总预算确认。阶段交接后停止，不自动开始下一阶段；本约定本身不授权开始新阶段，当前阶段以第4节及HANDOFF最新记录为准。

## 6 时间窗口、风险与待确认

用户每周8–10小时包括验收、排错、理解及演示，不等于全部时间可用于新增功能。P02后按真实耗时重估任务规模，不承诺固定每周阶段数。倒排目标为：slides前已有核心系统、真实实验与英文演示；报告/代码交付前完成复现和贡献说明。PDF日期仅作当前窗口：slides 11月15日23:59、演示11月20/27、报告代码11月29日23:59（2026）；**实际截止时间及时区须后续核对Canvas对应页面**。

| 风险/未定事项 | 处理 |
| --- | --- |
| 20 MiB/100,000行、30/300秒只是工程默认 | P04本地资源/取消实测，P09真实请求复核；不能写成已验证性能；冻结前共同调整并记录，8/2核心约束不暗改 |
| Windows进程启动/终止与清理成本 | P04先做真实spawn集成验证；记录清理开销与实际elapsed，父进程拒迟到发布，不用线程timeout冒充停止 |
| 模型ID/thinking/tool calling协议变化 | P09核对当时官方文档和真实响应，冻结模型/参数；本轮不硬编码未经联调的ID或假装真实兼容 |
| 数据获取/正式题覆盖/参考独立性 | P10核对官方文件，P11由开发代理用独立手算/参考抽核；本地开发fixture绝不混入40题 |
| 故障都触发但上下文不同 | P12按spec的预故障规则判可比，完整报告不可比/证据不足及分母，不强作配对改善 |
| 预算/真实usage未知或超支风险 | P09先少量测费，用户确认总额；P13/P14强门槛、保留暂停记录，不能自行缩240/60或用FakeProvider替代 |
| 课程页数、迟交、AI规定、演示场次 | 保留spec第7节待确认；Proposal暂无反馈不等于教师明确批准所有AI使用方式 |

未发现需要改变核心研究设计的实质冲突。P01已完成人工验收，P02/P03已完成实现、自动验收及审查；下一任务为P04_RUNTIME（todo，本轮未开始）。P02/P03暂无用户体验确认记录，浏览器自动化缺口如实保留。不重新访谈、不重写已完成需求与规格，不重复实现已完成页面。

## 附录A 2026-10-15临时环境历史验证记录

以下保留规划轮的历史快照，不代表当前源码或验收状态；当前P01/P02实现及实际测试以第4节与HANDOFF为准。

验证日期2026-10-15；引导Python 3.12.4 x64，pip 24.0。用 `python -I -m venv <项目外临时目录>\venv` 创建无system-site-packages的隔离环境，确认 `sys.prefix != sys.base_prefix`。从公开PyPI安装以下组合（含Windows wheels），未修改全局解释器或项目环境。

| 包 | 实测版本 |
| --- | --- |
| streamlit | 1.66.0 |
| pandas | 3.0.6 |
| matplotlib | 3.11.2 |
| pydantic | 2.14.1 |
| httpx | 0.28.1 |
| python-dotenv | 1.2.4 |
| pytest | 9.1.1 |
| numpy | 2.5.4 |

实际通过：完整安装；`pip check`返回`No broken requirements found.`；关键库导入；Pandas通用小表运算；Pydantic严格类型验证；Matplotlib Agg生成PNG；HTTPX内存MockTransport（无真实请求）；Streamlit AppTest的通用Hello页面（无exception）。AppTest初始化有bare-mode ScriptRunContext warning，但测试断言通过；未启动项目服务。

尚未验证：本项目CSV/统计/绘图/Controller等业务语义、33个验收场景、Windows工具监督/取消、输入极限与30/300秒可行性、DeepSeek协议及价格/usage、真实评测。pytest仅安装/导入，当前无项目测试可运行。临时安装/smoke日志保留于会话工具输出，临时环境及文件完成后清理；这里只保留已核对的结果与版本清单。

下面是实测`pip freeze`的53项完整环境锁定文本（不含pip）；P01保存为`requirements-lock.txt`，UTF-8/LF规范化SHA-256为`d690ded9fd5ba0938ec0646c0d3ff456b21dc6d5c7a8f3d170ee00ffbba4ea51`。它是环境重建依据，不是正式实验配置冻结。

```text
altair==6.3.0
annotated-types==0.8.0
anyio==4.15.1
attrs==26.1.0
certifi==2026.7.22
charset-normalizer==3.5.2
click==8.5.0
colorama==0.4.6
contourpy==1.4.0
cycler==0.12.1
fonttools==4.67.0
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.20
iniconfig==2.3.1
itsdangerous==2.2.0
Jinja2==3.1.6
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
kiwisolver==1.5.1
MarkupSafe==3.0.4
matplotlib==3.11.2
narwhals==2.27.1
numpy==2.5.4
packaging==26.3
pandas==3.0.6
pillow==12.3.0
pluggy==1.7.0
protobuf==7.36.2
pyarrow==26.0.0
pydantic==2.14.1
pydantic_core==2.50.1
pydeck==0.9.3
Pygments==2.21.0
pyparsing==3.3.3
pytest==9.1.1
python-dateutil==2.9.0.post0
python-dotenv==1.2.4
python-multipart==0.0.32
referencing==0.37.0
requests==2.34.2
rpds-py==2026.9.1
six==1.17.0
starlette==1.8.0
streamlit==1.66.0
typing-inspection==0.4.4
typing_extensions==4.16.0
tzdata==2026.5
urllib3==2.8.0
uvicorn==0.54.0
watchdog==6.0.0
websockets==17.2
```

## 附录B 官方技术依据

- [Streamlit安装与venv](https://docs.streamlit.io/get-started/installation/command-line)：支持范围与独立环境；本机兼容性以附录A实测为准。
- [Python版本生命周期](https://devguide.python.org/versions/)；[Python 3.12 multiprocessing](https://docs.python.org/3.12/library/multiprocessing.html)：Windows spawn与进程生命周期；[asyncio timeout/cancellation](https://docs.python.org/3.12/library/asyncio-task.html)。
- [HTTPX超时](https://www.python-httpx.org/advanced/timeouts/)与[传输/重试](https://www.python-httpx.org/advanced/transports/)：分项timeout不是整体deadline，重试显式控制。
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)及[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：模型请求/工具回传协议；具体线上配置仍待P09。
- 精确发布元数据：[streamlit](https://pypi.org/project/streamlit/)、[pandas](https://pypi.org/project/pandas/)、[matplotlib](https://pypi.org/project/matplotlib/)、[pydantic](https://pypi.org/project/pydantic/)、[httpx](https://pypi.org/project/httpx/)、[python-dotenv](https://pypi.org/project/python-dotenv/)、[pytest](https://pypi.org/project/pytest/)。核对日期2026-10-15，后续版本改变需重新验证。
