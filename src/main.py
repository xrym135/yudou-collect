import argparse
from datetime import datetime
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from collectors.base import (
    DownloadRecord,
    get_collector,
    list_collectors,
)

OUTPUT_DIR = Path("../dist/")
RECORD_FILE = OUTPUT_DIR / "downloaded.json"
REPORT_FILE = OUTPUT_DIR / "report.txt"
README_FILE = Path("../README.md")
GITHUB_PROXY = "https://ghproxy.net"
PROXY_URLS = [
    "https://raw.githubusercontent.com/hookzof/socks5_list/refs/heads/master/proxy.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/refs/heads/main/proxies/protocols/socks5/data.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/SOCKS5_RAW.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/refs/heads/master/generated/socks5_proxies.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/refs/heads/master/socks5.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/refs/heads/master/socks5.txt",
]
TEST_URL = "http://httpbin.org/ip"


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def test_request(url: str, proxy: str, timeout: int = 5) -> bool:
    session = requests.Session()
    session.verify = False
    proxies = {"http": proxy, "https": proxy}
    resp = session.get(url, proxies=proxies, timeout=timeout)
    resp.raise_for_status()
    return True


def check_proxy(proxies: list[str]) -> list[str]:
    available_proxies: list[str] = []
    tested = 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(test_request, TEST_URL, p): p for p in proxies}
        for future in as_completed(futures):
            proxy = futures[future]
            tested += 1
            total = len(proxies)
            try:
                future.result()
                available_proxies.append(proxy)
                if len(available_proxies) >= 40:
                    break

            except Exception:
                logging.debug(f"Proxy failed: {proxy}")
            if tested % 60 == 0:
                logging.info(
                    f"Checked {tested}/{total}, available: {len(available_proxies)}"
                )
    logging.info(f"Get avaliable Proxy: {len(available_proxies)}")
    return available_proxies


def get_proxy_list() -> list[str]:
    proxies = []
    for PROXY_URL in PROXY_URLS:
        PROXY_URL = f"{GITHUB_PROXY}/{PROXY_URL}"
        resp = requests.get(PROXY_URL, timeout=30)
        resp.raise_for_status()
        proxy = [
            f"socks5://{line.strip()}"
            for line in resp.text.splitlines()
            if line.strip()
        ]
        logging.info(f"Fetching proxies from: {PROXY_URL}, {len(proxy)}")
        proxies.extend(proxy[:500])
    proxies = list(set(proxies))
    logging.info(f"Get All Proxy: {len(proxies)}")
    return check_proxy(proxies)


def run_collector(
    collector_name: str, proxy_list: list[str], output_dir: Path, record: DownloadRecord
):
    """运行单个采集器"""
    collector_cls = get_collector(collector_name)
    collector = collector_cls(proxy_list)
    return collector.run(output_dir, record)


def write_download_report(results: list[dict], report_file: Path):
    report_lines = []

    # 报告标题和时间
    report_lines.append("=" * 70)
    report_lines.append("DOWNLOAD REPORT".center(70))
    report_lines.append(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(70)
    )
    report_lines.append("=" * 70)

    total_sites = len(results)
    total_urls = sum(r["total_urls"] for r in results)
    total_new = sum(len(r["new_urls"]) for r in results)
    report_lines.append(
        f"Total sites: {total_sites}, Total URLs: {total_urls}, New URLs: {total_new}"
    )
    report_lines.append("-" * 70)

    # 按站点分组输出
    for r in sorted(results, key=lambda x: x["site"]):
        site = r["site"]
        total = r["total_urls"]
        new_count = len(r["new_urls"])
        status = r["result"]

        report_lines.append(
            f"[{site}] Status: {status}, Total URLs: {total}, New URLs: {new_count}"
        )
        if new_count:
            for u in sorted(r["new_urls"]):
                report_lines.append(f"    - {u}")
        report_lines.append("-" * 70)

    report_lines.append("=" * 70)

    # 写入文件
    report_file.write_text("\n".join(report_lines), encoding="utf-8")

    # 打印到控制台
    print("\n".join(report_lines))


def update_readme(
    output_dir: Path, readme_file: Path, github_prefix: str = GITHUB_PROXY
):
    """
    更新 README.md 中每日更新订阅部分
    """
    sites = [d.name for d in output_dir.iterdir() if d.is_dir()]

    # 构建每日更新订阅内容
    lines = ["\n## 每日更新订阅\n"]

    for site in sorted(sites):
        site_dir = output_dir / site
        clash_path = site_dir / "clash.yaml"
        v2ray_path = site_dir / "v2ray.txt"

        lines.append(f"### {site} 订阅链接\n")

        if clash_path.exists():
            lines.append("```shell")
            lines.append(
                f"{github_prefix}/https://raw.githubusercontent.com/cook369/proxy-collect/main/dist/{site}/clash.yaml"
            )
            lines.append("```")

        if v2ray_path.exists():
            lines.append("```shell")
            lines.append(
                f"{github_prefix}/https://raw.githubusercontent.com/cook369/proxy-collect/main/dist/{site}/v2ray.txt"
            )
            lines.append("```")

    lines.append("\n---\n")

    # 读取原 README 内容
    if readme_file.exists():
        content = readme_file.read_text(encoding="utf-8")
        # 删除原有每日更新订阅部分
        if "## 每日更新订阅" in content:
            content = content.split("## 每日更新订阅")[0].rstrip()
        content += "\n" + "\n".join(lines)
    else:
        content = "\n".join(lines)

    # 写入 README.md
    readme_file.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run a collector")
    parser.add_argument(
        "--site",
        nargs="*",
        choices=list_collectors(),
        help="Choose which site(s) to collect from. If empty, all sites are collected",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all supported collectors and exit",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of threads for concurrent collectors",
    )
    record = DownloadRecord(RECORD_FILE)
    args = parser.parse_args()
    if args.list:
        print("Supported collectors:")
        for name in list_collectors():
            print(f"  - {name}")
        return

    # 选择采集器列表
    if args.site and len(args.site) > 0:
        collectors_to_run = args.site
    else:
        collectors_to_run = list_collectors()

    logging.info(f"Collectors to run: {collectors_to_run}")

    proxy_list = get_proxy_list()

    # 使用 ThreadPoolExecutor 并发运行采集器
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_collector, name, proxy_list, OUTPUT_DIR, record): name
            for name in collectors_to_run
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()  # 返回 run_collector 的字典
                results.append(result)
            except Exception:
                results.append(
                    {
                        "site": name,
                        "total_urls": 0,
                        "new_urls": [],
                        "result": "failed",
                    }
                )
    write_download_report(results, REPORT_FILE)
    update_readme(OUTPUT_DIR, README_FILE, GITHUB_PROXY)


if __name__ == "__main__":
    main()
