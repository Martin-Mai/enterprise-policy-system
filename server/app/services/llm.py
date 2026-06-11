"""
大模型服务模块
通过 httpx 异步流式调用本地 Ollama 生成接口，并提供数值合规后处理安全垫
"""

import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Ollama 服务调用异常"""


# ---------------------------------------------------------------------------
# 数值合规审计协议（注入 RAG System Prompt，禁止硬编码当前业务阈值）
# ---------------------------------------------------------------------------
PLAIN_TEXT_MATH_FORMAT_PROTOCOL: str = """
【数学表达式输出格式 · 强制纯文本】
回答中涉及计算、公式或数值推导时，必须使用纯文本或简单算术表达式，严禁使用任何 LaTeX、MathML 或类似复杂数学标记。

禁止输出的 LaTeX 命令与写法（包括但不限于）：
- \\times、\\frac、\\text、\\div、\\cdot、\\sqrt、\\sum 等反斜杠命令
- \\[ ... \\]、\\( ... \\)、$ ... $、$$ ... $$ 等数学定界符
- 用方括号包裹的 LaTeX 算式，如 [ 200 \\times 1.5 \\times \\frac{4}{8} = 150 \\text{ 元} ]

必须使用的纯文本写法：
- 乘法：* 或中文「乘」，或符号 ×
- 除法：/ 或中文「除以」，或符号 ÷
- 分数：4/8 或「4除以8」，禁止 \\frac{4}{8}
- 等号：=
- 单位与文字：直接写「元」「天」等，禁止 \\text{ 元 }

正确示例：
- 200 * 1.5 * (4/8) = 150 元
- 200 × 1.5 × 4 ÷ 8 = 150 元
- 总额度 10 天，已休 0 天，剩余 10 天

错误示例（严禁）：
- \\[ 200 \\times 1.5 \\times \\frac{4}{8} = 150 \\text{ 元} \\]
- $4500 > 3000$
"""

NUMERICAL_COMPLIANCE_AUDIT_PROTOCOL: str = """
【严苛的数值合规审计协议】
在生成最终答案之前，你必须在内心严格执行以下思维链分析（推理过程不要输出给用户，仅输出最终结论）：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💥 核心红线：禁止无依据脑补计算
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 你的推理与计算过程，【只能】且【必须】使用参考资料中明文出现的数字、公式和已知条件。
2. 如果参考资料中没有提及「已休假 X 天」「已使用 Y 额度」等明确扣减/扣除信息，你【绝对禁止】擅自假设、推测或凭空捏造任何扣减数值。
3. 对于用户明确处于「未休」「未使用」「全新」「从未使用」状态的业务请求，必须直接输出制度规定的【总额度/总天数】，不得进行任何擅自的加减法运算。
4. 严禁将参考资料中的总额度与用户未提及的「已消耗量」做减法（例如：资料写 10 天年假，用户说未休，禁止输出 10-5=5 天）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A. 金额审批类（差旅/报销/采购等）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
步骤一 [阈值检索]：从参考资料中找出所有涉及金额红线、审批阈值、限额标准的描述，精确提取其数值与单位（如「X 万元」「Y 元」）。
步骤二 [请求提取]：从用户当前提问中，精确提取涉事金额数值与单位。
步骤三 [单位归一与数学比对]：将两者统一换算为同一货币单位（元），在内心明确执行数学上的【大于 / 等于 / 小于】判定，禁止凭语感猜测。
步骤四 [规则应用]：根据比对结果，绝对严谨地套用规则，得出是否需要审批、由谁签批的最终结论。

【禁止】在未完成上述四步数值比对前，不得给出「无需审批」「未超过」「正常通过」等放行类结论。
【禁止】将较大金额误判为未超过较小阈值。

[合规审计推理范例 · 金额]
参考资料："差旅费超过 3000 元需总监审批。"
用户问题："我这次出差报销 4500 元可以吗？"
模型推理过程：
1. 规则阈值：3000 元
2. 申请金额：4500 元
3. 数值比对：4500 > 3000，已超过阈值。
4. 最终结论：不可以自行报销，您的差旅费已超过 3000 元，需要总监审批。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
B. 天数/额度类（年假/休假/带薪假等）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
步骤一 [资格审查]：核对用户条件（工龄、职级等）是否满足规则门槛。
步骤二 [额度提取]：从参考资料中精确提取匹配规则对应的【总额度/总天数】，不得引用其他档位的数字。
步骤三 [状态核对]：从用户提问中提取消耗状态（已休/未休/已用/未用）；若用户明确「未休/未使用」，则已消耗量 = 0。
步骤四 [数值合法性检查]（强制步骤，不可跳过）：
   - 核对最终输出的数字：该数字是直接来自参考资料原文（是/否）？
   - 若通过计算得出：公式中每一个变量（总天数、已休天数等）是否在资料中有明文数据支持（是/否）？
   - 若无明文支持：立即作废该计算，强制复原为原文总额度，并注明「因用户未休/未使用，故全额享受，无任何扣减」。

