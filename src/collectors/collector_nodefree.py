from datetime import datetime
from lxml import etree
from .base import BaseCollector, register_collector


@register_collector
class CollectorNodefree(BaseCollector):
    name = "nodefree"
    home_page = "https://nodefree.me"

    def get_today_url(self, home_page: str) -> str:
        home_etree = etree.HTML(home_page)
        links = home_etree.xpath(
            '//*[@id="boxmoe_theme_container"]/div/div/div[1]/article[1]/div[2]/div[2]/h3/a/@href'
        )
        if not links:
            raise ValueError("No links found on homepage.")
        return links[0]

    def get_dynamic_urls(self) -> list[tuple[str, str]]:
        url_suffix = f"{datetime.now().strftime('%Y/%m/%Y%m%d')}"
        urls = [
            (
                "clash.yaml",
                f"https://nodefree.githubrowcontent.com/{url_suffix}.yaml",
            ),
            (
                "v2ray.txt",
                f"https://nodefree.githubrowcontent.com/{url_suffix}.txt",
            ),
        ]
        return urls
