"""只读查询 PyPI 安全公告；须在已安装 requirements.txt 的隔离环境运行。

包含安装环境的传递依赖，不上传项目文件或配置。查询失败返回非零，不当作无漏洞。
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib.metadata import distributions
import json
from pathlib import Path
import urllib.request


def check(package):
    name, version = package
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.load(response)
        return {"name": name, "version": version, "advisories": [
            {"id": item["id"], "aliases": item.get("aliases", []),
             "fixed_in": item.get("fixed_in", []), "link": item.get("link")}
            for item in data.get("vulnerabilities", []) if not item.get("withdrawn")
        ]}
    except Exception as error:
        return {"name": name, "version": version, "error": type(error).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    packages = sorted({(d.metadata["Name"], d.version) for d in distributions()})
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(check, packages))
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "source": "PyPI version JSON vulnerabilities", "packages": results}
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    affected = [p for p in results if p.get("advisories") or p.get("error")]
    print(json.dumps({"checked": len(results), "issues": affected}, ensure_ascii=False, indent=2))
    return 1 if affected else 0


if __name__ == "__main__":
    raise SystemExit(main())
