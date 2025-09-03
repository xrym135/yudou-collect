from datetime import datetime
from lxml import etree
from .base import BaseCollector


class CollectorJichangx(BaseCollector):
    name = "jichangx"
    home_page = "https://jichangx.com/"

    def get_today_url(self, home_etree: etree._Element) -> str:
        return f"{self.home_page}/free-nodes-{datetime.now().strftime('%Y-%m-%d')}/"

    def get_fix_urls(self) -> list[tuple[str, str]]:
        urls = [
            (
                "v2ray.txt",
                f"{self.home_page}/nodes/v2ray-{datetime.now().strftime('%Y%m%d')}-01",
            ),
        ]
        return urls
