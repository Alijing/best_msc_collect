"""正文清洗：去广告、去水印、规范空白、相邻去重。"""
import re

_DEFAULT_NOISE_PATTERNS = [
    re.compile(r"请收藏本站|请记住本站|天才一秒|一秒记住|笔趣阁|qiyunxs|启云", re.I),
    re.compile(r"章节错误|点此举报|内容严重缺失|举报后维护|内容不全|VIP章节", re.I),
    re.compile(r"如果出现文字缺失.{0,6}格式混乱.{0,8}取消转码.{0,4}退出阅读模式"),
    re.compile(r"手机用户请|手机版阅读|手机访问|扫描二维码|扫码阅读|关注公众号", re.I),
    re.compile(r"^\s*第\s*\d+\s*章.*[求投].*[票票].*$"),
    re.compile(r"^\s*[\(（]?\s*(本章完|全文完|未完待续|待续)\s*[\)）]?\s*$"),
    re.compile(r"^\s*https?://\S+\s*$"),
    re.compile(r"^\s*www\.\S+\s*$"),
    re.compile(r"^\s*[\(（]?本章未完.*下一[页頁].*[\)）]?\s*$"),
    re.compile(r"^\s*[-=*~_·•]{3,}\s*$"),
    re.compile(r"^\s*[☆★※◆◇●○■□▲△▼▽✦✧✿❀]+\s*$"),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),
]


def clean_content(text: str, dedupe: bool = True) -> str:
    if not text:
        return ""

    lines: list[str] = []
    prev: str | None = None
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if any(p.search(ln) for p in _DEFAULT_NOISE_PATTERNS):
            continue
        if dedupe and ln == prev:
            continue
        lines.append(ln)
        prev = ln

    return "\n".join(lines)
