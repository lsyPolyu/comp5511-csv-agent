"""Deterministic interface translations; never translate data or tool identifiers."""

LANGUAGES = ("en", "zh")

# English source strings are stable lookup keys. A missing entry is an error so
# new interface copy cannot silently bypass the Chinese acceptance interface.
_TEXT_ZH = {
    "Interface language": "界面语言",
    "COMP5511 CSV Inspector": "COMP5511 CSV 检查器",
    "CSV Dataset Inspector": "CSV 数据集检查器",
    "Local tools only. No API key or model is used.": "仅使用本地工具，无需 API 密钥，不调用模型。",
    "Upload a CSV file": "上传 CSV 文件",
    "Choose Browse files to select a CSV, or drag one into the upload area.": "点击 Browse files（选择文件）上传 CSV，或将文件拖入上传区域。",
    "No current dataset. Select another CSV to continue.": "当前没有可用数据集，请选择另一个 CSV 文件继续。",
    "Select a CSV file to inspect its real data.": "请选择 CSV 文件以检查其中的真实数据。",
    "CSV loaded and inspected locally.": "已在本地加载并检查 CSV。",
    "Dataset ID: {dataset_id}": "数据集 ID：{dataset_id}",
    "Rows": "行数",
    "Columns": "列数",
    "Preview (first 5 rows)": "数据预览（前 5 行）",
    "Column summary": "列摘要",
    "Column": "列名",
    "Logical type": "逻辑类型",
    "Missing count": "缺失数量",
    "Missing ratio": "缺失比例",
    "Missing ratio = missing count / row count. Preview is limited to 5 rows.": "缺失比例 = 缺失数量 / 总行数。预览最多显示 5 行。",
    "Statistics result": "统计结果",
    "Showing the last submitted calculation. Editing controls does not run it again.": "显示最近一次提交的统计结果。修改控件不会重新运行统计。",
    "Result ID: {result_id} | Dataset ID: {dataset_id} | Run ID: {run_id}": "结果 ID：{result_id} | 数据集 ID：{dataset_id} | 任务 ID：{run_id}",
    "Filtered rows: {count}": "筛选后行数：{count}",
    "Missing group keys in {name!r} are displayed as {missing_label!r}.": "分组列 {name!r} 中的缺失值显示为 {missing_label!r}。",
    "<missing>": "<缺失>",
    "Calculation details": "计算详情",
    "Local statistics": "本地统计",
    "Set the number of filter, metric and sort rows, then configure the form and click Run statistics.": "先设置筛选条件、统计指标和排序字段的数量，再填写表单并点击“运行统计”。",
    "Number of filters": "筛选条件数量",
    "Number of metrics": "统计指标数量",
    "Number of sort keys": "排序字段数量",
    "Group by": "分组列",
    "**Filter {index} (all filters use AND)**": "**筛选条件 {index}（所有条件使用 AND）**",
    "Filter column {index}": "筛选列 {index}",
    "Filter operator {index}": "筛选运算符 {index}",
    "Filter value {index}": "筛选值 {index}",
    "For in, enter one value per line. Otherwise enter one value. Numeric columns require finite numbers; text stays literal.": "in 运算符每行填写一个值，其他运算符填写一个值。数值列必须使用有限数值；文本按原文匹配。",
    "row_count counts rows and uses No column. count counts nonmissing values. sum and mean require a numeric column. Aliases must be unique.": "row_count 统计行数并使用“无列”；count 统计非缺失值；sum 和 mean 需要数值列。别名（alias）必须唯一。",
    "Operation {index}": "统计方式 {index}",
    "Column {index}": "统计列 {index}",
    "Alias {index}": "别名（alias）{index}",
    "Sort field {index}": "排序字段 {index}",
    "Enter an exact grouping column name or metric alias. Keys are applied in this order; missing values are always last.": "输入完全一致的分组列名或统计指标别名。排序按此顺序依次应用，缺失值始终排在最后。",
    "Sort direction {index}": "排序方向 {index}",
    "Run statistics": "运行统计",
    "Chart from statistics": "基于统计结果绘图",
    "Source result: {result_id}. Generating or downloading a chart does not rerun statistics.": "来源结果：{result_id}。生成或下载图表不会重新运行统计。",
    "Source result": "来源结果",
    "Chart type": "图表类型",
    "X field": "X 字段",
    "Y field": "Y 字段",
    "Chart title": "图表标题",
    "X-axis label": "X 轴标签",
    "Y-axis label": "Y 轴标签",
    "For percent display, include (%) or (percent).": "显示百分比时，Y 轴标签必须包含 (%) 或 (percent)。",
    "X kind": "X 轴类型",
    "Default: category for bar, numeric for line. Line charts require numeric or date.": "默认：柱状图使用类别轴，折线图使用数值轴。折线图需要数值轴或日期轴。",
    "Date format": "日期格式",
    "Enter %Y-%m-%d only when X kind is date; leave empty otherwise.": "仅在 X 轴类型为日期时填写 %Y-%m-%d，其他情况请留空。",
    "Y format": "Y 值格式",
    "Decimal places": "小数位数",
    "Unit": "单位",
    "Use fraction for percent. Otherwise specify an English unit or unknown.": "显示百分比时填写 fraction；其他情况填写英文单位或 unknown。",
    "Generate chart": "生成图表",
    "Last successful chart: {chart_id} | Result: {result_id} | Run: {run_id}": "最近成功生成的图表：{chart_id} | 结果：{result_id} | 任务：{run_id}",
    "Download chart (PNG)": "下载图表（PNG）",
    "Underlying plot data": "底层绘图数据",
    "Source index": "来源行索引",
    "Original X": "原始 X 值",
    "Original Y": "原始 Y 值",
    "X sort key": "X 排序值",
    "Display X": "X 显示值",
    "Display Y": "Y 显示值",
    "Chart source and format": "图表来源与格式",
    "Analysis result": "统计结果",
    "X value": "X 值",
    "Value": "数值",
    "Value (%)": "数值 (%)",
}
_TEXT_ZH[
    "Upload one comma-separated CSV with a header, encoded as UTF-8 or UTF-8-BOM. "
    "Limits: 20 MiB and 100,000 data rows. Only empty fields count as missing."
] = "上传一个使用逗号分隔、包含表头且采用 UTF-8 或 UTF-8-BOM 编码的 CSV 文件。限制为 20 MiB、100,000 行数据。仅空字段视为缺失值。"

