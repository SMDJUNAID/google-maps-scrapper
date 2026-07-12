from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BusinessListing:
    name: str = ""
    address: str = ""
    phone: str = ""
    website: str = ""
    rating: str = ""
    reviews_count: str = ""
    category: str = ""
    place_url: str = ""
    search_query: str = ""
    country: str = ""
    industry: str = ""
    email: str = ""
    linkedin: str = ""
    instagram: str = ""
    whatsapp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScrapeConfig:
    country: str
    industry: str
    max_results: int = 100
    headless: bool = True
    slow_mo: int = 0
    output_dir: str = "output"
    extra_queries: list[str] = field(default_factory=list)
    search_strings: list[str] = field(default_factory=list)
