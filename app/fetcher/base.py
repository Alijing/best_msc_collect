from dataclasses import dataclass


@dataclass
class FetchResult:
    url: str
    status: int
    html: str
    final_url: str
