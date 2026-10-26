#!/usr/bin/env python3
"""Build and maintain the Jellyfin plugin catalog.

The source of truth is plugins/<slug>/:
  plugin.json    plugin metadata (guid, name, targetAbi, upstream, license, ...)
  versions.json  published versions (version, targetAbi, checksum, timestamp)
  LICENSE        license of the plugin being redistributed

manifest.json and the plugin table in README.md are generated from those files.

Commands:
  catalog.py build            regenerate manifest.json and README.md
  catalog.py build --check    fail if they are out of date (used by CI)
  catalog.py add-version <slug> <version> <md5>
                              record a published version, then rebuild
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

REPO = "furyetti/jellyfin-plugins"
ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
MANIFEST = ROOT / "manifest.json"
README = ROOT / "README.md"
README_START = "<!-- plugins:start -->"
README_END = "<!-- plugins:end -->"

REQUIRED = ("guid", "name", "overview", "description", "owner", "category", "targetAbi", "upstream", "license", "changes")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
MD5_RE = re.compile(r"^[0-9a-f]{32}$")


def fail(message):
    print(f"catalog: {message}", file=sys.stderr)
    sys.exit(1)


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def release_tag(slug, version):
    return f"{slug}-{version}"


def zip_name(slug, version):
    return f"{slug}-{version}.zip"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(f"cannot read {path.relative_to(ROOT)}: {error}")


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def load_plugins():
    plugins = []
    guids = {}
    for folder in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        slug = folder.name
        if not SLUG_RE.match(slug):
            fail(f"plugin folder '{slug}' must be lowercase-hyphenated")
        meta = read_json(folder / "plugin.json")
        missing = [key for key in REQUIRED if not meta.get(key)]
        if missing:
            fail(f"{slug}/plugin.json is missing {', '.join(missing)}")
        if not GUID_RE.match(meta["guid"]):
            fail(f"{slug}/plugin.json guid must be a lowercase GUID")
        if meta["guid"] in guids:
            fail(f"{slug} and {guids[meta['guid']]} share guid {meta['guid']}")
        guids[meta["guid"]] = slug
        if not (folder / "LICENSE").is_file():
            fail(f"{slug}/LICENSE is required when redistributing a build")

        versions_path = folder / "versions.json"
        versions = read_json(versions_path) if versions_path.exists() else []
        seen = set()
        for entry in versions:
            if not VERSION_RE.match(entry.get("version", "")):
                fail(f"{slug}: bad version {entry.get('version')!r}")
            if entry["version"] in seen:
                fail(f"{slug}: version {entry['version']} is listed twice")
            seen.add(entry["version"])
            if not MD5_RE.match(entry.get("checksum", "")):
                fail(f"{slug} {entry['version']}: checksum must be an md5 hex digest")
        plugins.append((slug, meta, versions))
    return plugins


def build_manifest(plugins):
    manifest = []
    for slug, meta, versions in plugins:
        manifest.append({
            "guid": meta["guid"],
            "name": meta["name"],
            "overview": meta["overview"],
            "description": meta["description"],
            "owner": meta["owner"],
            "category": meta["category"],
            "versions": [
                {
                    "version": v["version"],
                    "changelog": f"https://github.com/{REPO}/releases/tag/{release_tag(slug, v['version'])}",
                    "targetAbi": v["targetAbi"],
                    "sourceUrl": f"https://github.com/{REPO}/releases/download/"
                                 f"{release_tag(slug, v['version'])}/{zip_name(slug, v['version'])}",
                    "checksum": v["checksum"],
                    "timestamp": v["timestamp"],
                }
                for v in sorted(versions, key=lambda v: version_key(v["version"]), reverse=True)
            ],
        })
    return json.dumps(manifest, indent=2) + "\n"


def build_readme(plugins):
    rows = ["| Plugin | Latest | Based on | License | Changes |", "|---|---|---|---|---|"]
    for slug, meta, versions in plugins:
        latest = max((v["version"] for v in versions), key=version_key, default="unreleased")
        upstream = meta["upstream"].removeprefix("https://github.com/")
        rows.append(
            f"| {meta['name']} | {latest} | [{upstream}]({meta['upstream']}) "
            f"| [{meta['license']}](plugins/{slug}/LICENSE) | {meta['changes']} |"
        )
    text = README.read_text(encoding="utf-8")
    start, end = text.find(README_START), text.find(README_END)
    if start < 0 or end < start:
        fail(f"README.md must contain {README_START} and {README_END}")
    return text[: start + len(README_START)] + "\n" + "\n".join(rows) + "\n" + text[end:]


def build(check):
    plugins = load_plugins()
    outputs = {MANIFEST: build_manifest(plugins), README: build_readme(plugins)}
    stale = [p.name for p, content in outputs.items()
             if not p.exists() or p.read_text(encoding="utf-8").replace("\r\n", "\n") != content]
    if check:
        if stale:
            fail(f"{', '.join(stale)} out of date; run scripts/catalog.py build")
        print("catalog: up to date")
        return
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8", newline="\n")
    print(f"catalog: built {len(plugins)} plugin(s)")


def add_version(slug, version, checksum):
    folder = PLUGINS / slug
    if not (folder / "plugin.json").is_file():
        fail(f"unknown plugin '{slug}'; create plugins/{slug}/plugin.json first")
    if not VERSION_RE.match(version) or not MD5_RE.match(checksum):
        fail("version must look like 0.0.0.27 and checksum must be an md5 hex digest")
    meta = read_json(folder / "plugin.json")
    path = folder / "versions.json"
    versions = [v for v in (read_json(path) if path.exists() else []) if v["version"] != version]
    versions.append({
        "version": version,
        "targetAbi": meta["targetAbi"],
        "checksum": checksum,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    versions.sort(key=lambda v: version_key(v["version"]), reverse=True)
    write_json(path, versions)
    build(check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build")
    build_cmd.add_argument("--check", action="store_true")
    add_cmd = commands.add_parser("add-version")
    add_cmd.add_argument("slug")
    add_cmd.add_argument("version")
    add_cmd.add_argument("checksum")
    args = parser.parse_args()

    if args.command == "build":
        build(args.check)
    else:
        add_version(args.slug, args.version, args.checksum)


if __name__ == "__main__":
    main()
