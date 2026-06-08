"""
HTML邮件渲染引擎（公共模块）

将结构化文本内容渲染为精美的响应式HTML邮件，支持移动端和桌面端。

职责：文本 → HTML 渲染（纯渲染，不依赖SMTP、不依赖业务数据）
可被策略报告、可转债提醒等任意场景复用。

用法：
    from src.common.html_engine import render_email_html

    html = render_email_html(
        content="【每日一言】\\n\\n💡 投资有风险...\\n\\n【策略配置】\\n...",
        title="【Marcus策略小助手】",
        variant="responsive"  # 或 "mobile"
    )
"""

from __future__ import annotations

import re
import html as html_mod
from datetime import datetime
from typing import Dict, Optional, List


# ══════════════════════════════════════════════════════════════
# 章节渐变色/边框映射（可扩展）
# ══════════════════════════════════════════════════════════════

TITLE_GRADIENT_MAP: Dict[str, str] = {
    '每日一言': 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
    '财经动态': 'linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%)',
    '策略配置': 'linear-gradient(135deg, #D1FAE5 0%, #A7F3D0 100%)',
    '标的池': 'linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)',
    '操作建议': 'linear-gradient(135deg, #FCE7F3 0%, #FBCFE8 100%)',
    '今日总结': 'linear-gradient(135deg, #E0E7FF 0%, #C7D2FE 100%)',
}

BORDER_COLOR_MAP: Dict[str, str] = {
    '每日一言': '#F59E0B',
    '财经动态': '#3B82F6',
    '策略配置': '#10B981',
    '建议操作-胜率排行Top5': '#EC4899',
    '策略命中TOP15': '#4F46E5',
    '今日总结': '#6366F1',
    '风险&提示': '#EF4444',
}

# 表格头检测关键词
TABLE_HEADER_KEYWORDS = ('标的', '代码', '名称', '评分', '评级', '转债', '申购', '状态')


# ══════════════════════════════════════════════════════════════
# 核心渲染函数
# ══════════════════════════════════════════════════════════════

