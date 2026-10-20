# 最新开发交接

更新：2026-10-16（Asia/Shanghai）。**P01/P02/P03均done，包含P03.3中英展示与本次长驻服务旧入口修复；P04尚未开始，本轮停止交接。**最新全套267项通过，且重启后的真正8501已完成两语言上传/统计/绘图/下载/切换验证。此前265项只代表测试解释器中的磁盘代码回归，未覆盖长驻服务模块升级。

## 1 现场、范围与保留事项

- 目录：`F:\JavaAiNew\agent_project\COMP5511`。继续使用原`.venv\Scripts\python.exe`，Python3.12.4；未重建环境、安装/升级依赖或删除既有实现。
- 目录仍无`.git`，`git status`返回not a git repository；无branch/HEAD、tracked/untracked或diff可报告。未初始化/清理Git，用源码哈希记录磁盘。P03主体恢复时已核实旧HANDOFF落后于源码；恢复详情及238项历史回归保留于plan与`outputs/dev/p03/recovery-*`。
- 本轮新增`comp5511/i18n.py`、`tests/test_i18n.py`；修改app/statistics_ui/chart_ui、contracts/plotting及相关现有测试。更新既有spec/plan/README和本文件，无重复文档。
- `.venv`、三个依赖文件、datasets.py/analysis.py/state.py及原八行fixture保持历史哈希。复用P01–P03，不重写统计或数据解析。
- 用户明确授权中文操作与验收，故spec R01/R07与plan P03.3已更新；本轮不增加Agent中文问答、双语评测、模型调用或正式实验，不改变既定DeepSeek研究方案。

## 2 P03.3实际行为与接口

- 顶部`English / 中文`选择器，稳定key=`ui_language`、内部值en/zh，默认English，只在当前session保留。换文件/错误恢复不会重置语言，其他session独立。
- `i18n.py`集中管理`text`、`option_label`、`message_text`及`chart_defaults`。应用标题、说明、按钮、表单标签/帮助、摘要表头、状态和错误解释双语；技术项中文名加原英文枚举。
- 原CSV列名/类别/数据、alias、session/dataset/run/result/chart ID、工具schema字段/枚举和错误码原样保留。中文错误用静态code映射提供解释，保留英文详情；未知code有中文fallback。原错误对象不改，不调用模型翻译。
- 统计/图表控件从批量提交form改为即时同步session的控件；固定stats_*/chart_* key保留，只有Run statistics/Generate chart按钮分支执行。切换语言不加载CSV、不统计、不绘图，不改变已有结果/ID/PNG。
- `chart_ui._sync_defaults`只同步未自填标题/轴标签；自填通过on_change标记，哪怕明确改回旧默认字面值也保留。中文默认统计结果/X 值/数值，percent默认数值 (%)；英文默认Analysis result/X value/Value。已有PNG保持原产物，仅再次明确生成才用当前控件文字绘新图。
- PlotRequest标题/轴标签允许非空可打印Unicode，拒绝空白/换行/控制字符；unit仍按原英文语义，percent仍要求fraction且Y标签含(%)或(percent)。工具参数字段/枚举未新增语言字段。
- `plotting._font_config`检查实际文字的Unicode字形，优先保留DejaVu Sans并选择可覆盖的CJK字体。当前为Microsoft YaHei，文件`C:\Windows\Fonts\msyh.ttc`，使用FT2Font.get_charmap验证；仅渲染锁内rc_context设置font.family，不持久改全局配置。候选还有SimHei/Noto Sans CJK SC/Noto Sans SC/WenQuanYi Zen Hei；没有覆盖字体返回PLOT_RENDER_ERROR，不安装字体或包。
- P03主体行为保留：真实result引用、bar保序/line稳定排序、严格ISO日期与真实间距、null y缺口、空结果报错、percent显示不缩放底层值；换文件/失败加载/新统计清旧图与下载，Figure finally清理。具体接口和证据见plan P03。

## 3 本轮实际验证与审查

以下为代理开发验证，不是用户人工确认或正式实验：

- 完整命令`.\.venv\Scripts\python.exe -m pytest -q`，退出0，**265 passed in 21.88s**，日志`outputs/dev/p03/i18n/pytest.log`。包含P01–P03全部既有回归及语言补充。
- 分片实际结果：`tests/test_i18n.py`16 passed；`tests/test_plotting.py`53 passed；原P01/P02页面26 passed（`ui-regression.log`）；`tests/test_ui_charts.py -k 'language or chinese'`7 passed、14 deselected。其余准确命令/范围见`verification.json`。
- 英文/中文AppTest均执行上传→统计→绘图，中文百分比图与下载通过；预期0.75/0.25、75.00%/25.00%来自规格和手算，不调用被测实现生成预期。
- 跨语言保留尚未执行的filter/metric/sort/chart参数、原始CSV/alias、完整结果与PNG以及全部ID；计数确认load/aggregate/plot各只执行1次，语言切换不增调用。双语错误解释保留code/原对象，独立session默认English，中文换文件及失败加载清图通过。
- 实际生成并按原始分辨率查看`chinese-percent-bar.png`（中文CSV列/类别、自填中文标题轴）与`chinese-ui-percent.png`（中文页面默认标题轴、原female/male）。中文清晰、布局正常，missing-glyph warnings为空。PNG及JSON/字体/来源证据位于`outputs/dev/p03/i18n/`。
- code-review-and-quality两路独立只读审查，无未处理必改问题。内存禁用中文默认同步、反转语言校验后相关测试按预期失败，finally恢复且源码未改。附加AppTest验证自填旧默认值保留、新统计清默认元状态与旧PNG；中文渲染失败保留旧产物并恢复rcParams。
- 汇总`outputs/dev/p03/i18n/verification.json`，最终源码哈希`source-manifest.json`；旧P03恢复证据保留，不覆盖为本轮结果。此前PowerShell管道会污染中文测试字面值，生成脚本使用ASCII Unicode转义，中文文档直接UTF-8写入并复核。