[合规审计推理范例 · 年假未休]
参考资料："规则：员工工龄满 10 年者，每年可享受 10 天法定年假。"
用户问题："我工龄 12 年，今年到目前为止还从未休过年假，请问我现在能休几天？"
模型正规推理过程：
1. 资格审查：用户工龄 12 年 >= 10 年门槛，成功匹配规则。
2. 额度提取：匹配规则对应的总年假天数为 10 天。
3. 状态核对：用户明确说明「从未休过年假」，即已休天数 = 0。
4. 数值合法性检查：资料中没有任何关于「扣减 5 天」或「已休 5 天」的信息。因此，严禁执行 10 - 5 的幻觉扣减。
5. 最终结论：您本年度尚未休过年假，因此可全额享受制度规定的 10 天年假。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C. 工资/津贴类 · 单位换算强制规范（日/月/年/小时）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
当参考资料或用户问题中出现「日工资」「小时工资」「月薪」「年薪」「加班按 X 倍」等描述时，
你必须在内心【强制】增加「单位归一化（Unit Normalization）」步骤：先统一时间/金额单位，再列公式计算。

跨单位换算默认基准（若资料有明文标准则以资料为准）：
- 1 天 = 8 小时（或资料中的「标准工作 X 小时/天」）
- 1 个月 = 21.75 天
- 1 年 = 12 个月

强制步骤：
步骤一 [单位识别]：识别工资基准单位（日/月/年）与计算目标单位（小时/日/月）。
步骤二 [单位归一化]：将基准工资换算为目标单位。例如：小时工资 = 日工资 ÷ 标准工时。
步骤三 [规则套用]：在归一化后的单位上乘以倍数、小时数等变量。
步骤四 [结果校验]：严禁跳过归一化直接「日工资 × 倍数 × 小时数」。

[合规审计推理范例 · 加班费（日薪 × 小时）]
参考资料："工作日加班按1.5倍工资支付加班费。日工资200元，标准工作8小时。"
用户问题："加班4小时，应得多少加班费？"
模型正规推理过程：
1. 单位识别：基准为「日工资 200 元/天」，目标为按「小时」计加班费。
2. 单位归一化：小时工资 = 日工资 ÷ 8 = 200 ÷ 8 = 25 元/小时。
3. 规则套用：加班费 = 小时工资 × 1.5 × 加班小时数 = 25 × 1.5 × 4 = 150 元。
4. 结果校验：确认未使用错误算法「200 × 1.5 × 4 = 1200 元」。
5. 最终结论：您加班 4 小时，应得加班费 150 元。