def render_email_html(
    content: str,
    title: str = "【Marcus策略小助手】",
    variant: str = "responsive",
    date_str: Optional[str] = None,
) -> str:
    """
    将文本内容渲染为HTML邮件

    Args:
        content: 原始文本内容（多行字符串）
        title: 邮件标题
        variant: 渲染变体 — "responsive"（响应式，默认）或 "mobile"（仅移动端优化）
        date_str: 生成时间文本，不传则自动取当前时间

    Returns:
        HTML格式的邮件内容
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y年%m月%d日 %H:%M')

    content_html = _render_body(content, variant=variant)
    return _wrap_html_page(content_html, title, date_str, variant=variant)


def _render_body(content: str, variant: str = "responsive") -> str:
    """文本 → HTML body 主体渲染"""
    lines = content.split('\n')
    html_parts: List[str] = []
    in_list = False
    in_table = False

    for line in lines:
        line = line.strip()

        # 保护已有 HTML 标签不被 escape
        saved_tags: List[str] = []

        def _save(m: re.Match) -> str:
            saved_tags.append(m.group(0))
            return f'\x00TAG{len(saved_tags) - 1}\x00'

        line = re.sub(r'<[^>]+>', _save, line)
        line = html_mod.escape(line)
        for idx, tag in enumerate(saved_tags):
            line = line.replace(f'\x00TAG{idx}\x00', tag)

        # ── 空行 ──
        if not line:
            if in_table:
                html_parts.append('</tbody></table>')
                in_table = False
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append('<div style="height: 8px;"></div>')
            continue

        # ── Markdown 表格分隔行 ──
        if line.startswith('---') and '|' in line:
            continue

        # ── 分隔线 ──
        if line.startswith('==') or line.startswith('━━') or line.startswith('---'):
            if in_table:
                html_parts.append('</tbody></table>')
                in_table = False
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append('<hr style="border: none; border-top: 2px solid #4F46E5; margin: 16px 0; opacity: 0.3;">')
            continue

        # ── 主标题 【xxx】 ──
        if line.startswith('【') and line.endswith('】'):
            if in_table:
                html_parts.append('</tbody></table>')
                in_table = False
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            title_text = line.strip('【】')
            bg = TITLE_GRADIENT_MAP.get(title_text, 'linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)')
            border = BORDER_COLOR_MAP.get(title_text, '#4F46E5')
            html_parts.append(
                f'<h3 style="color: #1E293B; margin: 20px 0 12px 0; padding: 12px 16px; '
                f'background: {bg}; border-radius: 8px; font-size: 16px; font-weight: 600; '
                f'border-left: 4px solid {border}; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">{line}</h3>'
            )
            continue

        # ── 子标题 ## xxx ──
        if line.startswith('## '):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(
                f'<h4 style="color: #334155; margin: 16px 0 8px 0; font-size: 15px; font-weight: 600;">'
                f'📊 {line[3:]}</h4>'
            )
            continue

        # ── 列表项 ──
        if line.startswith('• ') or line.startswith('- ') or line.startswith('* '):
            if not in_list:
                html_parts.append(
                    '<ul style="margin: 8px 0; padding-left: 20px; list-style-type: none;">'
                )
                in_list = True
            item = line[2:].strip()
            html_parts.append(
                f'<li style="margin: 6px 0; padding-left: 8px; position: relative;">'
                f'<span style="position: absolute; left: -12px; color: #4F46E5;">•</span>{item}</li>'
            )
            continue

        # ── 数字序号项 ──
        if re.match(r'^\d+\.\s', line):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(
                f'<div style="margin: 8px 0; padding: 10px 14px; background: #F8FAFC; '
                f'border-radius: 6px; border: 1px solid #E2E8F0;">{line}</div>'
            )
            continue

        # ── 引用/重点项 ▶ ──
        if line.startswith('▶'):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            text = line[1:].strip()
            html_parts.append(
                f'<div style="margin: 8px 0; padding: 10px 14px; background: #F8FAFC; '
                f'border-radius: 6px; border: 1px solid #E2E8F0;">💡 {text}</div>'
            )
            continue

        # ── 表格行 ──
        if '|' in line and line.count('|') >= 2:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if not cells or cells[0] in ('---', '----'):
                continue
            # 只在未进入表格时判断是否为表头行（避免数据行被误判）
            if not in_table and any(kw in line for kw in TABLE_HEADER_KEYWORDS):
                html_parts.append(
                    '<table style="width: 100%; border-collapse: collapse; margin: 12px 0; '
                    'background: white; border-radius: 8px; overflow: hidden; '
                    'box-shadow: 0 1px 3px rgba(0,0,0,0.1);"><thead><tr>'
                )
                for cell in cells:
                    html_parts.append(
                        f'<th style="padding: 12px 10px; background: linear-gradient(135deg, #4F46E5 0%, '
                        f'#6366F1 100%); color: white; text-align: left; font-weight: 600; font-size: 13px;">'
                        f'{cell}</th>'
                    )
                html_parts.append('</tr></thead><tbody>')
                in_table = True
            else:
                html_parts.append('<tr style="border-bottom: 1px solid #F1F5F9;">')
                for i, cell in enumerate(cells):
                    style = _cell_style(i, cell)
                    html_parts.append(f'<td style="{style}">{cell}</td>')
                html_parts.append('</tr>')
            continue

        # 非表格行时，如果有未闭合表格则闭合
        if in_table:
            html_parts.append('</tbody></table>')
            in_table = False

        # ── 普通文本 ──
        if in_list:
            html_parts.append('</ul>')
            in_list = False

        line = _highlight_text(line)
        html_parts.append(
            f'<p style="margin: 8px 0; line-height: 1.6; color: #475569; font-size: 14px;">{line}</p>'
        )

    # 闭合残留
    if in_list:
        html_parts.append('</ul>')
    if in_table:
        html_parts.append('</tbody></table>')

    return '\n'.join(html_parts)


# ══════════════════════════════════════════════════════════════
# CSS 工具函数
# ══════════════════════════════════════════════════════════════

def _cell_style(col_index: int, cell_text: str) -> str:
    """根据列位置和内容生成表格单元格内联样式"""
    style = "padding: 10px; font-size: 13px; color: #334155;"
    if col_index == 0:
        style += " font-weight: 600; color: #4F46E5;"
    elif _looks_like_score(cell_text):
        style += " color: #E87722; font-weight: 700;"
    elif _looks_like_pct(cell_text):
        if cell_text.startswith('-'):
            style += " color: #059669; font-weight: 600;"  # 跌绿
        else:
            style += " color: #DC2626; font-weight: 600;"  # 涨红
    return style


def _looks_like_score(text: str) -> bool:
    """判断是否是评分格式（如 85.3）"""
    clean = text.replace('.', '').replace('-', '')
    return clean.isdigit() and '.' in text


def _looks_like_pct(text: str) -> bool:
    """判断是否是百分比格式（含 +/-）"""
    return '%' in text and ('+' in text or '-' in text)


# ══════════════════════════════════════════════════════════════
# 文本高亮
# ══════════════════════════════════════════════════════════════

def _highlight_text(line: str) -> str:
    """高亮文本中的百分比、评分、代码"""
    # 涨跌百分比（涨红跌绿）
    def _color_pct(m: re.Match) -> str:
        val = m.group(1)
        if val.startswith('-'):
            return f'<span style="color: #059669; font-weight: 600;">{val}</span>'
        elif val.startswith('+') or (len(val) > 0 and val[0].isdigit()):
            return f'<span style="color: #DC2626; font-weight: 600;">{val}</span>'
        return f'<span style="color: #6B7280; font-weight: 600;">{val}</span>'

    line = re.sub(r'([+-]?\d+\.?\d*%)', _color_pct, line)

    # 评分/分数（爱马仕橙）
    line = re.sub(
        r'(评分[:：]\s*\d+\.?\d*)',
        r'<span style="color: #E87722; font-weight: 700;">\1</span>',
        line
    )
    line = re.sub(
        r'(分数[:：]\s*\d+\.?\d*)',
        r'<span style="color: #E87722; font-weight: 700;">\1</span>',
        line
    )

    # 代码
    line = re.sub(
        r'([0-9]{6}\.[A-Z]{2})',
        r'<span style="background: #EEF2FF; color: #4F46E5; padding: 2px 6px; '
        r'border-radius: 4px; font-family: monospace; font-weight: 600;">\1</span>',
        line
    )
    return line


# ══════════════════════════════════════════════════════════════
# HTML 页面包装
# ══════════════════════════════════════════════════════════════

def _wrap_html_page(
    body_html: str,
    title: str,
    date_str: str,
    variant: str = "responsive"
) -> str:
    """将 body HTML 包装为完整的邮件页面"""

    if variant == "mobile":
        return _wrap_mobile(body_html, title, date_str)
    else:
        return _wrap_responsive(body_html, title, date_str)


def _wrap_mobile(body_html: str, title: str, date_str: str) -> str:
    return f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="format-detection" content="telephone=no, date=no, address=no, email=no">
    <title>{title}</title>
    <!--[if mso]>
    <style type="text/css">
        table {{border-collapse: collapse;}}
        td {{padding: 10px;}}
    </style>
    <![endif]-->
    <style type="text/css">
        @media screen and (max-width: 428px) {{
            .content-area {{ padding: 12px !important; }}
            .stock-card {{ padding: 10px !important; margin: 8px 0 !important; }}
            table {{ font-size: 11px !important; }}
            th, td {{ padding: 6px 4px !important; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; -webkit-font-smoothing: antialiased;">
    <div style="max-width: 390px; margin: 0 auto; background-color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        <div style="background: linear-gradient(135deg, #4F46E5 0%, #6366F1 50%, #818CF8 100%); padding: 24px 20px; text-align: center;">
            <h1 style="color: white; margin: 0 0 8px 0; font-size: 20px; font-weight: 700; letter-spacing: 0.5px;">📈 {title}</h1>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0; font-size: 13px;">生成时间：{date_str}</p>
        </div>
        <div class="content-area" style="padding: 16px 20px 24px 20px; background-color: #FAFBFC;">
            {body_html}
        </div>
        {_footer_html()}
    </div>
</body>
</html>"""


