import re
from lxml import etree
from .base import BaseCollector, register_collector


@register_collector
class CollectorCfmem(BaseCollector):
    name = "cfmeme"
    home_page = "https://www.cfmem.com"

    def get_today_url(self, home_page: str) -> str:
        home_etree = etree.HTML(home_page)
        links = home_etree.xpath('//*[@id="Blog1"]/div[1]/article[1]/div[1]/h2/a/@href')
        if not links:
            raise ValueError("No links found on homepage.")
        return links[0]

    def parse_urls(self, today_page: str) -> list[tuple[str, str]]:
        page_etree = etree.HTML(today_page)
        rules = {
            "clash.yaml": [
                '//*[@id="post-body"]/div/div[4]/div[2]/span/text()',
                r"https?://[^\s'\"<>]+?\.(?:yaml)",
            ],
            "v2ray.txt": [
                '//*[@id="post-body"]/div/div[4]/div[1]/span/text()',
                r"https?://[^\s'\"<>]+?\.(?:txt)",
            ],
        }
        urls: list[tuple[str, str]] = []
        for filename, (xpath_expr, regex_expr) in rules.items():
            hrefs: list[str] = page_etree.xpath(xpath_expr)
            if hrefs:
                re_href = re.findall(regex_expr, hrefs[0])
                if re_href:
                    urls.append((filename, str(re_href[0])))
        return urls
