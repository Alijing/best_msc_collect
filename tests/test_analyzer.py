from app.analyzer.container_scorer import pick_best_container
from app.analyzer.next_page import find_next_page
from app.parser.html_parser import parse_html

DEMO = """
<html><body>
  <div class="nav"><a href="/">首页</a><a href="/top">排行</a></div>
  <div id="list">
    <dl>
      <dd><a href="/read/1.html">第一章 初入江湖</a></dd>
      <dd><a href="/read/2.html">第二章 风雨欲来</a></dd>
      <dd><a href="/read/3.html">第三章 剑指苍穹</a></dd>
      <dd><a href="/read/4.html">第四章 暗流涌动</a></dd>
      <dd><a href="/read/5.html">第五章 雪夜孤城</a></dd>
    </dl>
  </div>
  <div class="pager">
    <a href="/novel/1/">首页</a>
    <a href="/novel/2.html">下一页</a>
    <a href="/novel/9.html">尾页</a>
  </div>
</body></html>
"""


def test_pick_best_container():
    sel = parse_html(DEMO)
    best = pick_best_container(sel)
    assert best is not None
    assert best["link_count"] >= 5
    assert best["chapter_ratio"] >= 0.9


def test_find_next_page():
    sel = parse_html(DEMO)
    nxt = find_next_page(sel, "https://example.com/novel/1/")
    assert nxt is not None
    assert "下一页" in nxt["text"]
