import argparse
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collectors.base import BaseCollector, DownloadRecord

OUTPUT_DIR = Path("../dist/")
RECORD_FILE = OUTPUT_DIR / "downloaded.json"
REPORT_FILE = OUTPUT_DIR / "report.txt"
README_FILE = Path("../README.md")
PROXY_PREFIX = "https://ghproxy.net"


def run_collector(collector_name: str, output_dir: Path, record: DownloadRecord):
    """运行单个采集器"""
    collector_cls = BaseCollector.get_collector(collector_name)
    collector = collector_cls()
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
    output_dir: Path, readme_file: Path, proxy_prefix: str = PROXY_PREFIX
):
    """
    更新 README.md 中每日更新订阅部分
    """
    sites = [d.name for d in output_dir.iterdir() if d.is_dir()]

    # 构建每日更新订阅内容
    lines = ["---", "\n## 每日更新订阅\n"]

    for site in sorted(sites):
        site_dir = output_dir / site
        clash_path = site_dir / "clash.yaml"
        v2ray_path = site_dir / "v2ray.txt"

        lines.append(f"### {site} 订阅链接\n")

        if clash_path.exists():
            lines.append("```shell")
            lines.append(
                f"{proxy_prefix}/https://raw.githubusercontent.com/cook369/proxy-collect/main/dist/{site}/clash.yaml"
            )
            lines.append("```")

        if v2ray_path.exists():
            lines.append("```shell")
            lines.append(
                f"{proxy_prefix}/https://raw.githubusercontent.com/cook369/proxy-collect/main/dist/{site}/v2ray.txt"
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
        choices=BaseCollector.list_collectors(),
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
        for name in BaseCollector.list_collectors():
            print(f"  - {name}")
        return

    # 选择采集器列表
    if args.site and len(args.site) > 0:
        collectors_to_run = args.site
    else:
        collectors_to_run = BaseCollector.list_collectors()
    # 使用 ThreadPoolExecutor 并发运行采集器
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_collector, name, OUTPUT_DIR, record): name
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
    update_readme(OUTPUT_DIR, README_FILE, PROXY_PREFIX)


if __name__ == "__main__":
    main()
