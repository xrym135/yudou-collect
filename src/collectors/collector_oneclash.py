from datetime import datetime
from lxml import etree
from .base import BaseCollector


class CollectorOneclash(BaseCollector):
    name = "oneclash"
    home_page = "https://oneclash.cc/"

    def get_today_url(self, home_etree: etree._Element) -> str:
        links = home_etree.xpath(
            "/html/body/section/div/div/div[1]/div[1]/div[1]/div/div[2]/div/div[1]/h2/a/@href"
        )
        if not links:
            raise ValueError("No links found on homepage.")
        return links[0]

    def get_fix_urls(self) -> list[tuple[str, str]]:
        url_suffix = f"{datetime.now().strftime('%Y/%m/%Y%m%d')}"
        urls = [
            (
                "clash.yaml",
                f"https://oneclash.githubrowcontent.com/{url_suffix}.yaml",
            ),
            (
                "v2ray.txt",
                f"https://oneclash.githubrowcontent.com/{url_suffix}.txt",
            ),
        ]
        return urls
