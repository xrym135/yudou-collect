import json
import logging
import random
import threading
import time
from pathlib import Path

import requests
import urllib3
from lxml import etree


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


COLLECTOR_REGISTRY: dict[str, type["BaseCollector"]] = {}


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class DownloadRecord:
    """管理各站点的下载记录，每次新获取的 URL 覆盖旧的"""

    def __init__(self, record_file: Path = Path("downloaded.json")):
        self.record_file = record_file
        self.data: dict[str, list[str]] = {}
        self.lock = threading.RLock()
        if record_file.exists():
            try:
                self.data = json.loads(record_file.read_text(encoding="utf-8"))
            except Exception:
                logging.warning(f"Failed to load record from {record_file}")

    def get_urls(self, site: str) -> set[str]:
        with self.lock:
            return set(self.data.get(site, []))

    def update_urls(self, site: str, urls: list[str]):
        """更新某站点的 URL，每次覆盖旧记录"""
        with self.lock:
            self.data[site] = urls
            self._save()

    def is_downloaded(self, site: str, url: str) -> bool:
        with self.lock:
            return url in self.get_urls(site)

    def _save(self):
        self.record_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")


class BaseCollector:
    """Base class for collectors"""

    name: str
    home_page: str

    DOWNLOAD_TIMEOUT = 30
    REQUEST_DELAY = (2, 5)
    heaers = {}

    def __init__(self) -> None:
        # Global session
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        if self.heaers:
            self.session.headers.update(self.heaers)

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "name") or not cls.name:
            raise AttributeError("Collector subclass must define a 'name' attribute")
        if cls.name in COLLECTOR_REGISTRY:
            raise ValueError(f"Collector name '{cls.name}' already exists")
        COLLECTOR_REGISTRY[cls.name] = cls

    @classmethod
    def list_collectors(cls) -> list[str]:
        """返回所有注册的采集器名称"""
        return list(COLLECTOR_REGISTRY.keys())

    @classmethod
    def get_collector(cls, name: str) -> type["BaseCollector"]:
        """根据名称获取采集器类"""
        if name not in COLLECTOR_REGISTRY:
            raise ValueError(f"No collector registered under name: {name}")
        return COLLECTOR_REGISTRY[name]

    def set_session_headers(self, headers: dict[str, str]) -> None:
        """设置session的请求头"""
        self.session.headers.update(headers)

    def fetch_html(self, url: str) -> etree._Element:
        logging.info(f"Fetching: {url}")
        time.sleep(random.uniform(*self.REQUEST_DELAY))
        resp = self.session.get(url, timeout=self.DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        return etree.HTML(resp.text)

    def get_today_url(self, home_etree: etree._Element) -> str | None:
        """Return today URL. Default None if not needed."""
        return None

    def parse_urls(self, page_etree: etree._Element) -> list[tuple[str, str]]:
        """Parse page to URLs. Default empty list if not needed."""
        return []

    def download_file(self, filename: str, url: str, outdir: Path) -> None:
        basedir = outdir / self.name
        basedir.mkdir(parents=True, exist_ok=True)
        try:
            logging.info(f"Downloading: {url}")
            resp = self.session.get(url, timeout=self.DOWNLOAD_TIMEOUT)
            resp.raise_for_status()
            path = basedir / filename
            path.write_text(resp.text, encoding="utf-8")
            logging.info(f"Saved to: {path}")
        except Exception:
            logging.exception(f"Failed to download {url}, skipping...")

    def download_files(self, urls: list[tuple[str, str]], output_dir: Path) -> None:
        for filename, url in urls:
            self.download_file(filename, url, output_dir)

    def get_fix_urls(self) -> list[tuple[str, str]]:
        return []

    def get_dynamic_urls(self) -> list[tuple[str, str]]:
        home_etree = self.fetch_html(self.home_page)
        today_url = self.get_today_url(home_etree)
        if not today_url:
            return []
        logging.info(f"Today's URL: {today_url}")
        page_etree = self.fetch_html(today_url)
        return self.parse_urls(page_etree)

    def get_download_urls(self) -> list[tuple[str, str]]:
        """Parse the page to get the URLs of the files."""
        urls = self.get_fix_urls()
        if urls:
            return urls
        return self.get_dynamic_urls()

    def run(
        self, output_dir: Path, record: DownloadRecord | None = None
    ) -> dict[str, str | list[str] | int]:
        logging.info(f"[{self.name}] Start collector")
        logging.info(f"[{self.name}] Fetching homepage: {self.home_page}")
        result = "success"
        all_urls: list[tuple[str, str]] = []
        new_urls: list[str] = []
        try:
            all_urls = self.get_download_urls()
            if record:
                urls_to_download = [
                    (f, u)
                    for f, u in all_urls
                    if not record.is_downloaded(self.name, u)
                ]
            else:
                urls_to_download = all_urls
            logging.info(f"Found {len(urls_to_download)} URLs.")
            if not urls_to_download:
                logging.info(f"[{self.name}] No new URLs to download.")
                if record:
                    record.update_urls(self.name, [u[1] for u in all_urls])
                return {
                    "site": self.name,
                    "total_urls": len(all_urls),
                    "new_urls": [],
                    "result": result,
                }

            start = time.time()
            self.download_files(urls_to_download, output_dir)
            new_urls = [u[1] for u in urls_to_download]

            # 更新下载记录，覆盖旧的
            if record:
                record.update_urls(self.name, [u[1] for u in all_urls])

            logging.info(f"All files downloaded in {time.time() - start:.2f}s")

        except Exception as e:
            result = "failed"
            logging.error(f"Error: {e}")
        logging.info(f"[{self.name}] Collector finished")
        return {
            "site": self.name,
            "total_urls": len(all_urls),
            "new_urls": new_urls,
            "result": result,
        }
