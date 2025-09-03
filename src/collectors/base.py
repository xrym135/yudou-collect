from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import threading
import time
from pathlib import Path
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

COLLECTOR_REGISTRY: dict[str, type["BaseCollector"]] = {}


class DownloadRecord:
    """管理各站点下载记录，每次新获取 URL 覆盖旧记录"""

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
        with self.lock:
            self.data[site] = urls
            self._save()

    def is_downloaded(self, site: str, url: str) -> bool:
        with self.lock:
            return url in self.get_urls(site)

    def _save(self):
        self.record_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")


class ProxyManager:
    """管理代理池并发请求"""

    def __init__(self, proxies_list: list[str] | None = None):
        self.lock = threading.RLock()
        self.proxies_list = proxies_list or []
        self.proxies_list.insert(0, "")
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )

    def _request(
        self, url: str, proxy: str | None, timeout: int = 30
    ) -> requests.Response:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        resp = self.session.get(url, proxies=proxies, timeout=timeout)
        resp.raise_for_status()
        if resp.text.strip() == "":
            raise ValueError("Empty response")
        return resp

    def fetch_html(
        self, url: str, max_workers: int = 10, timeout: int = 30
    ) -> requests.Response:
        proxies = self.proxies_list.copy()
        if not proxies:
            raise RuntimeError(f"All proxies failed to fetch {url}")
        with ThreadPoolExecutor(max_workers=min(max_workers, len(proxies))) as executor:
            futures = {
                executor.submit(self._request, url, p, timeout): p for p in proxies
            }
            for future in as_completed(futures):
                proxy = futures[future]
                try:
                    resp = future.result()
                    logging.info(f"Successfully fetched {url} with proxy {proxy}")
                    return resp
                except Exception as e:
                    logging.debug(f"Proxy {proxy} failed: {e}")
        raise RuntimeError(f"All proxies failed to fetch {url}")


class BaseCollector:
    """核心采集器逻辑，不负责注册"""

    name: str
    home_page: str
    DOWNLOAD_TIMEOUT = 60

    def __init__(self, proxies_list: list[str] | None = None):
        self.proxy_manager = ProxyManager(proxies_list)

    # -------------------- HTML抓取 -------------------- #
    def fetch_html(self, url: str) -> str:
        logging.info(f"Fetching: {url}")
        resp = self.proxy_manager.fetch_html(url, timeout=self.DOWNLOAD_TIMEOUT)
        return resp.text

    def get_today_url(self, home_page: str) -> str | None:
        """子类覆盖动态生成今日页面 URL"""
        return None

    def parse_urls(self, today_page: str) -> list[tuple[str, str]]:
        """子类覆盖解析页面得到下载 URL"""
        return []

    def get_download_urls(self) -> list[tuple[str, str]]:
        home_page = self.fetch_html(self.home_page)
        today_url = self.get_today_url(home_page)
        if not today_url:
            return []
        logging.info(f"Today's URL: {today_url}")
        today_page = self.fetch_html(today_url)
        return self.parse_urls(today_page)

    # -------------------- 文件下载 -------------------- #
    def download_file(self, filename: str, url: str, outdir: Path):
        basedir = outdir / self.name
        basedir.mkdir(parents=True, exist_ok=True)
        try:
            logging.info(f"Downloading: {url}")
            resp_data = self.fetch_html(url)
            path = basedir / filename
            path.write_text(resp_data, encoding="utf-8")
            logging.info(f"Saved to: {path}")
        except Exception:
            logging.exception(f"Failed to download {url}, skipping...")

    def download_files(
        self, urls: list[tuple[str, str]], output_dir: Path, max_workers: int = 5
    ):
        if not urls:
            return
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.download_file, f, u, output_dir) for f, u in urls
            ]
            for future in as_completed(futures):
                future.result()

    # -------------------- 结果管理 -------------------- #
    def _make_result(
        self,
        all_urls: list[tuple[str, str]],
        new_urls: list[str],
        result: str = "success",
    ):
        return {
            "site": self.name,
            "total_urls": len(all_urls),
            "new_urls": new_urls,
            "result": result,
        }

    def run(
        self, output_dir: Path, record: DownloadRecord | None = None
    ) -> dict[str, str | list[str] | int]:
        logging.info(f"[{self.name}] Start collector")
        result = "success"
        all_urls: list[tuple[str, str]] = []
        new_urls: list[str] = []

        try:
            all_urls = self.get_download_urls()
            urls_to_download = (
                [(f, u) for f, u in all_urls if not record.is_downloaded(self.name, u)]
                if record
                else all_urls
            )
            logging.info(f"Found {len(urls_to_download)} URLs.")

            if urls_to_download:
                start = time.time()
                self.download_files(urls_to_download, output_dir)
                new_urls = [u for _, u in urls_to_download]
                logging.info(f"All files downloaded in {time.time() - start:.2f}s")

            if record:
                record.update_urls(self.name, [u for _, u in all_urls])

        except Exception as e:
            result = "failed"
            logging.error(f"Error: {e}")

        logging.info(f"[{self.name}] Collector finished")
        return self._make_result(all_urls, new_urls, result)


# -------------------- 子类注册辅助函数 -------------------- #
def register_collector(cls: type[BaseCollector]):
    """注册采集器子类"""
    name = cls.name
    if name in COLLECTOR_REGISTRY:
        raise ValueError(f"Collector {name} already registered")
    COLLECTOR_REGISTRY[name] = cls
    return cls


def list_collectors() -> list[str]:
    return list(COLLECTOR_REGISTRY.keys())


def get_collector(name: str) -> type[BaseCollector]:
    if name not in COLLECTOR_REGISTRY:
        raise ValueError(f"No collector registered under name: {name}")
    return COLLECTOR_REGISTRY[name]