### 3.1 最新真实运行故障与修复

- 真实异常：旧8501服务18:56:30在app.py:110报告render_statistics单参TypeError。当前实际源码、venv导入来源和inspect.signature确认statistics_ui/chart_ui两入口均为(session, language='en')，不是language关键字限定问题或磁盘接口漏改。
- 未改源码/未重启前，直接用真实8501 HTTP/WebSocket后台协议，英文和中文分别上传CSV（HTTP204）均复现同文异常，服务返回绝对项目app.py路径。说明新app调用混用了长驻进程内旧单参入口；具体为何自动重载未刷新旧对象缺少直接证据，未推断watcher配置错误。
- 仅生产改动为app.py:110/111显式language=language，两真实定义保留、异常不吞。明确命名调用不是旧对象修复；实际修复是定向重启经命令行确认的本项目服务。新增现有test_ui_charts.py中的en/zh真实上传入口回归，检查真实模块来源、签名绑定、切换保留及后续统计/绘图。
- 本轮聚焦2 passed、21 deselected in3.99s；全套267 passed in23.73s。修改前strict spy失败是命名调用约定测试，不当作原磁盘接口故障。原265项早已覆盖AppTest上传与中文流程；漏检的是测试解释器与长驻8501不同进程，之前只对后者检查首页/health。
- 新服务真实后台完整两语言流程通过，无应用异常：上传/统计0.75与0.25/percent PNG/下载200/切换保持来源ID与PNG hash/新统计清旧入口/继续绘图绑定新run。AppTest与后台协议独立，不冒充真实浏览器渲染。
- 证据在outputs/dev/p03/live-entry-fix/：旧服务trace、source-before.json、live-before-restart-en/zh.json、live-after-restart-en/zh.json、entry-regression.log、pytest.log、进程前后JSON、service.json、新服务stdout/stderr、verification.json及最终source-manifest.json。protocol_probe.py是开发后台探针，不是正式实验或业务模块。依赖/工具定义不变，无P04或付费调用。

## 4 服务与真实边界

- 当前地址仍为**http://127.0.0.1:8501/**。19:06:58（Asia/Shanghai）用项目venv、明确工作目录与绝对app.py重启，新启动器PID17348、监听PID10460；健康200/ok，真实上传后功能验证已通过。最新记录为`outputs/dev/p03/live-entry-fix/service.json`及processes-after-restart.json；i18n/http-check.json是重启前历史记录。
- 本次限定PID的CIM已成功读取命令行，确认旧30976/29308属于本项目。Stop-Process首次内部异常没有停止旧服务；改用.NET API仅停止已复核的29308，30976自动退出，然后确认端口空闲再启动。没有结束其他进程。以后重新核对身份，PID可能复用；所有测试/生成/探针/审查已结束，无并发写入或遗留任务。
- 本轮浏览器inventory仍为空，IAB明确返回Browser is not available。AppTest不覆盖原生文件选择器、真实浏览器页面布局、实际PNG下载落盘或浏览器特有事件；PNG自身已实际视觉查看。
- 框架限制：锁定版Streamlit原生上传器内部Browse files/拖放提示无公开翻译参数，保留英文；应用提供中文上传标签和帮助，浏览器/操作系统对话框使用自身语言。官方file_uploader文档已核对，链接见README；未改框架、CSS伪替换DOM或升级依赖来隐藏限制。
- P01已有用户人工验收记录；P02/P03及本补充暂无用户体验确认。只需集中体验一次顶部切中文→上传八行→Sex分组mean(Survived)→percent/fraction图→切英文检查旧图保留→下载PNG。无需用户重跑自动清单。

## 5 使用与精确接续点

刷新原8501地址，重启后旧内存session已结束，需重新上传CSV。顶部选中文；上传`data/dev/eight_rows.csv`，分组列选Sex，统计方式选平均值（mean），统计列选Survived，alias填rate，点击运行统计。图表类型柱状图（bar）、X=Sex、Y=rate；Y值格式选百分比（percent），单位填fraction，小数位数2，未自填Y标签自动为数值 (%)，点击生成图表。底层仍0.75/0.25，显示75.00%/25.00%；可下载图表（PNG）。切语言不重画已生成图，自填文字保留。以后改变已导入UI模块接口须重启已核对身份的服务并验证实际上传；浏览器刷新或首页200不保证Python模块已更新。

课程展示请选English；正式英文任务、实验配置、答案/报告/slides和口头演讲范围不变。本次仅为中文操作验收，不做Agent中文问答或双语评测。

**next_task_id：P04_RUNTIME，状态todo；本轮不开始。**下一轮读取本交接、plan P04及spec R06/R08/R12/R13/AC32，核对现场与服务，复用已有P03接口，按P04薄片实现Windows spawn工具监督、deadline/取消、迟到拒收及清理证据。P03语言或上下文测试不等于实际worker取消验证。

尚未验证且不属于本补充：最大输入性能/内存、真实30/300秒deadline及worker停止、Controller/Agent/FakeProvider、DeepSeek协议/API/价格/usage、完整33场景、正式reference/scorer、240+60正式运行、报告/演示。P04–P16保持todo。

持续约束：plan为唯一任务索引，主动验证见第5.1节；保留单CSV/白名单、baseline首错停止/proposed最多2次修复、8次工具尝试、240+60分开统计。正式实验前先测费再由用户确认总预算，不记录密钥。课程规则/截止时间冲突与演示安排仍见spec/intent待确认；不以代理墙钟推算用户人力吞吐。
