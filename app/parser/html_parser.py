from parsel import Selector


def parse_html(html: str) -> Selector:
    return Selector(text=html)