_OPTION_ZH = {
    "row_count": "行数（row_count）", "count": "非缺失值计数（count）",
    "sum": "求和（sum）", "mean": "平均值（mean）",
    "eq": "等于（eq）", "ne": "不等于（ne）", "gt": "大于（gt）",
    "ge": "大于或等于（ge）", "lt": "小于（lt）", "le": "小于或等于（le）",
    "in": "属于列表（in）", "asc": "升序（asc）", "desc": "降序（desc）",
    "bar": "柱状图（bar）", "line": "折线图（line）", "default": "默认（default）",
    "category": "类别（category）", "numeric": "数值（numeric）", "date": "日期（date）",
    "number": "数值（number）", "percent": "百分比（percent）",
    "unknown": "未知（unknown）", "fraction": "小数比例（fraction）", "text": "文本（text）",
}

_ERROR_ZH = {
    "UNSUPPORTED_INPUT": "请选择以逗号分隔的 .csv 文件。",
    "INPUT_LIMIT_EXCEEDED": "CSV 超出大小或行数限制（20 MiB、100,000 行数据）。",
    "EMPTY_DATASET": "CSV 必须包含有效表头和至少一行数据。",
    "CSV_PARSE_ERROR": "CSV 无法解析，请检查 UTF-8 编码、引号和每行的字段数量。",
    "INVALID_HEADER": "列名不能为空或重复。",
    "NO_DATASET": "请先上传有效的 CSV 文件。",
    "INVALID_ARGUMENTS": "统计参数无效，请检查必填字段、统计列以及分组列和别名的唯一性。",
    "INVALID_COLUMN": "所选列不存在，请使用当前数据集中的原始列名。",
    "INVALID_FILTER_TYPE": "筛选值和运算符必须匹配列类型；数值必须为有限数，in 运算符每行填写一个值。",
    "INCOMPATIBLE_AGGREGATION": "sum 和 mean 只能用于已知的数值列。",
    "INVALID_SORT_FIELD": "排序字段必须是结果中的分组列名或统计指标别名。",
    "EMPTY_RESULT": "没有行满足筛选条件；筛选条件未被修改。",
    "NUMERIC_ERROR": "计算无法得到有限数值，请检查输入数值范围。",
    "NO_VALID_VALUES": "一个或多个结果组中的统计指标没有非缺失值。",
    "INVALID_RESULT_REFERENCE": "该结果不属于当前会话、数据集或统计任务，或已失效，请先运行当前统计任务。",
    "INVALID_CHART_REFERENCE": "该图表不属于当前会话、数据集或统计任务，或已失效，请重新生成图表。",
    "INVALID_PLOT_FORMAT": "绘图格式无效：标题和轴标签须为非空可打印文字，单位须为英文；折线图需要数值或日期 X 轴；日期格式必须为 %Y-%m-%d；百分比需要 unit=fraction 且 Y 轴标签包含 (%) 或 (percent)；小数位数为 0–6。",
    "INVALID_PLOT_FIELD": "所选绘图字段不在当前统计结果中。",
    "INVALID_PLOT_X": "X 值无效：数值轴要求有限且非缺失的数值；日期轴要求真实存在且严格符合 YYYY-MM-DD 的日期。",
    "INVALID_PLOT_Y": "Y 字段必须是数值列，且仅包含有限数值或缺失值。",
    "NO_PLOTTABLE_DATA": "当前结果没有可绘制的行，或 Y 字段全部缺失。",
    "MISSING_PLOT_Y": "缺失的 Y 值保留为图中间隙，未补为 0。",
    "PLOT_RENDER_ERROR": "图表渲染失败，请检查绘图参数后重试。",
}


def _check_language(language: str) -> None:
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported interface language: {language!r}")


def text(key: str, language: str = "en", **values: object) -> str:
    """Translate registered interface copy, preserving supplied data verbatim."""
    _check_language(language)
    translated = _TEXT_ZH[key]
    return (key if language == "en" else translated).format(**values)


def option_label(value: str | None, language: str = "en") -> str:
    """Display a technical enum; callers must not pass original CSV values."""
    _check_language(language)
    if value is None:
        return "No column (row_count)" if language == "en" else "无列（row_count）"
    translated = _OPTION_ZH[value]
    return value if language == "en" else translated


def message_text(error_or_warning: dict, language: str = "en") -> str:
    """Keep codes and original detail, adding a deterministic Chinese explanation."""
    _check_language(language)
    code, message = error_or_warning["code"], error_or_warning["message"]
    if language == "en":
        return f"{code}: {message}"
    explanation = _ERROR_ZH.get(code, "操作未完成，请根据以下英文详情检查输入或配置。")
    return f"{code}: {explanation} 英文详情：{message}"


def chart_defaults(language: str = "en") -> dict[str, str]:
    """Return fresh defaults only; existing chart artifacts are not translated."""
    return {"chart_title": text("Analysis result", language),
            "chart_x_label": text("X value", language),
            "chart_y_label": text("Value", language)}
