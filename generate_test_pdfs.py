#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced RAG 精排（Reranker）测试数据集 PDF 生成脚本。

执行后在 ./test_datasets/ 目录下生成 04~09 共 6 个精简版测试 PDF，
用于评估 Reranker 在数字陷阱、同义替换、表文混合、跨文档矛盾、
长距关联及长尾密集文本等场景下的精排能力。

依赖：reportlab
"""

import os
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# 全局初始化
# ---------------------------------------------------------------------------
os.makedirs("./test_datasets", exist_ok=True)

# 注册中文字体（内置 CID 字体，无需外部 ttf）
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

OUTPUT_DIR = "./test_datasets"
PAGE_SIZE = A4
MARGIN = 2 * cm


def _base_styles():
    """构建文档通用段落样式。"""
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ChineseTitle",
            fontName="STSong-Light",
            fontSize=16,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ChineseHeading",
            fontName="STSong-Light",
            fontSize=13,
            leading=18,
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ChineseBody",
            fontName="STSong-Light",
            fontSize=10.5,
            leading=16,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ChineseBodyLeft",
            fontName="STSong-Light",
            fontSize=10.5,
            leading=16,
            alignment=TA_LEFT,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            fontName="STSong-Light",
            fontSize=9,
            leading=13,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableHeader",
            fontName="STSong-Light",
            fontSize=9,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.white,
        )
    )
    return styles


def _p(text: str, style) -> Paragraph:
    """快捷创建 Paragraph。"""
    return Paragraph(text, style)


def _table_cell(text: str, styles, header: bool = False) -> Paragraph:
    """Table 单元格专用：中文必须包裹在 Paragraph 中。"""
    st = styles["TableHeader"] if header else styles["TableCell"]
    return Paragraph(text, st)


def _build_table(rows, col_widths, styles) -> Table:
    """构建带 Paragraph 单元格的标准表格。"""
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return tbl


def _save_pdf(filename: str, story: list) -> None:
    """写入 PDF 文件。"""
    path = os.path.join(OUTPUT_DIR, filename)
    doc = SimpleDocTemplate(
        path,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )
    doc.build(story)
    print(f"  已生成: {path}")


# ---------------------------------------------------------------------------
# 04 — 伺服电机选型手册（数字陷阱）
# ---------------------------------------------------------------------------
def generate_04_product_servo_motor():
    styles = _base_styles()
    story = []

    story.append(_p("SM 系列伺服电机选型手册（节选）", styles["ChineseTitle"]))
    story.append(_p("文档编号：SM-MANUAL-2025-04　版本：V2.3", styles["ChineseBodyLeft"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(_p("第1章　产品概述", styles["ChineseHeading"]))
    story.append(
        _p(
            "SM 系列交流伺服电机面向数控机床、工业机器人及精密装配产线，"
            "具备高响应、低惯量、宽调速比等特点。本手册以型号 SM-080-A 为典型负载案例，"
            "说明理论计算与实测修正两套扭矩数据的适用场景。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("第2章　理论计算扭矩", styles["ChineseHeading"]))
    story.append(
        _p(
            "针对负载型号 <b>SM-080-A</b>，在额定转速 3000 r/min、"
            "环境温度 25℃、连续 duty 工况下，依据电机常数与负载惯量比公式，"
            "经工程计算得出：<b>理论计算扭矩为 12.5 N·m</b>。"
            "该数值适用于初步选型与仿真验证阶段，未计入现场传动损耗与温升修正。",
            styles["ChineseBody"],
        )
    )

    spec_rows = [
        [
            _table_cell("参数项", styles, header=True),
            _table_cell("SM-080-A 规格", styles, header=True),
            _table_cell("备注", styles, header=True),
        ],
        [
            _table_cell("额定功率", styles),
            _table_cell("3.0 kW", styles),
            _table_cell("S1 连续工作制", styles),
        ],
        [
            _table_cell("理论计算扭矩", styles),
            _table_cell("12.5 N·m", styles),
            _table_cell("第2章公式推导", styles),
        ],
        [
            _table_cell("额定转速", styles),
            _table_cell("3000 r/min", styles),
            _table_cell("—", styles),
        ],
    ]
    story.append(_build_table(spec_rows, [4 * cm, 4 * cm, 6 * cm], styles))
    story.append(Spacer(1, 0.4 * cm))

    story.append(_p("第3章　安装与调试要点", styles["ChineseHeading"]))
    story.append(
        _p(
            "安装时应保证联轴器同轴度不大于 0.05 mm，电缆屏蔽层单端接地。"
            "上电前须核对驱动器参数与电机铭牌编码一致，避免错配导致过流保护。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("第4章　实测修正与过载保护", styles["ChineseHeading"]))
    story.append(
        _p(
            "经产线带载实测（含减速机效率、皮带张紧及散热条件），"
            "对型号 <b>SM-080-A</b> 进行修正：<b>实测修正扭矩为 14.2 N·m</b>。"
            "当负载峰值超过该值时，驱动器将触发过载保护并记录故障码 E-021。"
            "<b>最终选型请以实测修正值为准</b>，理论计算值 12.5 N·m 仅作参考，"
            "不得作为采购合同中的性能验收依据。",
            styles["ChineseBody"],
        )
    )

    _save_pdf("04-product-servo-motor.pdf", story)


# ---------------------------------------------------------------------------
# 05 — Q3 预算执行分析（千分位数字 + 表文混合）
# ---------------------------------------------------------------------------
def generate_05_financial_budget_q3():
    styles = _base_styles()
    story = []

    story.append(_p("2025 年第三季度预算执行分析报告", styles["ChineseTitle"]))
    story.append(_p("编制部门：财务管理部　报告期：2025-Q3", styles["ChineseBodyLeft"]))
    story.append(Spacer(1, 0.3 * cm))

    pre_analysis = (
        "本报告对 2025 年第三季度智能制造产线升级专项的执行情况进行汇总分析。"
        "经集团预算委员会批复，本专项第三季度正式<b>预算批复金额为 ￥12,345,000.00</b>，"
        "涵盖设备采购、安装调试、人员培训及质保金预留等科目。"
        "批复文件编号 FIN-BUD-2025-Q3-001 已于 7 月 1 日生效，"
        "各成本中心须在批复额度内按月度计划有序支出，"
        "超支部分需另行提交追加申请并经 CFO 联签后方可动用。"
        "以下从科目维度、供应商分布及执行进度三方面展开说明，"
        "供管理层审阅与四季度滚动预测参考。"
    )
    story.append(_p(pre_analysis, styles["ChineseBody"]))

    budget_rows = [
        [
            _table_cell("成本中心", styles, header=True),
            _table_cell("预算科目", styles, header=True),
            _table_cell("批复金额（元）", styles, header=True),
            _table_cell("本季执行（元）", styles, header=True),
            _table_cell("执行率", styles, header=True),
            _table_cell("差异说明", styles, header=True),
        ],
        [
            _table_cell("CC-101 产线一部", styles),
            _table_cell("设备采购", styles),
            _table_cell("￥8,200,000.00", styles),
            _table_cell("￥7,950,000.00", styles),
            _table_cell("96.95%", styles),
            _table_cell("部分设备延期到货", styles),
        ],
        [
            _table_cell("CC-102 产线二部", styles),
            _table_cell("安装调试", styles),
            _table_cell("￥2,500,000.00", styles),
            _table_cell("￥2,380,000.00", styles),
            _table_cell("95.20%", styles),
            _table_cell("—", styles),
        ],
        [
            _table_cell("CC-103 培训中心", styles),
            _table_cell("人员培训", styles),
            _table_cell("￥950,000.00", styles),
            _table_cell("￥920,000.00", styles),
            _table_cell("96.84%", styles),
            _table_cell("—", styles),
        ],
        [
            _table_cell("CC-104 质保预留", styles),
            _table_cell("质保金", styles),
            _table_cell("￥695,000.00", styles),
            _table_cell("￥730,000.00", styles),
            _table_cell("105.04%", styles),
            _table_cell("提前支付部分质保", styles),
        ],
        [
            _table_cell("合计", styles),
            _table_cell("—", styles),
            _table_cell("￥12,345,000.00", styles),
            _table_cell("￥11,980,000.00", styles),
            _table_cell("97.04%", styles),
            _table_cell("实际执行支出汇总", styles),
        ],
    ]
    story.append(_build_table(budget_rows, [2.8 * cm, 2.5 * cm, 3 * cm, 3 * cm, 1.8 * cm, 3.2 * cm], styles))
    story.append(Spacer(1, 0.4 * cm))

    post_analysis = (
        "从执行汇总表可见，第三季度各成本中心合计<b>实际执行支出为 ￥11,980,000.00</b>，"
        "较批复总额节约 ￥365,000.00，整体执行率 97.04%。"
        "设备采购与安装调试基本按计划推进，质保金科目因供应商要求略有提前支付，"
        "导致该科目执行率略超 100%。"
        "财务建议四季度重点关注 CC-101 延期到货设备的验收入账时点，"
        "并同步更新全年现金流预测模型。"
        "本报告数据已与 ERP 总账模块对账一致，差异项已在附表二中逐项说明。"
    )
    story.append(_p(post_analysis, styles["ChineseBody"]))

    _save_pdf("05-financial-budget-q3.pdf", story)


# ---------------------------------------------------------------------------
# 06 — 考勤与休假制度（同义异词）
# ---------------------------------------------------------------------------
def generate_06_hr_attendance_normal():
    styles = _base_styles()
    story = []

    story.append(_p("考勤与休假管理制度", styles["ChineseTitle"]))
    story.append(_p("文件编号：HR-POL-2025-06　生效日期：2025-01-01", styles["ChineseBodyLeft"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(_p("第1章　总则", styles["ChineseHeading"]))
    story.append(
        _p(
            "为规范员工出勤与休假行为，保障生产秩序与员工合法权益，特制定本制度。"
            "员工申请年假、事假、病假等休假类型时，须按本章及后续章节规定的流程提交申请。"
            "休假审批流程的第一受理单位为<b>人力资源中心</b>，"
            "该中心负责初审材料完整性并在两个工作日内给出初审意见。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("第2章　考勤管理", styles["ChineseHeading"]))
    story.append(
        _p(
            "标准工时制员工每日打卡四次，弹性工时制员工按部门备案方案执行。"
            "迟到、早退、旷工的处理标准见附表一。因公务外出须提前在 OA 系统登记，"
            "未经登记视为缺勤。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("第3章　年假管理", styles["ChineseHeading"]))
    story.append(
        _p(
            "员工依法享受带薪年休假。年假天数按司龄阶梯计算，具体标准见下表。"
            "员工提交年假申请后，由直属主管审批，再流转至<b>HR部门</b>备案。"
            "HR部门在备案环节核对司龄与剩余额度，确认无误后生效。",
            styles["ChineseBody"],
        )
    )

    leave_rows = [
        [
            _table_cell("司龄区间", styles, header=True),
            _table_cell("年假天数（工作日）", styles, header=True),
            _table_cell("备注", styles, header=True),
        ],
        [
            _table_cell("1—5 年（含 5 年）", styles),
            _table_cell("5 天", styles),
            _table_cell("按自然年计算", styles),
        ],
        [
            _table_cell("5—10 年（含 10 年）", styles),
            _table_cell("10 天", styles),
            _table_cell("含第 5 周年当日", styles),
        ],
        [
            _table_cell("10 年以上", styles),
            _table_cell("15 天", styles),
            _table_cell("上限 15 天，不累计至下年", styles),
        ],
    ]
    story.append(_build_table(leave_rows, [4.5 * cm, 4.5 * cm, 5.5 * cm], styles))
    story.append(Spacer(1, 0.4 * cm))

    story.append(_p("第4章　事假与病假", styles["ChineseHeading"]))
    story.append(
        _p(
            "事假须提前申请，病假须于返岗后三日内补交医疗机构证明。"
            "连续事假超过 15 天或累计超过 30 天的，按劳动合同及公司规章处理。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("第5章　审批权限与归档", styles["ChineseHeading"]))
    story.append(
        _p(
            "部门经理可批准 3 天以内（含）的各类休假；超过 3 天的须报分管领导审批。"
            "所有审批完成的休假单由<b>人资部</b>统一归档，保存期限不少于三年。"
            "人资部每月出具考勤异常报表，与薪酬核算系统对接。",
            styles["ChineseBody"],
        )
    )

    _save_pdf("06-hr-attendance-normal.pdf", story)


# ---------------------------------------------------------------------------
# 07 — 智能产线采购合同（长距离关联）
# ---------------------------------------------------------------------------
def generate_07_contract_project_alpha():
    styles = _base_styles()
    story = []

    story.append(_p("XX 智能产线项目设备采购合同（脱敏）", styles["ChineseTitle"]))
    story.append(_p("合同编号：CT-2025-ALPHA-09", styles["ChineseBodyLeft"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(_p("第1条　付款里程碑（含验收款条件）", styles["ChineseHeading"]))
    story.append(
        _p(
            "1.1 预付款：合同生效后 10 个工作日内，甲方向乙方支付合同总价 30%。<br/>"
            "1.2 到货款：设备运抵甲方现场并经开箱检验合格后 15 个工作日内，支付 40%。<br/>"
            "1.3 验收款：产线完成安装调试，且满足本合同约定的最终验收标准后，"
            "甲方向乙方支付合同总价 25%。<br/>"
            "1.4 质保金：剩余 5% 作为质保金，质保期满且无未决质量争议后无息支付。",
            styles["ChineseBody"],
        )
    )

    milestone_rows = [
        [
            _table_cell("里程碑", styles, header=True),
            _table_cell("比例", styles, header=True),
            _table_cell("触发条件", styles, header=True),
        ],
        [
            _table_cell("预付款", styles),
            _table_cell("30%", styles),
            _table_cell("合同生效", styles),
        ],
        [
            _table_cell("到货款", styles),
            _table_cell("40%", styles),
            _table_cell("开箱检验合格", styles),
        ],
        [
            _table_cell("验收款", styles),
            _table_cell("25%", styles),
            _table_cell("满足最终验收标准", styles),
        ],
        [
            _table_cell("质保金", styles),
            _table_cell("5%", styles),
            _table_cell("质保期满无争议", styles),
        ],
    ]
    story.append(_build_table(milestone_rows, [3.5 * cm, 2.5 * cm, 8.5 * cm], styles))
    story.append(Spacer(1, 0.4 * cm))

    # 中间填充约 400 字法务通用条款
    story.append(_p("第2条　一般条款", styles["ChineseHeading"]))
    legal_block = (
        "2.1 本合同受中华人民共和国法律管辖。因本合同引起的争议，"
        "双方应友好协商；协商不成的，提交甲方所在地有管辖权的人民法院诉讼解决。"
        "2.2 未经对方书面同意，任何一方不得转让本合同项下的权利或义务。"
        "2.3 本合同附件与正文具有同等法律效力；附件与正文冲突时，以正文为准，"
        "正文未约定事项以附件为准。2.4 不可抗力事件持续超过 90 日的，"
        "任何一方有权书面通知对方终止合同，已履行部分按实际进度结算，"
        "未履行部分互不承担违约责任。2.5 乙方保证所供设备不侵犯任何第三方知识产权，"
        "若发生侵权指控，乙方应自费应诉并赔偿甲方因此遭受的直接损失。"
        "2.6 保密义务自双方接触之日起至合同终止后五年内持续有效，"
        "披露方标注为保密的信息，接收方不得向无关第三方泄露。"
        "2.7 本合同一式四份，甲乙双方各执两份，自双方法定代表人或授权代表签字并加盖公章之日起生效。"
    )
    story.append(_p(legal_block, styles["ChineseBody"]))

    story.append(_p("第3条　知识产权与数据", styles["ChineseHeading"]))
    story.append(
        _p(
            "项目实施过程中产生的工艺改进专利，归属按补充协议约定。"
            "乙方不得将甲方提供的生产数据用于合同约定以外的用途。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("第4条　保险与运输", styles["ChineseHeading"]))
    story.append(
        _p(
            "设备运输由乙方负责，运输保险由乙方投保，保额不低于合同总价。"
            "货到甲方指定现场后，风险转移至甲方，但所有权保留至验收款支付完毕。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("第5条　违约责任", styles["ChineseHeading"]))
    story.append(
        _p(
            "乙方延迟交货每逾期一日，按迟交设备价款万分之五向甲方支付违约金，"
            "上限不超过迟交部分价款的 10%。甲方无正当理由延迟付款的，"
            "按同期 LPR 向乙方支付逾期利息。",
            styles["ChineseBody"],
        )
    )

    story.append(PageBreak())

    story.append(_p("第6条　质保与维护", styles["ChineseHeading"]))
    story.append(
        _p(
            "质保期为最终验收合格之日起 12 个月。质保期内非人为损坏的故障，"
            "乙方应在 48 小时内响应，5 个工作日内修复或更换。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("第7条　培训与文档", styles["ChineseHeading"]))
    story.append(
        _p(
            "乙方须提供不少于 40 人时的操作与维护培训，并交付中文操作手册、"
            "电气原理图及备件清单电子版各一套。",
            styles["ChineseBody"],
        )
    )

    story.append(PageBreak())

    # 最终验收标准放在文档末尾（第3页）
    story.append(_p("第8条　最终验收标准", styles["ChineseHeading"]))
    story.append(
        _p(
            "8.1 产线完成安装调试后，须进入试运行阶段。"
            "<b>最终验收标准：设备须连续无故障运行 30 天</b>，"
            "期间不得出现导致产线停机的重大故障（定义见技术附件 A）。"
            "8.2 试运行期间每日运行记录由双方共同签字确认。"
            "8.3 满足上述条件后，甲方组织正式验收，验收合格后触发验收款支付条件。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("第9条　合同附件清单", styles["ChineseHeading"]))
    story.append(
        _p(
            "附件 A：技术规格书；附件 B：设备清单及报价；附件 C：安装调试方案。",
            styles["ChineseBody"],
        )
    )

    _save_pdf("07-contract-project-alpha.pdf", story)


# ---------------------------------------------------------------------------
# 08 — Delta 项目结项总结（跨文档矛盾）
# ---------------------------------------------------------------------------
def generate_08_project_summary_delta():
    styles = _base_styles()
    story = []

    story.append(_p("Delta 智能产线项目结项总结报告", styles["ChineseTitle"]))
    story.append(_p("项目代号：DELTA-2025　编制日期：2025-11-30", styles["ChineseBodyLeft"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(_p("一、项目背景", styles["ChineseHeading"]))
    story.append(
        _p(
            "Delta 项目为 XX 智能产线升级的重要组成部分，主要设备采购依据合同 "
            "<b>CT-2025-ALPHA-09</b>（详见归档文件 "
            "<b>07-contract-project-alpha.pdf</b>）执行。"
            "项目于 2025 年 3 月启动，计划 9 月底完成终验。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("二、实施过程概述", styles["ChineseHeading"]))
    story.append(
        _p(
            "设备到货到货、安装调试均按里程碑推进，预付款与到货款已按期支付。"
            "试运行阶段自 10 月 1 日开始，累计记录运行 28 天，期间发生主轴报警 3 次，"
            "其中 2 次导致产线停机超过 4 小时。",
            styles["ChineseBody"],
        )
    )

    story.append(_p("三、技术指标对照", styles["ChineseHeading"]))
    metric_rows = [
        [
            _table_cell("指标项", styles, header=True),
            _table_cell("合同要求", styles, header=True),
            _table_cell("实测结果", styles, header=True),
            _table_cell("判定", styles, header=True),
        ],
        [
            _table_cell("主轴重复定位精度", styles),
            _table_cell("±0.005 mm", styles),
            _table_cell("±0.012 mm", styles),
            _table_cell("不合格", styles),
        ],
        [
            _table_cell("连续无故障运行", styles),
            _table_cell("30 天", styles),
            _table_cell("未达成", styles),
            _table_cell("不合格", styles),
        ],
        [
            _table_cell("产能达标率", styles),
            _table_cell("≥95%", styles),
            _table_cell("97.2%", styles),
            _table_cell("合格", styles),
        ],
    ]
    story.append(_build_table(metric_rows, [4 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm], styles))
    story.append(Spacer(1, 0.4 * cm))

    story.append(_p("四、结论与建议", styles["ChineseHeading"]))
    story.append(
        _p(
            "综合试运行数据与第三方检测报告，<b>因主轴重复定位精度未达合同第 8 条规定，"
            "项目最终未通过验收，拒绝支付尾款并终止结算。</b>"
            "建议采购部门启动合同违约条款评估，并另行组织招采以替换关键主轴单元。"
            "本报告已抄送财务管理部、法务部及供应商项目组。",
            styles["ChineseBody"],
        )
    )

    _save_pdf("08-project-summary-delta.pdf", story)


# ---------------------------------------------------------------------------
# 09 — 生产安全事故应急处置 FAQ（长尾密集文本）
# ---------------------------------------------------------------------------
def generate_09_ops_emergency_dense():
    styles = _base_styles()
    story = []

    story.append(_p("生产安全事故应急处置 FAQ", styles["ChineseTitle"]))
    story.append(_p("文档编号：OPS-FAQ-2025-09　适用：全体生产及运维人员", styles["ChineseBodyLeft"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(_p("Q1：发生灼烫伤或机械伤害时应如何启动应急响应？", styles["ChineseHeading"]))

    # 超过 400 字、无换行无分段的密集纯文本
    dense_text = (
        "根据《中华人民共和国安全生产法》及公司《生产安全事故报告和调查处理规定》，"
        "当现场发生灼烫伤或机械伤害事故时，第一发现人须立即按下就近急停按钮并切断相关设备动力源，"
        "同时通过车间广播或对讲系统向班组长及当班安全员发出一级警报，"
        "任何在场人员不得擅自移动伤者除非存在二次伤害风险如设备继续运转或有毒气体泄漏，"
        "班组长应在三分钟内完成初步伤情判断并拨打内部急救专线8001及120外部急救电话，"
        "安全员须在五分钟内到达事故现场设置警戒区并保护现场原始状态包括设备运行参数截图与监控录像封存，"
        "车间主任作为现场应急指挥第一责任人须组织未受伤人员按疏散路线图撤离至指定集合点并完成点名，"
        "若事故涉及机械卷入则严禁非专业人员使用切割工具施救必须等待专业救援队伍，"
        "对于灼烫伤伤者应使用流动清洁冷水持续冲洗伤处不少于15分钟但不得强行剥离已与创面粘连的衣物，"
        "事故发生后一小时内须向公司EHS部门及所在地应急管理部门完成初报，"
        "迟报瞒报漏报将依据安全生产法第九十一条及公司纪律处分条例对直接责任人与管理责任人进行责任追究，"
        "包括但不限于一票否决年度安全绩效、经济赔偿、调离岗位直至解除劳动合同，"
        "构成刑事犯罪的依法移送司法机关，"
        "应急响应链依次为现场第一发现人、班组长、车间主任、分厂EHS专员、公司安全总监及总经理，"
        "每一层级须在规定的响应时限内完成信息传递与处置决策并留存书面或电子记录以备事故调查与工伤保险理赔，"
        "事故调查组应在事故发生后24小时内成立并在72小时内提交初步原因分析报告，"
        "整改措施未闭环前相关产线不得恢复生产。"
    )
    # 使用无 leading 额外空白的紧凑样式，保持单段落
    dense_style = ParagraphStyle(
        name="DenseNoBreak",
        fontName="STSong-Light",
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=10,
    )
    story.append(Paragraph(dense_text, dense_style))

    story.append(_p("Q2：各类事故应急处置操作一览表", styles["ChineseHeading"]))

    emergency_rows = [
        [
            _table_cell("事故类型", styles, header=True),
            _table_cell("处置步骤", styles, header=True),
            _table_cell("责任人", styles, header=True),
        ],
        [
            _table_cell("灼烫伤", styles),
            _table_cell("急停→冲洗→包扎→送医→报告", styles),
            _table_cell("班组长 / 安全员", styles),
        ],
        [
            _table_cell("机械伤害", styles),
            _table_cell("急停→警戒→专业救援→保护现场→报告", styles),
            _table_cell("车间主任 / EHS专员", styles),
        ],
        [
            _table_cell("触电", styles),
            _table_cell("断电→心肺复苏→120→隔离电源→调查", styles),
            _table_cell("电工 / 安全总监", styles),
        ],
        [
            _table_cell("火灾", styles),
            _table_cell("报警→疏散→灭火→清点→配合调查", styles),
            _table_cell("消防联络员 / 总经理", styles),
        ],
    ]
    story.append(_build_table(emergency_rows, [3.5 * cm, 7 * cm, 4 * cm], styles))

    story.append(Spacer(1, 0.4 * cm))
    story.append(
        _p(
            "注：本 FAQ 为现场快速查阅版本，详细流程以《生产安全事故应急预案》正文为准。",
            styles["ChineseBodyLeft"],
        )
    )

    _save_pdf("09-ops-emergency-dense.pdf", story)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main():
    # Windows 控制台默认 GBK，确保 emoji 成功消息可正常输出
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("开始生成 Advanced RAG 精排测试 PDF …")
    generate_04_product_servo_motor()
    generate_05_financial_budget_q3()
    generate_06_hr_attendance_normal()
    generate_07_contract_project_alpha()
    generate_08_project_summary_delta()
    generate_09_ops_emergency_dense()
    print("✅ 6个精简版精排测试集PDF生成完毕！")


if __name__ == "__main__":
    main()
