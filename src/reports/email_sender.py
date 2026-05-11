"""
邮件发送模块
使用SMTP发送分析报告
支持丰富的邮件内容格式
针对iPhone 12和移动端优化
"""
import smtplib
import re
import html
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formatdate
from typing import List, Optional, Dict
from pathlib import Path
from datetime import datetime

from ..core.config import EmailConfig
from ..data.fetcher import DataFetcher


def format_email_html(content: str, title: str = "【Marcus策略小助手】") -> str:
    """
    将文本内容格式化为精美的HTML邮件（移动端优化版）
    
    Args:
        content: 原始文本内容（多行字符串）
        title: 邮件标题
        
    Returns:
        HTML格式的邮件内容（针对iPhone 12优化）
    """
    # 获取当前时间
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日 %H:%M')
    
    # 将文本内容转为HTML（保留换行和基本格式）
    lines = content.split('\n')
    html_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        # 保护HTML标签不被escape（如 <strong> 预估胜率红色加粗）
        _html_tags = []
        def _save_tag(m):
            _html_tags.append(m.group(0))
            return f'\x00HTMLTAG{len(_html_tags)-1}\x00'
        line = re.sub(r'<[^>]+>', _save_tag, line)
        line = html.escape(line)
        for idx, tag in enumerate(_html_tags):
            line = line.replace(f'\x00HTMLTAG{idx}\x00', tag)
        if not line:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<div style="height: 8px;"></div>')
            continue
        
        # 处理分隔线
        if line.startswith('==') or line.startswith('━━') or line.startswith('---'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<div style="height: 12px;"></div><hr style="border: none; border-top: 2px solid #4F46E5; margin: 16px 0; opacity: 0.3;"><div style="height: 12px;"></div>')
            continue
        
        # 处理主标题 【xxx】
        if line.startswith('【') and line.endswith('】'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            # 为不同章节使用不同的渐变背景色，增强视觉区分
            title_gradient_map = {
                '每日一言': 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
                '财经动态': 'linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%)',
                '策略配置': 'linear-gradient(135deg, #D1FAE5 0%, #A7F3D0 100%)',
                '股票选择': 'linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)',
                '操作建议': 'linear-gradient(135deg, #FCE7F3 0%, #FBCFE8 100%)',
                '今日总结': 'linear-gradient(135deg, #E0E7FF 0%, #C7D2FE 100%)',
            }
            border_color_map = {
                '每日一言': '#F59E0B',
                '财经动态': '#3B82F6',
                '策略配置': '#10B981',
                '建议操作-胜率排行Top5': '#EC4899',
                '策略命中TOP15': '#4F46E5',
                '今日总结': '#6366F1',
                '风险&提示': '#EF4444',
            }
            # 提取标题文字用于匹配
            title_text = line.strip('【】')
            bg_color = title_gradient_map.get(title_text, 'linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)')
            border_color = border_color_map.get(title_text, '#4F46E5')
            
            html_lines.append(f'<h3 style="color: #1E293B; margin: 20px 0 12px 0; padding: 12px 16px; background: {bg_color}; border-radius: 8px; font-size: 16px; font-weight: 600; border-left: 4px solid {border_color}; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">{line}</h3>')
            continue
        
        # 处理子标题 ## xxx
        if line.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h4 style="color: #334155; margin: 16px 0 8px 0; font-size: 15px; font-weight: 600;">📊 {line[3:]}</h4>')
            continue
        
        # 处理列表项
        if line.startswith('• ') or line.startswith('- ') or line.startswith('* '):
            if not in_list:
                html_lines.append('<ul style="margin: 8px 0; padding-left: 20px; list-style-type: none;">')
                in_list = True
            item_content = line[2:].strip()
            # 高亮关键词
            item_content = re.sub(r'(股票代码|评分|涨跌幅|信号)', r'<strong style="color: #4F46E5;">\1</strong>', item_content)
            html_lines.append(f'<li style="margin: 6px 0; padding-left: 8px; position: relative;"><span style="position: absolute; left: -12px; color: #4F46E5;">•</span>{item_content}</li>')
            continue
        
        # 处理序号项（如 "1. xxx"）
        if re.match(r'^\d+\.\s', line):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content_text = re.sub(r'^\d+\.\s', '', line)
            html_lines.append(f'<div style="margin: 8px 0; padding: 10px 14px; background: #F8FAFC; border-radius: 6px; border: 1px solid #E2E8F0;"><span style="color: #64748B; font-size: 13px;">{line[:line.index(".")+1]}</span> {content_text}</div>')
            continue
        
        # 处理引用/重点项 ▶
        if line.startswith('▶'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            line = line[1:].strip()
            # 操作建议的 ▶ 使用粉色底色（操作建议章节内的）
            # 其他使用黄色底色
            html_lines.append(f'<div style="margin: 8px 0; padding: 10px 14px; background: #F8FAFC; border-radius: 6px; border: 1px solid #E2E8F0;">💡 {line}</div>')
            continue
        
        # 处理表格行（如包含 | 的内容）
        if '|' in line and line.count('|') >= 2:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if cells and cells[0] not in ['---', '----']:
                is_header = any(keyword in line for keyword in ['股票', '代码', '名称', '评分'])
                if is_header:
                    html_lines.append('<table style="width: 100%; border-collapse: collapse; margin: 12px 0; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);"><thead><tr>')
                    for cell in cells:
                        html_lines.append(f'<th style="padding: 12px 10px; background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%); color: white; text-align: left; font-weight: 600; font-size: 13px;">{cell}</th>')
                    html_lines.append('</tr></thead><tbody>')
                else:
                    html_lines.append('<tr style="border-bottom: 1px solid #F1F5F9;">')
                    for i, cell in enumerate(cells):
                        # 根据列内容添加样式
                        cell_style = "padding: 10px; font-size: 13px; color: #334155;"
                        if i == 0:  # 股票代码
                            cell_style += " font-weight: 600; color: #4F46E5;"
                        elif '评分' in str(cell) or cell.replace('.', '').isdigit():
                            score = float(cell) if cell.replace('.', '').replace('-', '').isdigit() else 0
                            if score >= 80:
                                cell_style += " color: #059669; font-weight: 600;"
                            elif score >= 60:
                                cell_style += " color: #D97706; font-weight: 600;"
                            else:
                                cell_style += " color: #DC2626; font-weight: 600;"
                        html_lines.append(f'<td style="{cell_style}">{cell}</td>')
                    html_lines.append('</tr>')
            continue
        elif '<tr>' in ''.join(html_lines[-5:]):
            html_lines.append('</tbody></table>')
        
        # 处理普通文本 - 高亮数字和百分比
        if in_list:
            html_lines.append('</ul>')
            in_list = False
        
        # 高亮百分比
        line = re.sub(
            r'([+-]?\d+\.?\d*%)', 
            r'<span style="color: #DC2626; font-weight: 600; background: #FEE2E2; padding: 2px 6px; border-radius: 4px;">\1</span>', 
            line
        )
        # 高亮评分
        line = re.sub(
            r'(评分[:：]\s*(\d+\.?\d*))', 
            r'<span style="color: #059669; font-weight: 600;">\1</span>', 
            line
        )
        # 高亮股票代码
        line = re.sub(
            r'([0-9]{6}\.[A-Z]{2})', 
            r'<span style="background: #EEF2FF; color: #4F46E5; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-weight: 600;">\1</span>', 
            line
        )
        
        html_lines.append(f'<p style="margin: 8px 0; line-height: 1.6; color: #475569; font-size: 14px;">{line}</p>')
    
    if in_list:
        html_lines.append('</ul>')
    
    # 关闭可能未关闭的表格
    if '<tr>' in ''.join(html_lines[-5:]):
        html_lines.append('</tbody></table>')
    
    content_html = '\n'.join(html_lines)
    
    # 生成完整的HTML邮件 - 针对iPhone 12优化
    html_output = f"""<!DOCTYPE html>
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
        /* iPhone 12 优化 */
        @media screen and (max-width: 428px) {{
            .content-area {{
                padding: 12px !important;
            }}
            .stock-card {{
                padding: 10px !important;
                margin: 8px 0 !important;
            }}
            table {{
                font-size: 11px !important;
            }}
            th, td {{
                padding: 6px 4px !important;
            }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; -webkit-font-smoothing: antialiased;">
    <!-- 针对iPhone 12优化的邮件容器 -->
    <div style="max-width: 390px; margin: 0 auto; background-color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        
        <!-- 顶部渐变头部 -->
        <div style="background: linear-gradient(135deg, #4F46E5 0%, #6366F1 50%, #818CF8 100%); padding: 24px 20px; text-align: center;">
            <h1 style="color: white; margin: 0 0 8px 0; font-size: 20px; font-weight: 700; letter-spacing: 0.5px;">📈 {title}</h1>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0; font-size: 13px;">生成时间：{date_str}</p>
        </div>
        
        <!-- 内容区域 -->
        <div class="content-area" style="padding: 16px 20px 24px 20px; background-color: #FAFBFC;">
            {content_html}
        </div>
        
        <!-- 底部信息栏 -->
        <div style="background: linear-gradient(135deg, #F8FAFC 0%, #F1F5F9 100%); padding: 16px 20px; border-top: 2px solid #E2E8F0;">
            <div style="text-align: center; margin-bottom: 12px;">
                <span style="display: inline-block; padding: 6px 16px; background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%); color: white; border-radius: 20px; font-size: 12px; font-weight: 600;">Marcus策略小助手</span>
            </div>
            <p style="margin: 0 0 6px 0; text-align: center; color: #94A3B8; font-size: 12px;">⚠️ 本报告由AI自动生成，仅供参考</p>
            <p style="margin: 0; text-align: center; color: #94A3B8; font-size: 12px;">股市有风险，投资需谨慎</p>
            <p style="margin: 8px 0 0 0; text-align: center; color: #94A3B8; font-size: 11px; line-height: 1.6;">所有分析结果基于技术面量化模型，不保证准确性。用户应根据自身判断和风险承受能力做出独立投资决策</p>
        </div>
        
    </div>
</body>
</html>"""
    
    return html_output


def format_email_html_responsive(content: str, title: str = "【Marcus策略小助手】") -> str:
    """
    将文本内容格式化为响应式HTML邮件（同时支持移动端和桌面端）
    
    Args:
        content: 原始文本内容（多行字符串）
        title: 邮件标题
        
    Returns:
        HTML格式的邮件内容（响应式设计）
    """
    # 获取当前时间
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日 %H:%M')
    
    # 将文本内容转为HTML（保留换行和基本格式）
    lines = content.split('\n')
    html_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        # 保护HTML标签不被escape（如 <strong> 预估胜率红色加粗）
        _html_tags = []
        def _save_tag_r(m):
            _html_tags.append(m.group(0))
            return f'\x00HTMLTAG{len(_html_tags)-1}\x00'
        line = re.sub(r'<[^>]+>', _save_tag_r, line)
        line = html.escape(line)
        for idx, tag in enumerate(_html_tags):
            line = line.replace(f'\x00HTMLTAG{idx}\x00', tag)
        if not line:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<div style="height: 8px;"></div>')
            continue
        
        # 处理分隔线
        if line.startswith('==') or line.startswith('━━') or line.startswith('---'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<hr style="border: none; border-top: 2px solid #4F46E5; margin: 16px 0; opacity: 0.3;">')
            continue
        
        # 处理主标题
        if line.startswith('【') and line.endswith('】'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            # 为不同章节使用不同的渐变背景色
            title_gradient_map = {
                '每日一言': 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)',
                '财经动态': 'linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%)',
                '策略配置': 'linear-gradient(135deg, #D1FAE5 0%, #A7F3D0 100%)',
                '股票选择': 'linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)',
                '操作建议': 'linear-gradient(135deg, #FCE7F3 0%, #FBCFE8 100%)',
                '今日总结': 'linear-gradient(135deg, #E0E7FF 0%, #C7D2FE 100%)',
            }
            border_color_map = {
                '每日一言': '#F59E0B',
                '财经动态': '#3B82F6',
                '策略配置': '#10B981',
                '建议操作-胜率排行Top5': '#EC4899',
                '策略命中TOP15': '#4F46E5',
                '今日总结': '#6366F1',
                '风险&提示': '#EF4444',
            }
            title_text = line.strip('【】')
            bg_color = title_gradient_map.get(title_text, 'linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)')
            border_color = border_color_map.get(title_text, '#4F46E5')
            
            html_lines.append(f'<h3 style="color: #1E293B; margin: 20px 0 12px 0; padding: 12px 16px; background: {bg_color}; border-radius: 8px; font-size: 16px; font-weight: 600; border-left: 4px solid {border_color}; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">{line}</h3>')
            continue
        
        # 处理子标题
        if line.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<h4 style="color: #334155; margin: 16px 0 8px 0; font-size: 15px; font-weight: 600;">📊 {line[3:]}</h4>')
            continue
        
        # 处理列表项
        if line.startswith('• ') or line.startswith('- ') or line.startswith('* '):
            if not in_list:
                html_lines.append('<ul style="margin: 8px 0; padding-left: 20px; list-style-type: none;">')
                in_list = True
            item_content = line[2:].strip()
            html_lines.append(f'<li style="margin: 6px 0; padding-left: 8px; position: relative;"><span style="position: absolute; left: -12px; color: #4F46E5;">•</span>{item_content}</li>')
            continue
        
        # 处理序号项
        if re.match(r'^\d+\.\s', line):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content_text = re.sub(r'^\d+\.\s', '', line)
            html_lines.append(f'<div style="margin: 8px 0; padding: 10px 14px; background: #F8FAFC; border-radius: 6px; border: 1px solid #E2E8F0;">{line}</div>')
            continue
        
        # 处理引用/重点项
        if line.startswith('▶'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            line = line[1:].strip()
            html_lines.append(f'<div style="margin: 8px 0; padding: 10px 14px; background: #F8FAFC; border-radius: 6px; border: 1px solid #E2E8F0;">💡 {line}</div>')
            continue
        
        # 处理表格
        if '|' in line and line.count('|') >= 2:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if cells and cells[0] not in ['---', '----']:
                is_header = any(keyword in line for keyword in ['股票', '代码', '名称', '评分'])
                if is_header:
                    html_lines.append('<table style="width: 100%; border-collapse: collapse; margin: 12px 0; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);"><thead><tr>')
                    for cell in cells:
                        html_lines.append(f'<th style="padding: 12px 10px; background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%); color: white; text-align: left; font-weight: 600; font-size: 13px;">{cell}</th>')
                    html_lines.append('</tr></thead><tbody>')
                else:
                    html_lines.append('<tr style="border-bottom: 1px solid #F1F5F9;">')
                    for i, cell in enumerate(cells):
                        cell_style = "padding: 10px; font-size: 13px; color: #334155;"
                        if i == 0:
                            cell_style += " font-weight: 600; color: #4F46E5;"
                        html_lines.append(f'<td style="{cell_style}">{cell}</td>')
                    html_lines.append('</tr>')
            continue
        elif '<tr>' in ''.join(html_lines[-5:]):
            html_lines.append('</tbody></table>')
        
        # 处理普通文本
        if in_list:
            html_lines.append('</ul>')
            in_list = False
        
        line = re.sub(r'([+-]?\d+\.?\d*%)', r'<span style="color: #DC2626; font-weight: 600;">\1</span>', line)
        line = re.sub(r'(评分[:：]\d+\.?\d*)', r'<span style="color: #059669; font-weight: 600;">\1</span>', line)
        line = re.sub(r'([0-9]{6}\.[A-Z]{2})', r'<span style="background: #EEF2FF; color: #4F46E5; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-weight: 600;">\1</span>', line)
        
        html_lines.append(f'<p style="margin: 8px 0; line-height: 1.6; color: #475569; font-size: 14px;">{line}</p>')
    
    if in_list:
        html_lines.append('</ul>')
    
    if '<tr>' in ''.join(html_lines[-5:]):
        html_lines.append('</tbody></table>')
    
    content_html = '\n'.join(html_lines)
    
    # 生成响应式HTML
    html_output = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="format-detection" content="telephone=no, date=no, address=no, email=no">
    <title>{title}</title>
    <style type="text/css">
        /* 基础样式重置 */
        body {{
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
        }}
        
        /* 针对iPhone 12及类似设备的优化 */
        @media screen and (max-width: 428px) {{
            .container {{
                width: 100% !important;
                max-width: 100% !important;
            }}
            .header {{
                padding: 20px 16px !important;
            }}
            .content {{
                padding: 16px !important;
            }}
            table {{
                font-size: 12px !important;
            }}
            th, td {{
                padding: 8px 6px !important;
            }}
        }}
        
        /* 针对桌面端的优化 */
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
        
        <!-- 顶部渐变头部 -->
        <div class="header" style="background: linear-gradient(135deg, #4F46E5 0%, #6366F1 50%, #818CF8 100%); padding: 28px 24px; text-align: center;">
            <h1 style="color: white; margin: 0 0 8px 0; font-size: 22px; font-weight: 700;">📈 {title}</h1>
            <p style="color: rgba(255, 255, 255, 0.9); margin: 0; font-size: 14px;">生成时间：{date_str}</p>
        </div>
        
        <!-- 内容区域 -->
        <div class="content" style="padding: 20px 24px 28px 24px;">
            {content_html}
        </div>
        
        <!-- 底部信息栏 -->
        <div style="background: linear-gradient(135deg, #F8FAFC 0%, #F1F5F9 100%); padding: 20px 24px; border-top: 2px solid #E2E8F0;">
            <div style="text-align: center; margin-bottom: 12px;">
                <span style="display: inline-block; padding: 8px 20px; background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%); color: white; border-radius: 20px; font-size: 13px; font-weight: 600;">Marcus策略小助手</span>
            </div>
            <p style="margin: 0 0 6px 0; text-align: center; color: #94A3B8; font-size: 12px;">⚠️ 本报告由AI自动生成，仅供参考</p>
            <p style="margin: 0 0 6px 0; text-align: center; color: #94A3B8; font-size: 12px;">股市有风险，投资需谨慎</p>
            <p style="margin: 8px 0 0 0; text-align: center; color: #94A3B8; font-size: 11px; line-height: 1.6;">所有分析结果基于技术面量化模型，不保证准确性。用户应根据自身判断和风险承受能力做出独立投资决策</p>
        </div>
        
    </div>
    
    <!--[if mso]>
    </td></tr></table>
    </center>
    <![endif]-->
</body>
</html>"""
    
    return html_output


class EmailSender:
    """
    邮件发送器（优化版）
    
    支持QQ邮箱SMTP发送，包含丰富的邮件格式
    针对移动端（特别是iPhone 12）优化
    """
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.logger = logging.getLogger("AInvest.EmailSender")
        self.data_fetcher = DataFetcher()
    
    def generate_email_content(self, stock_results: List[Dict], strategy_config: Dict = None) -> str:
        """
        生成完整的邮件内容
        
        Args:
            stock_results: 股票选择结果列表
            strategy_config: 策略配置信息
            
        Returns:
            完整的邮件内容（纯文本格式，将由format_email_html处理）
        """
        content_lines = []
        
        # 1. 每日一言
        daily_quote = self.data_fetcher.get_daily_quote()
        content_lines.append("【每日一言】")
        content_lines.append("")
        content_lines.append(f"💡 {daily_quote}")
        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")
        
        # 2. 财经动态
        content_lines.append("【财经动态】")
        content_lines.append("")
        
        news_list = self.data_fetcher.fetch_all_news()
        if news_list:
            for i, news in enumerate(news_list[:10], 1):
                title = news.get('title', '')
                # 去除时间，只保留标题
                content_lines.append(f"{i}. {title}")
        else:
            content_lines.append("暂无财经动态更新")
        
        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")
        
        # 3. 策略配置
        content_lines.append("【策略配置】")
        content_lines.append("")
        
        if strategy_config:
            for strategy_name, weight in strategy_config.items():
                content_lines.append(f"• {strategy_name}: 权重 {weight}%")
        else:
            content_lines.append("• 默认策略: 权重 100%")
        
        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")
        
        # 4. 策略命中TOP15
        content_lines.append("【策略命中TOP15】")
        content_lines.append("")

        if stock_results:
            for i, stock in enumerate(stock_results[:15], 1):
                symbol = stock.get('symbol', '')
                name = stock.get('name', '')
                current_price = stock.get('current_price', 0)
                change_pct = stock.get('change_pct', 0)
                score = stock.get('score', 0)
                amount = stock.get('amount', 0)
                signals = stock.get('signals', [])
                change_str = f"{change_pct:+.2f}%"
                amount_str = f"{amount/1e8:.2f}亿" if amount >= 1e8 else f"{amount/1e4:.0f}万" if amount > 0 else "N/A"
                sig_str = " / ".join(signals[:3]) if signals else "-"
                content_lines.append(f"▶ {i}. {name}（{symbol}）  成交额：{amount_str}")
                content_lines.append(f"   评分：{score:.1f}分  现价：{current_price:.2f}元 ({change_str})")
                content_lines.append(f"   命中策略：{sig_str}")
                content_lines.append("")

        content_lines.append("=" * 50)
        content_lines.append("")

        # 5. 建议操作-胜率排行Top5
        content_lines.append("【建议操作-胜率排行Top5】")
        content_lines.append("")
        
        if stock_results:
            for i, stock in enumerate(stock_results[:5], 1):
                symbol = stock.get('symbol', '')
                name = stock.get('name', '')
                current_price = stock.get('current_price', 0)
                change_pct = stock.get('change_pct', 0)
                suggest_buy_price = stock.get('suggest_buy_price', current_price * 0.98)
                stop_loss = stock.get('stop_loss', suggest_buy_price * 0.95)
                take_profit = stock.get('take_profit', suggest_buy_price * 1.10)
                win_rate = stock.get('win_rate', 0)
                signals = stock.get('signals', [])
                sig_str = " / ".join(signals[:3]) if signals else "-"

                content_lines.append(f"▶ {i}. {name}（{symbol}）   预估胜率：<strong style='color:#DC2626;font-weight:bold;'>{win_rate:.1f}%</strong>")
                content_lines.append(f"   现价：{current_price:.2f}元 ({change_pct:+.2f}%)   建议买入：{suggest_buy_price:.2f}元")
                content_lines.append(f"   止损：{stop_loss:.2f}元（-5%）  止盈：{take_profit:.2f}元（+8%）")
                content_lines.append(f"   命中策略：{sig_str}")
                content_lines.append("")
        
        content_lines.append("=" * 50)
        content_lines.append("")

        # 6. 市场态势
        content_lines.append("【市场态势】")
        content_lines.append("")

        try:
            overview = self.data_fetcher.get_market_overview()
            # 沪深300
            if overview.get('csi300'):
                csi = overview['csi300']
                csi_chg = csi['change_pct']
                arrow = "↑" if csi_chg >= 0 else "↓"
                content_lines.append(f"📈 沪深300:  {csi_chg:+.2f}% {arrow}")
            # 创业板指
            if overview.get('cyb_index'):
                cyb = overview['cyb_index']
                cyb_chg = cyb['change_pct']
                arrow = "↑" if cyb_chg >= 0 else "↓"
                content_lines.append(f"📊 创业板指:  {cyb_chg:+.2f}% {arrow}")
            # 涨跌家数
            up_total = overview.get('up_count', 0)
            down_total = overview.get('down_count', 0)
            if up_total > 0 or down_total > 0:
                total = up_total + down_total
                up_ratio = up_total / total * 100 if total > 0 else 50
                content_lines.append(f"📊 涨跌家数:  上涨 {up_total} 家 / 下跌 {down_total} 家 (上涨占比 {up_ratio:.0f}%)")
            # 总成交额
            total_amt = overview.get('total_amount', 0)
            if total_amt > 0:
                amt_str = f"{total_amt/1e12:.2f}万亿" if total_amt >= 1e12 else f"{total_amt/1e8:.0f}亿"
                content_lines.append(f"💹 市场成交:  {amt_str}")
        except Exception:
            if stock_results:
                up_count_all = sum(1 for s in stock_results[:15] if s.get('change_pct', 0) > 0)
                down_count_all = sum(1 for s in stock_results[:15] if s.get('change_pct', 0) < 0)
                content_lines.append(f"📊 涨跌家数(样本):  上涨 {up_count_all} / 下跌 {down_count_all}")

        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")

        # 7. 今日总结
        content_lines.append("【今日总结】")
        content_lines.append("")

        if stock_results:
            avg_score = sum(s.get('score', 0) for s in stock_results[:15]) / min(15, len(stock_results))
            up_count = sum(1 for s in stock_results[:15] if s.get('change_pct', 0) > 0)

            content_lines.append(f"▶ 平均评分: {avg_score:.1f}")
            content_lines.append(f"▶ 上涨家数: {up_count} 只")
            content_lines.append(f"▶ 建议重点关注前3只股票")

        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")

        # 7. 风险&提示
        content_lines.append("【风险&提示】")
        content_lines.append("")
        content_lines.append("• 以上仅供参考，不构成投资建议")
        content_lines.append("• 股市有风险，投资需谨慎")
        content_lines.append("• 建议分散持仓，单只仓位不超过总资金的20%")
        content_lines.append("• 必须设置止损位（建议-5%），严格执行")
        content_lines.append("")

        ipo_list = self.data_fetcher.get_ipo_calendar(max_days=7)
        if ipo_list:
            content_lines.append("📋 近期打新日历（未来7天）：")
            for ipo in ipo_list:
                content_lines.append(f"  • {ipo['apply_date']}  {ipo['stock_name']}（{ipo['stock_code']}）申购代码：{ipo['apply_code']} | 发行价：{ipo['price']} | 顶格市值：{ipo['market_cap_needed']}万")
        else:
            content_lines.append("📋 近7天暂无新股申购安排")

        return '\n'.join(content_lines)
    
    def send(
        self,
        subject: str,
        html_content: str,
        to_emails: Optional[List[str]] = None,
        cc_emails: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
        use_responsive: bool = True
    ) -> bool:
        """
        发送邮件
        
        Args:
            subject: 邮件主题
            html_content: HTML邮件内容（纯文本，将被格式化）
            to_emails: 收件人列表（覆盖配置）
            cc_emails: 抄送列表（覆盖配置）
            attachments: 附件路径列表
            use_responsive: 是否使用响应式设计（默认True）
            
        Returns:
            发送是否成功
        """
        if not self.config.enabled:
            self.logger.info("邮件发送已禁用")
            return False
        
        # 格式化HTML内容
        if use_responsive:
            html_content = format_email_html_responsive(html_content, subject)
        else:
            html_content = format_email_html(html_content, subject)
        
        # 确定收件人
        recipients = to_emails or self.config.to_emails
        cc_list = cc_emails or self.config.cc_emails
        
        if not recipients:
            self.logger.error("没有配置收件人")
            return False
        
        # 调试模式跳过抄送
        if self.config.debug_mode:
            cc_list = []
            self.logger.info("调试模式：跳过抄送")
        
        try:
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = self.config.smtp_user
            msg['To'] = ', '.join(recipients)
            msg['Date'] = formatdate(localtime=True)
            
            if cc_list:
                msg['Cc'] = ', '.join(cc_list)
            
            # 添加纯文本版本和HTML版本
            plain_content = self._html_to_plain(html_content)
            msg.attach(MIMEText(plain_content, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 添加附件
            if attachments:
                mixed_msg = MIMEMultipart('mixed')
                mixed_msg['Subject'] = msg['Subject']
                mixed_msg['From'] = msg['From']
                mixed_msg['To'] = msg['To']
                mixed_msg['Date'] = msg['Date']
                if cc_list:
                    mixed_msg['Cc'] = msg['Cc']
                mixed_msg.attach(msg)
                
                for filepath in attachments:
                    self._add_attachment(mixed_msg, filepath)
                
                msg = mixed_msg
            
            # 发送邮件
            all_recipients = recipients + cc_list
            
            # 根据端口选择连接方式
            if self.config.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port, timeout=30)
                server.starttls()
            
            with server as smtp_server:
                smtp_server.login(self.config.smtp_user, self.config.smtp_password)
                smtp_server.sendmail(self.config.smtp_user, all_recipients, msg.as_string())
            
            self.logger.info(f"邮件发送成功: {recipients}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            self.logger.error("SMTP认证失败，请检查用户名和授权码")
            return False
        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP发送失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"邮件发送异常: {e}")
            return False
    
    def _html_to_plain(self, html: str) -> str:
        """将HTML转换为纯文本"""
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'<p[^>]*>', '\n', text)
        text = re.sub(r'</p>', '', text)
        text = re.sub(r'<h[1-6][^>]*>', '\n', text)
        text = re.sub(r'</h[1-6]>', '\n', text)
        text = re.sub(r'<div[^>]*>', '\n', text)
        text = re.sub(r'</div>', '', text)
        text = re.sub(r'<li[^>]*>', '• ', text)
        text = re.sub(r'</li>', '\n', text)
        text = re.sub(r'<ul[^>]*>', '', text)
        text = re.sub(r'</ul>', '', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()
    
    def _add_attachment(self, msg: MIMEMultipart, filepath: str):
        """添加附件"""
        try:
            path = Path(filepath)
            if not path.exists():
                self.logger.warning(f"附件不存在: {filepath}")
                return
            
            with open(path, 'rb') as f:
                part = MIMEApplication(f.read(), Name=path.name)
                part['Content-Disposition'] = f'attachment; filename="{path.name}"'
                msg.attach(part)
            
            self.logger.debug(f"已添加附件: {path.name}")
            
        except Exception as e:
            self.logger.warning(f"添加附件失败: {e}")
    
    def send_report(
        self,
        results_summary: str,
        html_content: str,
        strategy_name: str,
        attachments: Optional[List[str]] = None,
        stock_results: List[Dict] = None,
        strategy_config: Dict = None
    ) -> bool:
        """
        发送选股报告
        
        Args:
            results_summary: 结果摘要（纯文本）
            html_content: HTML报告内容
            strategy_name: 策略名称
            attachments: 附件路径列表
            stock_results: 股票选择结果列表
            strategy_config: 策略配置信息
            
        Returns:
            发送是否成功
        """
        # 构建邮件主题（新格式）
        date_str = datetime.now().strftime('%Y-%m-%d')
        subject = f"[Marcus策略小助手] {date_str} 动态策略报告"
        
        # 生成完整的邮件内容
        if stock_results:
            email_content = self.generate_email_content(stock_results, strategy_config)
        else:
            email_content = results_summary
        
        # 使用配置中的收件人
        to_emails = self.config.to_emails if self.config.to_emails else []
        cc_emails = self.config.cc_emails if self.config.cc_emails else []
        
        self.logger.info(f"准备发送邮件:")
        self.logger.info(f"  主题: {subject}")
        self.logger.info(f"  收件人: {to_emails}")
        self.logger.info(f"  附件: {attachments}")
        
        # 使用生成的内容发送邮件
        return self.send(
            subject=subject,
            html_content=email_content,
            to_emails=to_emails,
            cc_emails=cc_emails,
            attachments=attachments
        )
    
    def test_connection(self) -> bool:
        """
        测试SMTP连接
        
        Returns:
            连接是否成功
        """
        try:
            with smtplib.SMTP_SSL(
                self.config.smtp_server,
                self.config.smtp_port,
                timeout=30
            ) as server:
                server.login(self.config.smtp_user, self.config.smtp_password)
            
            self.logger.info("SMTP连接测试成功")
            return True
            
        except Exception as e:
            self.logger.error(f"SMTP连接测试失败: {e}")
            return False