【严禁】跨单位混算而不换算（如日工资直接乘以加班小时数）。
【严禁】输出未除以标准工时的「日工资 × 倍数 × 小时数」类错误算式。
"""

# 安全垫触发后返回给用户的统一纠正文案（金额超标放行类）
NUMERICAL_COMPLIANCE_CORRECTION: str = (
    "提示：系统触发合规红线拦截。根据制度，您的申请金额已超过规定阈值，"
    "请务必提交对应负责人审批。"
)

# 安全垫触发后返回给用户的纠正文案模板（未休状态下幻觉扣减类）
UNAUTHORIZED_DEDUCTION_CORRECTION_TEMPLATE: str = (
    "[合规系统提示] 检测到模型生成逻辑出现异常缩减。"
    "根据您提供的「{status_hint}」状态与制度规范，"
    "您当前可全额享受 {baseline_days:g} 天{quota_label}，无需扣减。"
)

UNIT_CONVERSION_CORRECTION_TEMPLATE: str = (
    "[合规系统提示] 检测到工资单位换算错误，已自动修正如下：\n"
    "{steps_text}\n"
    "最终结论：{conclusion}"
)

# ---------------------------------------------------------------------------
# 单位换算合规：日薪/月薪/年薪 ↔ 小时 跨单位计算
# ---------------------------------------------------------------------------
_DEFAULT_HOURS_PER_DAY: float = 8.0
_DEFAULT_DAYS_PER_MONTH: float = 21.75
_DEFAULT_MONTHS_PER_YEAR: float = 12.0

_HOURLY_QUANTITY_QUERY_KEYWORDS: Tuple[str, ...] = (
    "加班",
    "加班费",
    "超时",
    "加点",
    "防暑津贴",
    "高温津贴",
)
_HOURLY_QUANTITY_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:个)?小时")
_DAILY_WAGE_PATTERN = re.compile(
    r"日(?:工资|薪)(?:为|是|约|大约)?\s*(\d+(?:\.\d+)?)\s*元?",
)
_MONTHLY_WAGE_PATTERN = re.compile(
    r"月(?:工资|薪)(?:为|是|约|大约)?\s*(\d+(?:\.\d+)?)\s*元?",
)
_YEARLY_WAGE_PATTERN = re.compile(
    r"(?:年(?:工资|薪)|年薪)(?:为|是|约|大约)?\s*(\d+(?:\.\d+)?)\s*元?",
)
_STANDARD_HOURS_PER_DAY_PATTERN = re.compile(
    r"(?:标准工作|每(?:日|天)工作|每日工作|一天工作|工作)\s*(\d+(?:\.\d+)?)\s*小时",
)
_PAY_MULTIPLIER_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*倍(?:工资|薪资|薪酬|支付)?",
)
_WRONG_DAILY_TO_HOURLY_CALC_PATTERN = re.compile(
    r"日(?:工资|薪)[^\n=]{0,40}?"
    r"(\d+(?:\.\d+)?)\s*[×*xX]\s*"
    r"(\d+(?:\.\d+)?)\s*[×*xX]\s*"
    r"(\d+(?:\.\d+)?)",
)
_ANSWER_CONCLUSION_AMOUNT_PATTERN = re.compile(
    r"(?:=|为|是|约|大约|共计|共|应得|可得|应付|共计)\s*(\d+(?:\.\d+)?)\s*元",
)
_DAILY_RATE_QUERY_PATTERN = re.compile(r"日(?:工资|薪)")
_MONTHLY_RATE_QUERY_PATTERN = re.compile(r"月(?:工资|薪)")

# ---------------------------------------------------------------------------
# 金额解析：支持 万/元/RMB/￥/逗号分隔等中文与半角写法
# ---------------------------------------------------------------------------
_WAN_AMOUNT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:万|萬|[wW])"
    r"(?:\s*(?:元|块|人民币|RMB|rmb|￥|¥))?",
    re.IGNORECASE,
)
_YUAN_AMOUNT_PATTERN = re.compile(
    r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:元|块|人民币|RMB|rmb|￥|¥)",
    re.IGNORECASE,
)
# 无单位但位数较长的大额整数，按「元」理解（如 120000）
_LARGE_PLAIN_AMOUNT_PATTERN = re.compile(
    r"(?<![\d.])(\d+(?:,\d{3})+|\d{5,})(?![\d.])(?!\s*(?:万|萬|[wW]))",
)

# 从制度文本中提取审批阈值：「超过/大于 … X 万/元」或「X 万 … 红线/阈值/审批」
_THRESHOLD_LEADING_PATTERN = re.compile(
    r"(?:超过|大于|高于|不少于|不低于|达到|满|超出|突破|击穿|以上|及以上)"
    r"[\s]*"
    r"(?:人民币)?"
    r"[\s]*"
    r"(\d+(?:\.\d+)?)\s*(万|萬|[wW]|元|块|人民币|RMB|rmb|￥|¥)?",
    re.IGNORECASE,
)
_THRESHOLD_TRAILING_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(万|萬|[wW]|元|块|人民币|RMB|rmb|￥|¥)?"
    r"[\s]*(?:审批红线|红线|阈值|上限|限额|审批线|需.*?审批|须.*?审批|应.*?审批)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# 天数/额度合规：检测「零消耗」用户表述 & 从资料/回答中提取天数
# ---------------------------------------------------------------------------
_ZERO_CONSUMPTION_KEYWORDS: Tuple[str, ...] = (
    "未休",
    "未休假",
    "没请过假",
    "没请假",
    "未使用",
    "全年未动",
    "从未休",
    "还没休",
    "没有休",
    "一次都没",
    "零消耗",
    "尚未休",
    "尚未使用",
    "还未休",
    "还未使用",
    "没休过",
    "没用过",
    "全新",
    "全额",
)

# 制度文本中与「天数额度」相关的语境关键词
_DAY_QUOTA_CONTEXT_KEYWORDS: Tuple[str, ...] = (
    "年假",
    "休假",
    "带薪假",
    "假期",
    "法定假",
    "调休",
    "病假",
    "事假",
    "产假",
    "陪产假",
)

# 从制度文本提取「X 天」额度：数字前后 40 字内须含额度语境词
_DAY_QUOTA_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*天",
    re.IGNORECASE,
)
# 从制度文本提取「享受/享有 X 天」类表述
_DAY_ENTITLEMENT_PATTERN = re.compile(
    r"(?:享受|享有|可休|获得|发放|给予|共计|共)\s*(\d+(?:\.\d+)?)\s*天",
    re.IGNORECASE,
)
# 从模型回答中提取「结论性天数」：可休/剩余/还能/享有 等引导词后的数字
_ANSWER_CONCLUSION_DAY_PATTERN = re.compile(
    r"(?:可(?:休|享受|享有|申请|请)|剩余|还能|应该|应当|一共|共|全额|总共|目前|现在|"
    r"因此|所以|结论|答案|享有|获得)\s*(?:为|是|约|大概|大约)?\s*(\d+(?:\.\d+)?)\s*天",
    re.IGNORECASE,
)
# 从模型回答中提取所有「X 天」表述
_ANSWER_ANY_DAY_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*天",
    re.IGNORECASE,
)
# 资料中是否存在「已休/扣减/剩余」等扣减依据
_DEDUCTION_EVIDENCE_PATTERN = re.compile(
    r"(?:已休|已使用|已消耗|已请|扣减|扣除|减去|剩余|结余)\s*(?:\d+(?:\.\d+)?)\s*天",
    re.IGNORECASE,
)

# LLM 误判放行时的典型措辞
_RELEASE_PHRASES: Tuple[str, ...] = (
    "无需审批",
    "不需要审批",
    "无须审批",
    "不用审批",
    "不必审批",
    "未超过",
    "不超过",
    "尚未超过",
    "没有超过",
    "未达",
    "未触及",
    "正常通过",
    "可以自行",
    "可自行",
    "无需提交",
    "不触发",
    "无需报备",
    "无需走审批",
    "可以直接",
)

# LaTeX / 数学标记净化
_LATEX_INLINE_MATH_PATTERN = re.compile(r"\$\$([^$]+)\$\$|\$([^$]+)\$")
_LATEX_DISPLAY_MATH_PATTERN = re.compile(r"\\\[(.*?)\\\]", re.DOTALL)
_LATEX_PAREN_MATH_PATTERN = re.compile(r"\\\((.*?)\\\)", re.DOTALL)
_LATEX_BRACKET_BLOCK_PATTERN = re.compile(r"\[\s*([^\]]*\\[^\]]+)\]")
_LATEX_FRAC_PATTERN = re.compile(r"\\frac\{([^{}]+)\}\{([^{}]+)\}")
_LATEX_TEXT_PATTERN = re.compile(r"\\text\{([^{}]*)\}")
_LATEX_COMMAND_REPLACEMENTS: Tuple[Tuple[str, str], ...] = (
    (r"\\times", "×"),
    (r"\\div", "÷"),
    (r"\\cdot", "×"),
    (r"\\pm", "±"),
    (r"\\leq", "≤"),
    (r"\\geq", "≥"),
    (r"\\neq", "≠"),
    (r"\\approx", "≈"),
    (r"\\%", "%"),
)
_LATEX_REMAINING_COMMAND_PATTERN = re.compile(
    r"\\(?:mathrm|mathbf|textbf|textit|left|right|big|Big|small)\{[^{}]*\}|\\[a-zA-Z]+",
)
_LATEX_INCOMPLETE_TAIL_PATTERN = re.compile(
    r"(?:\\(?:[a-zA-Z]*)?$|\\(?:frac|text)\{[^{}]*$|\$\s*$|\\[\[(]?$|\[\s*[^\]]*\\[^\]]*$)",
)


def _strip_latex_delimiters(text: str) -> str:
    """移除 LaTeX 定界符，保留内部纯文本内容。"""
    result = _LATEX_DISPLAY_MATH_PATTERN.sub(r"\1", text)
    result = _LATEX_PAREN_MATH_PATTERN.sub(r"\1", result)
    result = _LATEX_INLINE_MATH_PATTERN.sub(
        lambda match: match.group(1) or match.group(2) or "",
        result,
    )
    result = _LATEX_BRACKET_BLOCK_PATTERN.sub(r"\1", result)
    return result


def sanitize_latex_math(text: str) -> str:
    """
    将模型输出中的 LaTeX / MathML 风格数学标记转换为纯文本。

    作为流式回答的安全垫：无论模型是否遵守 Prompt，落库与推送前均经此函数处理。
    """
    if not text:
        return text

    result = text.replace(r"\$", "$")
    result = _strip_latex_delimiters(result)

    while True:
        replaced = _LATEX_FRAC_PATTERN.sub(r"\1/\2", result)
        if replaced == result:
            break
        result = replaced

    result = _LATEX_TEXT_PATTERN.sub(r"\1", result)

    for pattern, replacement in _LATEX_COMMAND_REPLACEMENTS:
        result = re.sub(pattern, replacement, result)

    result = _LATEX_REMAINING_COMMAND_PATTERN.sub("", result)
    result = result.replace("\\", "")
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip() if text == text.strip() else result


def _has_incomplete_latex(text: str) -> bool:
    """检测缓冲区末尾是否存在尚未闭合的 LaTeX 片段，供流式 hold-back 使用。"""
    if not text:
        return False
    if _LATEX_INCOMPLETE_TAIL_PATTERN.search(text):
        return True
    if text.count("$") % 2 == 1:
        return True
    if text.count("\\[") > text.count("\\]"):
        return True
    if text.count("\\(") > text.count("\\)"):
        return True

    last_open = text.rfind("[")
    if last_open != -1 and "]" not in text[last_open:]:
        segment = text[last_open:]
        inner = segment[1:]
        # 引用编号 [1] 在闭合前 hold-back，避免误拆
        if re.fullmatch(r"\s*\d*", inner):
            return True
        # 含 LaTeX 命令，或「[ 200 ...」类算式块，在 ] 闭合前 hold-back
        if "\\" in segment or re.match(r"\s+\d", inner):
            return True

    return False


class LatexStreamSanitizer:
    """流式 LaTeX 净化器：hold-back 未闭合片段，仅向前端推送已净化的增量文本。"""

    def __init__(self) -> None:
        self._raw: str = ""
        self._emitted_len: int = 0

    def feed(self, token: str) -> str:
        if not token:
            return ""
        self._raw += token
        if _has_incomplete_latex(self._raw):
            return ""
        sanitized = sanitize_latex_math(self._raw)
        delta = sanitized[self._emitted_len:]
        self._emitted_len = len(sanitized)
        return delta

    def flush(self) -> str:
        if not self._raw:
            return ""
        sanitized = sanitize_latex_math(self._raw)
        delta = sanitized[self._emitted_len:]
        self._emitted_len = len(sanitized)
        return delta

    @property
    def raw_text(self) -> str:
        return self._raw


_RELEASE_PHRASES: Tuple[str, ...] = (
    "无需审批",
    "不需要审批",
    "无须审批",
    "不用审批",
    "不必审批",
    "未超过",
    "不超过",
    "尚未超过",
    "没有超过",
    "未达",
    "未触及",
    "正常通过",
    "可以自行",
    "可自行",
    "无需提交",
    "不触发",
    "无需报备",
    "无需走审批",
    "可以直接",
)


def _to_yuan(value_str: str, unit: str = "") -> float:
    """将数值字符串与单位提示统一换算为元。"""
    value = float(value_str.replace(",", ""))
    unit_normalized = unit.strip().lower()
    if unit_normalized in {"万", "萬", "w"}:
        return value * 10000.0
    return value


def extract_monetary_amounts_yuan(text: str) -> List[float]:
    """
    从文本中提取所有金额并归一化为「元」。
    兼容：12万、12 万元、4500 元、120,000、120000 等写法。
    """
    if not text:
        return []

    amounts: List[float] = []
    seen_spans: List[Tuple[int, int]] = []

    def _record(match: re.Match[str], yuan_value: float) -> None:
        span = match.span()
        if any(not (span[1] <= start or span[0] >= end) for start, end in seen_spans):
            return
        seen_spans.append(span)
        amounts.append(yuan_value)

    for match in _WAN_AMOUNT_PATTERN.finditer(text):
        _record(match, _to_yuan(match.group(1), "万"))

    for match in _YUAN_AMOUNT_PATTERN.finditer(text):
        _record(match, _to_yuan(match.group(1), "元"))

    for match in _LARGE_PLAIN_AMOUNT_PATTERN.finditer(text):
        _record(match, _to_yuan(match.group(1), "元"))

    return amounts


def extract_threshold_amounts_yuan(text: str) -> List[float]:
    """
    从制度/检索文本中提取审批阈值金额（归一化为元）。
    仅匹配带有「超过/大于/红线/阈值/审批」等合规语境的片段。
    """
    if not text:
        return []

    thresholds: List[float] = []

    for match in _THRESHOLD_LEADING_PATTERN.finditer(text):
        thresholds.append(_to_yuan(match.group(1), match.group(2) or "元"))

    for match in _THRESHOLD_TRAILING_PATTERN.finditer(text):
        thresholds.append(_to_yuan(match.group(1), match.group(2) or "元"))

    return thresholds


def _contains_release_phrase(answer: str) -> bool:
    """检测回答中是否包含「无需审批 / 未超过 / 正常通过」等放行措辞。"""
    normalized = answer.replace(" ", "")
    return any(phrase in normalized for phrase in _RELEASE_PHRASES)


def query_indicates_zero_consumption(query: str) -> bool:
    """
    扫描用户提问，判断是否命中「未休/未使用/零消耗」等强烈零消费表述。

    命中时，后端安全垫将启用「禁止幻觉扣减」断言防御。
    """
    if not query:
        return False
    normalized = query.replace(" ", "")
    return any(keyword in normalized for keyword in _ZERO_CONSUMPTION_KEYWORDS)


def _chunk_text_from_retrieved(retrieved_chunks: List[Dict[str, Any]]) -> str:
    """将检索分块合并为单一文本，供正则提取使用。"""
    return "\n".join(str(chunk.get("text", "")) for chunk in retrieved_chunks)


def _has_day_quota_context(text: str, start: int, end: int, window: int = 40) -> bool:
    """判断匹配 span 前后窗口内是否包含天数额度相关语境词。"""
    snippet = text[max(0, start - window): min(len(text), end + window)]
    return any(keyword in snippet for keyword in _DAY_QUOTA_CONTEXT_KEYWORDS)


def extract_policy_day_baselines(text: str) -> List[float]:
    """
    从制度/检索文本中提取天数额度基准（年假/休假/带薪假等语境）。

    策略：
    1. 「X 天」且前后窗口含额度语境词；
    2. 「享受/享有 X 天」类 entitlement 句式。
    """
    if not text:
        return []

    baselines: List[float] = []
    seen: set[float] = set()

    for match in _DAY_QUOTA_PATTERN.finditer(text):
        if not _has_day_quota_context(text, match.start(), match.end()):
            continue
        value = float(match.group(1))
        if value not in seen:
            seen.add(value)
            baselines.append(value)

    for match in _DAY_ENTITLEMENT_PATTERN.finditer(text):
        value = float(match.group(1))
        if value not in seen:
            seen.add(value)
            baselines.append(value)

    return baselines


def extract_answer_conclusion_days(answer: str) -> List[float]:
    """
    从模型回答中提取「结论性天数」——与可休/剩余/享有等引导词绑定的数字。

    若未匹配到结论性表述，则回退为回答中所有「X 天」数字（保守拦截）。
    """
    if not answer:
        return []

    conclusion_days: List[float] = []
    for match in _ANSWER_CONCLUSION_DAY_PATTERN.finditer(answer):
        conclusion_days.append(float(match.group(1)))

    if conclusion_days:
        return conclusion_days

    return [float(match.group(1)) for match in _ANSWER_ANY_DAY_PATTERN.finditer(answer)]


def _infer_quota_label(query: str, chunk_text: str) -> str:
    """根据提问/资料语境推断额度类型标签，用于纠正文案。"""
    combined = (query + chunk_text).replace(" ", "")
    if "年假" in combined:
        return "年假"
    if "带薪" in combined:
        return "带薪假"
    if "调休" in combined:
        return "调休"
    if "病假" in combined:
        return "病假"
    return "假期"


def _infer_status_hint(query: str) -> str:
    """从用户提问中提取状态提示词，用于纠正文案。"""
    normalized = query.replace(" ", "")
    for keyword in _ZERO_CONSUMPTION_KEYWORDS:
        if keyword in normalized:
            return keyword
    return "未使用"


def _chunks_contain_deduction_evidence(chunk_text: str) -> bool:
    """
    检测参考资料中是否存在可用于扣减计算的明文依据。

    若资料本身未提及已休/扣减天数，则模型不得自行扣减。
    """
    if not chunk_text:
        return False
    return _DEDUCTION_EVIDENCE_PATTERN.search(chunk_text) is not None


def _extract_first_float(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text)
    if not match:
        return None
    return float(match.group(1))


def _extract_standard_hours_per_day(text: str) -> float:
    hours = _extract_first_float(_STANDARD_HOURS_PER_DAY_PATTERN, text)
    if hours and hours > 0:
        return hours
    return _DEFAULT_HOURS_PER_DAY


def _extract_pay_multiplier(text: str) -> float:
    multiplier = _extract_first_float(_PAY_MULTIPLIER_PATTERN, text)
    return multiplier if multiplier and multiplier > 0 else 1.0


def _query_involves_hourly_quantity(query: str) -> bool:
    normalized = query.replace(" ", "")
    if "小时" in normalized:
        return True
    return any(keyword in normalized for keyword in _HOURLY_QUANTITY_QUERY_KEYWORDS)


def _extract_overtime_hours(query: str) -> float | None:
    return _extract_first_float(_HOURLY_QUANTITY_PATTERN, query)


def _extract_answer_conclusion_amounts(answer: str) -> List[float]:
    if not answer:
        return []
    return [
        float(match.group(1))
        for match in _ANSWER_CONCLUSION_AMOUNT_PATTERN.finditer(answer)
    ]


def _amounts_close(left: float, right: float, rel_tol: float = 0.02) -> bool:
    if right == 0:
        return abs(left) < 0.01
    return abs(left - right) <= max(0.01, abs(right) * rel_tol)


def _format_calc_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def _answer_contains_hourly_normalization(answer: str, hours_per_day: float) -> bool:
    if re.search(r"小时工资", answer):
        return True
    hours_token = _format_calc_number(hours_per_day)
    if re.search(rf"(?:÷|/)\s*{re.escape(hours_token)}\b", answer):
        return True
    if hours_per_day == _DEFAULT_HOURS_PER_DAY and re.search(r"(?:÷|/)\s*8\b", answer):
        return True
    return False


def _detect_wrong_daily_to_hourly_calc(
    answer: str,
    daily_wage: float,
    multiplier: float,
    hours: float,
    hours_per_day: float,
) -> bool:
    """检测「日工资 × 倍数 × 小时数」未除以标准工时的错误算法。"""
    wrong_amount = daily_wage * multiplier * hours
    correct_amount = (daily_wage / hours_per_day) * multiplier * hours

    for amount in _extract_answer_conclusion_amounts(answer):
        if _amounts_close(amount, wrong_amount) and not _amounts_close(amount, correct_amount):
            return True

    if _answer_contains_hourly_normalization(answer, hours_per_day):
        return False

    for match in _WRONG_DAILY_TO_HOURLY_CALC_PATTERN.finditer(answer):
        wage, mult, qty = (float(match.group(i)) for i in range(1, 4))
        if (
            _amounts_close(wage, daily_wage)
            and _amounts_close(mult, multiplier)
            and _amounts_close(qty, hours)
        ):
            return True

    compact = answer.replace(" ", "")
    wrong_expr = (
        f"{_format_calc_number(daily_wage)}×{_format_calc_number(multiplier)}"
        f"×{_format_calc_number(hours)}"
    )
    wrong_expr_ascii = wrong_expr.replace("×", "*")
    if wrong_expr in compact or wrong_expr_ascii in compact:
        return True

    return False


def _build_daily_hourly_overtime_correction(
    daily_wage: float,
    multiplier: float,
    hours: float,
    hours_per_day: float,
    result_label: str,
) -> str:
    hourly_wage = daily_wage / hours_per_day
    correct_amount = hourly_wage * multiplier * hours
    wrong_amount = daily_wage * multiplier * hours
    steps_text = (
        f"1. 单位归一化：小时工资 = 日工资 ÷ {hours_per_day:g} = "
        f"{daily_wage:g} ÷ {hours_per_day:g} = {hourly_wage:g} 元/小时。\n"
        f"2. 计算{result_label}：{result_label} = 小时工资 × {multiplier:g} × 加班小时数 = "
        f"{hourly_wage:g} × {multiplier:g} × {hours:g} = {correct_amount:g} 元。\n"
        f"（错误算法「日工资 × 倍数 × 小时数 = {wrong_amount:g} 元」已作废。）"
    )
    conclusion = f"您加班 {hours:g} 小时，应得{result_label} {correct_amount:g} 元。"
    return UNIT_CONVERSION_CORRECTION_TEMPLATE.format(
        steps_text=steps_text,
        conclusion=conclusion,
    )


def _build_period_conversion_correction(
    base_amount: float,
    base_label: str,
    target_label: str,
    divisor: float,
    divisor_label: str,
    result_label: str,
) -> str:
    correct_amount = base_amount / divisor
    steps_text = (
        f"1. 单位归一化：{target_label} = {base_label} ÷ {divisor_label} = "
        f"{base_amount:g} ÷ {divisor:g} = {correct_amount:g} 元。\n"
        f"（错误算法「直接将{base_label}当作{target_label} = {base_amount:g} 元」已作废。）"
    )
    conclusion = f"{result_label}为 {correct_amount:g} 元。"
    return UNIT_CONVERSION_CORRECTION_TEMPLATE.format(
        steps_text=steps_text,
        conclusion=conclusion,
    )


def _validate_daily_wage_hourly_overtime(
    query: str,
    combined_text: str,
    llm_answer: str,
) -> Tuple[bool, str]:
    if not _query_involves_hourly_quantity(query):
        return False, ""

    overtime_hours = _extract_overtime_hours(query)
    if not overtime_hours or overtime_hours <= 0:
        return False, ""

    daily_wage = _extract_first_float(_DAILY_WAGE_PATTERN, combined_text)
    if not daily_wage or daily_wage <= 0:
        return False, ""

    hours_per_day = _extract_standard_hours_per_day(combined_text)
    multiplier = _extract_pay_multiplier(combined_text)

    if not _detect_wrong_daily_to_hourly_calc(
        llm_answer, daily_wage, multiplier, overtime_hours, hours_per_day,
    ):
        return False, ""

    normalized = combined_text.replace(" ", "")
    if "防暑" in normalized or "高温" in normalized:
        result_label = "防暑津贴"
    elif "加班" in normalized:
        result_label = "加班费"
    else:
        result_label = "费用"

    correction = _build_daily_hourly_overtime_correction(
        daily_wage, multiplier, overtime_hours, hours_per_day, result_label,
    )
    logger.warning(
        "[NumericalCompliance] 触发日薪→小时单位换算拦截 | daily=%.2f | mult=%.2f | "
        "hours=%.2f | hpd=%.2f | query=%r",
        daily_wage,
        multiplier,
        overtime_hours,
        hours_per_day,
        query[:120],
    )
    return True, correction


def _validate_monthly_to_daily_conversion(
    query: str,
    combined_text: str,
    llm_answer: str,
) -> Tuple[bool, str]:
    if not _DAILY_RATE_QUERY_PATTERN.search(query):
        return False, ""

    monthly_wage = _extract_first_float(_MONTHLY_WAGE_PATTERN, combined_text)
    if not monthly_wage or monthly_wage <= 0:
        return False, ""

    daily_wage_in_context = _extract_first_float(_DAILY_WAGE_PATTERN, combined_text)
    if daily_wage_in_context:
        return False, ""

    correct_amount = monthly_wage / _DEFAULT_DAYS_PER_MONTH
    wrong_amount = monthly_wage

    answer_amounts = _extract_answer_conclusion_amounts(llm_answer)
    if not answer_amounts:
        return False, ""

    if not any(
        _amounts_close(amount, wrong_amount) and not _amounts_close(amount, correct_amount)
        for amount in answer_amounts
    ):
        return False, ""

    correction = _build_period_conversion_correction(
        base_amount=monthly_wage,
        base_label="月薪",
        target_label="日工资",
        divisor=_DEFAULT_DAYS_PER_MONTH,
        divisor_label="21.75天",
        result_label="日工资",
    )
    logger.warning(
        "[NumericalCompliance] 触发月薪→日薪单位换算拦截 | monthly=%.2f | query=%r",
        monthly_wage,
        query[:120],
    )
    return True, correction


def _validate_yearly_to_monthly_conversion(
    query: str,
    combined_text: str,
    llm_answer: str,
) -> Tuple[bool, str]:
    if not _MONTHLY_RATE_QUERY_PATTERN.search(query):
        return False, ""

    yearly_wage = _extract_first_float(_YEARLY_WAGE_PATTERN, combined_text)
    if not yearly_wage or yearly_wage <= 0:
        return False, ""

    monthly_wage_in_context = _extract_first_float(_MONTHLY_WAGE_PATTERN, combined_text)
    if monthly_wage_in_context:
        return False, ""

    correct_amount = yearly_wage / _DEFAULT_MONTHS_PER_YEAR
    wrong_amount = yearly_wage

    answer_amounts = _extract_answer_conclusion_amounts(llm_answer)
    if not answer_amounts:
        return False, ""

    if not any(
        _amounts_close(amount, wrong_amount) and not _amounts_close(amount, correct_amount)
        for amount in answer_amounts
    ):
        return False, ""

    correction = _build_period_conversion_correction(
        base_amount=yearly_wage,
        base_label="年薪",
        target_label="月薪",
        divisor=_DEFAULT_MONTHS_PER_YEAR,
        divisor_label="12个月",
        result_label="月薪",
    )
    logger.warning(
        "[NumericalCompliance] 触发年薪→月薪单位换算拦截 | yearly=%.2f | query=%r",
        yearly_wage,
        query[:120],
    )
    return True, correction


def validate_unit_conversion(
    query: str,
    retrieved_chunks: List[Dict[str, Any]],
    llm_answer: str,
) -> Tuple[bool, str]:
    """
    拦截跨时间单位工资换算错误（如日薪直接乘加班小时、月薪当日薪等）。

    Returns:
        (should_intercept, replacement_message)
    """
    if not query or not llm_answer or not retrieved_chunks:
        return False, ""

    chunk_text = _chunk_text_from_retrieved(retrieved_chunks)
    combined_text = f"{chunk_text}\n{query}"

    for validator in (
        _validate_daily_wage_hourly_overtime,
        _validate_monthly_to_daily_conversion,
        _validate_yearly_to_monthly_conversion,
    ):
        intercepted, replacement = validator(query, combined_text, llm_answer)
        if intercepted:
            return True, replacement

    return False, ""


def validate_unauthorized_deduction(
    query: str,
    retrieved_chunks: List[Dict[str, Any]],
    llm_answer: str,
) -> Tuple[bool, str]:
    """
    拦截「用户明确未休/未使用，但模型擅自扣减额度」的幻觉回答。

    触发条件（全部满足）：
    1. 用户提问命中零消费关键词；
    2. 资料中存在可识别的天数额度基准；
    3. 资料中无扣减依据；
    4. 模型回答中的结论性天数 < 资料基准天数。

    Returns:
        (should_intercept, correction_suffix)
        - should_intercept=True 时，correction_suffix 为追加至流末尾的合规修正提示
        - should_intercept=False 时，correction_suffix 为空字符串
    """
    if not query or not llm_answer or not retrieved_chunks:
        return False, ""

    if not query_indicates_zero_consumption(query):
        return False, ""

    chunk_text = _chunk_text_from_retrieved(retrieved_chunks)
    baselines = extract_policy_day_baselines(chunk_text)
    if not baselines:
        return False, ""

    # 资料中若已有扣减依据，则允许模型引用资料做扣减，不拦截
    if _chunks_contain_deduction_evidence(chunk_text):
        return False, ""

    baseline_days = max(baselines)
    answer_days = extract_answer_conclusion_days(llm_answer)
    if not answer_days:
        return False, ""

    # 任一结论性天数低于基准且不为 0（0 通常表示「已休 0 天」，非最终额度）
    reduced_days = [
        day for day in answer_days
        if 0 < day < baseline_days
    ]
    if not reduced_days:
        return False, ""

    quota_label = _infer_quota_label(query, chunk_text)
    status_hint = _infer_status_hint(query)
    correction = UNAUTHORIZED_DEDUCTION_CORRECTION_TEMPLATE.format(
        status_hint=status_hint,
        baseline_days=baseline_days,
        quota_label=quota_label,
    )

    logger.warning(
        "[NumericalCompliance] 触发幻觉扣减拦截 | baseline=%.1f天 | answer_days=%s | "
        "query=%r",
        baseline_days,
        reduced_days,
        query[:120],
    )
    return True, correction


def validate_numerical_compliance(
    query: str,
    retrieved_chunks: List[Dict[str, Any]],
    llm_answer: str,
) -> Tuple[bool, str, str]:
    """
    纯 Python 数值合规安全垫（流尾钩子专用）。

    覆盖三类业务事故：
    A. 金额审批：申请金额已超标但模型仍给出「无需审批/未超过」等放行结论；
    B. 天数额度：用户明确未休/未使用，但模型擅自扣减制度规定的总额度；
    C. 工资单位：跨日/月/年/小时换算错误（如日薪直接乘加班小时数）。

    Args:
        query: 用户原始提问
        retrieved_chunks: 混合检索返回的知识库分块
        llm_answer: 大模型完整回答（流式拼接后的全文）

    Returns:
        (should_intercept, append_suffix, replacement_message)
        - should_intercept=False：三者均空/原样，无需追加或替换
        - 金额拦截：append_suffix=""，replacement_message=金额纠正全文（替换展示）
        - 扣减拦截：append_suffix=合规修正提示（追加至流末尾），replacement_message=""
        - 单位换算拦截：append_suffix=""，replacement_message=换算纠正全文（替换落库）
    """
    if not query or not llm_answer or not retrieved_chunks:
        return False, "", ""

    # ── B. 未休状态下幻觉扣减（追加修正提示，保留原流内容） ──
    deduction_intercepted, deduction_suffix = validate_unauthorized_deduction(
        query, retrieved_chunks, llm_answer,
    )
    if deduction_intercepted:
        return True, deduction_suffix, ""

    # ── C. 工资跨单位换算错误（整段替换为纠正文案） ──
    unit_intercepted, unit_replacement = validate_unit_conversion(
        query, retrieved_chunks, llm_answer,
    )
    if unit_intercepted:
        return True, "", unit_replacement

    # ── A. 金额超标仍放行（整段替换为纠正文案） ──
    query_amounts = extract_monetary_amounts_yuan(query)
    if not query_amounts:
        return False, "", ""

    chunk_text = _chunk_text_from_retrieved(retrieved_chunks)
    threshold_amounts = extract_threshold_amounts_yuan(chunk_text)
    if not threshold_amounts:
        return False, "", ""

    if not _contains_release_phrase(llm_answer):
        return False, "", ""

    query_amount = max(query_amounts)
    threshold_amount = min(threshold_amounts)

    if query_amount > threshold_amount:
        logger.warning(
            "[NumericalCompliance] 触发金额红线拦截 | query=%.2f元 | threshold=%.2f元 | "
            "query_text=%r",
            query_amount,
            threshold_amount,
            query[:120],
        )
        return True, "", NUMERICAL_COMPLIANCE_CORRECTION

    return False, "", ""


async def stream_ollama_generate(prompt: str) -> AsyncIterator[str]:
    """
    异步流式请求 Ollama /api/generate 接口，逐 token 产出文本片段。

    Args:
        prompt: 完整 RAG Prompt 文本

    Yields:
        每次 yield 一个 token 片段（由 Ollama 返回的 response 字段）

    Raises:
        OllamaError: 网络超时、HTTP 错误或响应解析失败时抛出
    """
    payload = {
        "model": settings.OLLAMA_CHAT_MODEL,
        "prompt": prompt,
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.OLLAMA_GENERATE_TIMEOUT) as client:
            async with client.stream(
                "POST",
                settings.OLLAMA_GENERATE_URL,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning("[Ollama] 无法解析流式响应行: %s", line)
                        raise OllamaError("大模型服务响应超时") from exc

                    token: str = data.get("response", "")
                    if token:
                        yield token

                    if data.get("done"):
                        break
    except httpx.TimeoutException as exc:
        logger.exception("[Ollama] 流式生成超时: %s", exc)
        raise OllamaError("大模型服务响应超时") from exc
    except httpx.HTTPError as exc:
        logger.exception("[Ollama] 流式生成 HTTP 错误: %s", exc)
        raise OllamaError("大模型服务响应超时") from exc
    except OllamaError:
        raise
    except Exception as exc:
        logger.exception("[Ollama] 流式生成未知错误: %s", exc)
        raise OllamaError("大模型服务响应超时") from exc
