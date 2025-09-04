from abc import ABC, abstractmethod
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
        self.data: dict[str, dict[str, bool]] = {}
        self.lock = threading.RLock()
        if record_file.exists():
            try:
                self.data = json.loads(record_file.read_text(encoding="utf-8"))
            except Exception:
                logging.warning(f"Failed to load record from {record_file}")
    
    def update_site(self, site: str, site_data: dict[str, bool]) -> None:
        with self.lock:
            self.data[site] = site_data
            self.save_record()

    def is_downloaded(self, site: str, url: str) -> bool:
        with self.lock:
            return self.data.get(site, {}).get(url, False)

    def save_record(self):
        with self.lock:
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
                    extralog = f"with proxy: {proxy}" if proxy else ""
                    logging.info(f"Successfully fetched {url} {extralog}")
                    return resp
                except Exception as e:
                    logging.debug(f"Proxy {proxy} failed: {e}")
        raise RuntimeError(f"All proxies failed to fetch {url}")


class BaseCollector(ABC):
    """采集器逻辑"""

    name: str
    home_page: str
    DOWNLOAD_TIMEOUT = 20

    def __init__(self, proxies_list: list[str] | None = None):
        self.proxy_manager = ProxyManager(proxies_list)

    # -------------------- HTML抓取 -------------------- #
    def fetch_html(self, url: str) -> str:
        start = time.time()
        logging.info(f"[{self.name}] Fetching: {url}")
        resp = self.proxy_manager.fetch_html(url, timeout=self.DOWNLOAD_TIMEOUT)
        logging.info(f"[{self.name}] Fetching: {url} took {time.time() - start:.2f}s")
        return resp.text

    @abstractmethod
    def get_download_urls(self) -> list[tuple[str, str]]:
        raise NotImplementedError

    # -------------------- 文件下载 -------------------- #
    def download_file(self, filename: str, url: str, outdir: Path) -> bool:
        basedir = outdir / self.name
        basedir.mkdir(parents=True, exist_ok=True)
        try:
            logging.info(f"[{self.name}] Downloading: {url}")
            resp_data = self.fetch_html(url)
            path = basedir / filename
            path.write_text(resp_data, encoding="utf-8")
            logging.info(f"[{self.name}] Saved to: {path}")
            return True 
        except Exception as e:
            logging.error(f"[{self.name}] Failed to download {url} {e}, skipping...")
            return False

    def download_files(
        self, urls: list[tuple[str, str]], output_dir: Path, record: DownloadRecord | None = None
    ) -> tuple[dict[str, bool], dict[str, bool]]:
        data = {}
        new_url = {}
        for f, u in urls:
            if record and record.is_downloaded(self.name, u):
                data[u] = True
                continue
            ret = self.download_file(f, u, output_dir)
            data[u] = ret
            new_url[u] = ret
        return data, new_url

    # -------------------- 结果管理 -------------------- #
    def _make_result(
        self,
        all_urls: list[tuple[str, str]],
        new_urls: dict[str, bool],
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
        urls: list[tuple[str, str]] = []
        new_urls: dict[str, bool] = {}

        try:
            urls = self.get_download_urls()
            
            logging.info(f"[{self.name}] Found {len(urls)} URLs.")
            
            site_data, new_urls = self.download_files(urls, output_dir, record)

            if record:
                record.update_site(self.name, site_data)

        except Exception as e:
            result = "failed"
            logging.error(f"[{self.name}] Error: {e}")

        logging.info(f"[{self.name}] Collector finished")
        return self._make_result(urls, new_urls, result)


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