def _wrap_responsive(body_html: str, title: str, date_str: str) -> str:
    return f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="format-detection" content="telephone=no, date=no, address=no, email=no">
    <title>{title}</title>
    <style type="text/css">
        body {{ margin: 0 !important; padding: 0 !important; width: 100% !important; }}
        @media screen and (max-width: 428px) {{
            .container {{ width: 100% !important; max-width: 100% !important; }}
            .header {{ padding: 20px 16px !important; }}
            .content {{ padding: 16px !important; }}
            table {{ font-size: 12px !important; }}
            th, td {{ padding: 8px 6px !important; }}
        }}
        @media screen and (min-width: 600px) {{
            .email-container {{
                max-width: 600px !important;
                margin: 20px auto !important;
                border-radius: 12px !important;
                overflow: hidden !important;
            }}
        }}
    </style>
</head>
<body style="background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;">
    <!--[if mso]>
    <center>
    <table width="600"><tr><td>
    <![endif]-->
    <div class="email-container" style="max-width: 600px; margin: 0 auto; background-color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <div class="header" style="background: linear-gradient(135deg, #4F46E5 0%, #6366F1 50%, #818CF8 100%); padding: 28px 24px; text-align: center;">
            <h1 style="color: white; margin: 0 0 8px 0; font-size: 22px; font-weight: 700;">📈 {title}</h1>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0; font-size: 14px;">生成时间：{date_str}</p>
        </div>
        <div class="content" style="padding: 20px 24px 28px 24px;">
            {body_html}
        </div>
        {_footer_html()}
    </div>
    <!--[if mso]>
    </td></tr></table>
    </center>
    <![endif]-->
</body>
</html>"""


def _footer_html() -> str:
    """公共邮件页脚"""
    return """
        <div style="background: linear-gradient(135deg, #F8FAFC 0%, #F1F5F9 100%); padding: 20px 24px; border-top: 2px solid #E2E8F0;">
            <div style="text-align: center; margin-bottom: 12px;">
                <span style="display: inline-block; padding: 8px 20px; background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%); color: white; border-radius: 20px; font-size: 13px; font-weight: 600;">Marcus策略小助手</span>
            </div>
            <p style="margin: 0 0 6px 0; text-align: center; color: #94A3B8; font-size: 12px;">⚠️ 本报告由AI自动生成，仅供参考</p>
            <p style="margin: 0 0 6px 0; text-align: center; color: #94A3B8; font-size: 12px;">股市有风险，投资需谨慎</p>
            <p style="margin: 8px 0 0 0; text-align: center; color: #94A3B8; font-size: 11px; line-height: 1.6;">所有分析结果基于技术面量化模型，不保证准确性。用户应根据自身判断和风险承受能力做出独立投资决策</p>
        </div>"""
