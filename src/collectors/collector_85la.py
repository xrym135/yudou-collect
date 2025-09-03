from lxml import etree
from .base import BaseCollector


class Collector85la(BaseCollector):
    name = "85la"
    home_page = "https://www.85la.com"
    DOWNLOAD_TIMEOUT = 100

    def __init__(self) -> None:
        super().__init__()
        # Global session
        proxy = "http://123.157.255.82:3128"
        self.session.proxies = {
            "http": proxy,
            "https": proxy,
        }

    def get_today_url(self, home_etree: etree._Element) -> str:
        links = home_etree.xpath(
            '(//div[contains(@class,"title-article")])[1]//a/@href'
        )
        if not links:
            raise ValueError("No links found on homepage.")
        return links[0]

    def parse_urls(self, page_etree: etree._Element) -> list[tuple[str, str]]:
        rules = {
            "clash.yaml": '//*[@id="md_content_2"]/div/div[5]/div[4]/p/a/@href',
            "v2ray.txt": '//*[@id="md_content_2"]/div/div[5]/div[2]/p/a/@href',
        }
        urls: list[tuple[str, str]] = []
        for filename, xpath_expr in rules.items():
            hrefs: list[str] = page_etree.xpath(xpath_expr)
            if hrefs:
                urls.append((filename, str(hrefs[0])))
        return urls
