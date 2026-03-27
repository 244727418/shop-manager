# -*- coding: utf-8 -*-
"""UI 工具函数：Markdown 转 HTML 等，供利润分析、历史记录等对话框复用。"""
import re


def convert_markdown_to_html(text):
    """将简单 Markdown 文本转为 HTML，用于 QTextBrowser 等展示。"""
    if not text:
        return ""

    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    lines = text.split("\n")
    result = []
    in_list = False
    i = 0
    length = len(lines)

    while i < length:
        line = lines[i]

        if not line.strip():
            if in_list:
                result.append("</ul>")
                in_list = False
            i += 1
            continue

        h_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if h_match:
            if in_list:
                result.append("</ul>")
                in_list = False
            level = len(h_match.group(1))
            content = h_match.group(2)
            result.append(f"<h{level}>{content}</h{level}>")
            i += 1
            continue

        list_match = re.match(r"^(\d+)\.\s+(.+)$", line)
        if list_match:
            if not in_list:
                result.append("<ul>")
                in_list = True
            content = list_match.group(2)
            content = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", content)
            content = re.sub(r"\*(.+?)\*", r"<i>\1</i>", content)
            content = re.sub(r"`(.+?)`", r"<code>\1</code>", content)
            result.append(f"<li>{content}</li>")
            i += 1
            continue

        bullet_match = re.match(r"^[-*]\s+(.+)$", line)
        if bullet_match:
            if not in_list:
                result.append("<ul>")
                in_list = True
            content = bullet_match.group(1)
            content = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", content)
            content = re.sub(r"\*(.+?)\*", r"<i>\1</i>", content)
            content = re.sub(r"`(.+?)`", r"<code>\1</code>", content)
            result.append(f"<li>{content}</li>")
            i += 1
            continue

        if in_list:
            result.append("</ul>")
            in_list = False

        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"\*(.+?)\*", r"<i>\1</i>", line)
        line = re.sub(r"`(.+?)`", r"<code>\1</code>", line)
        result.append(f"<p>{line}</p>")
        i += 1

    if in_list:
        result.append("</ul>")

    html = "".join(result)
    html = re.sub(r"(<br>\s*)+", "<br>", html)
    return html
