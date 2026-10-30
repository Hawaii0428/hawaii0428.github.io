#!/usr/bin/env python3
"""将树洞导出的 comments 转为小纸条网页的卡片 JSON。仅使用 Python 标准库。"""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
BEIJING = timezone(timedelta(hours=8))
COLLECTIONS = ("c1", "c2", "c3")


def nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("必须是非负整数")
    return number


def parse_after(value):
    """未带时区的日期、时间按北京时间解释；日期取当天零点。"""
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T].+)?", value):
            raise ValueError
        date = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "时间格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]，例如 '2026-04-28 23:59:59'"
        ) from exc
    if date.tzinfo is None:
        date = date.replace(tzinfo=BEIJING)
    return date.astimezone(BEIJING)


def iter_comments(value):
    """导出文件的评论嵌套在多层分页列表里，不递归进入 quote。"""
    if isinstance(value, list):
        for item in value:
            yield from iter_comments(item)
    elif isinstance(value, dict):
        yield value
    else:
        raise ValueError("comments 中只能包含评论对象或分页列表")


def normalize_paragraphs(text):
    # 网页按两个换行拆段，并去掉段内的单换行，所以需转换源文中的单换行。
    return "\n\n".join(line.strip() for line in text.splitlines() if line.strip())


def convert(data, min_length=50, summary_length=15, after=None):
    if not isinstance(data, dict) or "comments" not in data:
        raise ValueError("源文件必须是包含 comments 字段的 JSON 对象")
    if not isinstance(data["comments"], list):
        raise ValueError("comments 字段必须是列表")

    stats = {"total": 0, "other_authors": 0, "short": 0, "duplicates": 0, "before_cutoff": 0}
    cutoff = after.timestamp() if after is not None else None
    records = []
    seen = {}
    for comment in iter_comments(data["comments"]):
        stats["total"] += 1
        if comment.get("name") != "洞主":
            stats["other_authors"] += 1
            continue
        cid = comment.get("cid")
        if type(cid) is not int or cid < 0:
            raise ValueError("洞主评论缺少有效的整数 cid")
        text = comment.get("text")
        if not isinstance(text, str):
            raise ValueError(f"评论 {cid} 的 text 必须是字符串")
        timestamp = comment.get("timestamp")
        if type(timestamp) is not int:
            raise ValueError(f"评论 {cid} 的 timestamp 必须是秒级整数时间戳")

        # 同一条评论可能在分页中重复出现；内容冲突时停止，避免丢失数据。
        signature = (text, timestamp)
        if cid in seen:
            if seen[cid] != signature:
                raise ValueError(f"评论 {cid} 重复出现，且正文或时间不同")
            stats["duplicates"] += 1
            continue
        seen[cid] = signature

        # “之后”不含指定时刻；直接比较秒级时间戳，保留精确时间边界。
        if cutoff is not None and timestamp <= cutoff:
            stats["before_cutoff"] += 1
            continue

        full_content = normalize_paragraphs(text)
        if not full_content or len(re.sub(r"\s+", "", full_content)) < min_length:
            stats["short"] += 1
            continue
        try:
            date = datetime.fromtimestamp(timestamp, BEIJING)
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError(f"评论 {cid} 的时间戳超出有效范围") from exc

        preview = re.sub(r"\s+", " ", full_content).strip()
        if summary_length == 0:
            preview = ""
        elif len(preview) > summary_length:
            preview = preview[:summary_length] + "..."
        card = {
            "title": date.strftime("%Y.%m.%d"),
            "content": preview,
            "fullContent": full_content,
        }
        records.append((timestamp, cid, date.strftime("%Y%m%d"), card))

    # 时间相同则按 cid 排序，确保重复运行时文件名和目录分配保持一致。
    records.sort(key=lambda item: (item[0], item[1]))
    cards = []
    for index, (_, cid, date, card) in enumerate(records):
        # cid 保证同一天有多篇文章时不会互相覆盖。
        relative_path = Path(COLLECTIONS[index % len(COLLECTIONS)]) / f"{date}_{cid}.json"
        cards.append((relative_path, card))
    return cards, stats


def plan_additions(output, cards, overwrite=False):
    """跨三个目录检查 ID 和正文，保留已有卡片，只分配本次新增的卡片。"""
    existing_ids = {}
    existing_texts = set()
    for collection in COLLECTIONS:
        for target in sorted((output / collection).glob("*.json")):
            if not target.is_file():
                continue
            existing = json.loads(target.read_text(encoding="utf-8-sig"))
            if not isinstance(existing, dict) or not isinstance(existing.get("fullContent"), str):
                raise ValueError(f"已有卡片缺少有效的 fullContent：{target}")
            existing_texts.add(re.sub(r"\s+", "", existing["fullContent"]))
            match = re.fullmatch(r"\d{8}_(\d+)\.json", target.name)
            if match:
                existing_ids.setdefault(int(match[1]), (target.relative_to(output), existing))

    planned = []
    skipped = updated = added = 0
    for relative_path, card in cards:
        cid = int(relative_path.stem.split("_")[-1])
        text_key = re.sub(r"\s+", "", card["fullContent"])
        if cid in existing_ids:
            old_path, existing = existing_ids[cid]
            if overwrite and existing != card:
                planned.append((old_path, card))
                updated += 1
            else:
                skipped += 1
            continue
        if text_key in existing_texts:
            # 兼容旧文章的日期文件名、随机文件名及不同的段落换行方式。
            skipped += 1
            continue
        target = Path(COLLECTIONS[added % len(COLLECTIONS)]) / relative_path.name
        planned.append((target, card))
        existing_ids[cid] = (target, card)
        existing_texts.add(text_key)
        added += 1
    return planned, skipped, added, updated


def write_cards(output, cards, overwrite=False):
    # 先检查所有目标，避免遇到冲突时已经写入部分卡片。
    for relative_path, card in cards:
        target = output / relative_path
        if target.exists():
            try:
                existing = json.loads(target.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError):
                existing = None
            if existing != card and not overwrite:
                raise ValueError(f"目标文件已存在且内容不同：{target}；请换输出目录或使用 --overwrite")

    for relative_path, card in cards:
        target = output / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(card, ensure_ascii=False, indent=4) + "\n",
                          encoding="utf-8", newline="\n")

    # 读取目录里的全部 JSON，保留已有文章的索引；不带 BOM，避免 fetch 读到隐藏字符。
    for collection in COLLECTIONS:
        folder = output / collection
        folder.mkdir(parents=True, exist_ok=True)
        names = sorted(p.name for p in folder.glob("*.json") if p.is_file())
        (folder / "filelist.txt").write_text("\n".join(names), encoding="utf-8", newline="\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path,
                        default=ROOT / "setting" / "6740010-1-165.json", help="源 JSON 路径")
    parser.add_argument("--output", type=Path, default=ROOT / "setting" / "tx",
                        help="输出目录，默认直接追加到现有 setting/tx/c1、c2、c3")
    parser.add_argument("--min-length", type=nonnegative_int, default=50,
                        help="洞主正文的最少非空白字符数，默认 50，0 表示保留全部非空正文")
    parser.add_argument("--summary-length", type=nonnegative_int, default=15,
                        help="摘要最多保留的字符数（不含省略号），默认 15，0 表示不生成摘要")
    parser.add_argument("--after", type=parse_after, metavar="TIME",
                        default=parse_after("2026-05-01 00:00:00"),
                        help="仅导出严格晚于此时刻的评论；日期或日期加时间，默认北京时间")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写文件")
    parser.add_argument("--overwrite", action="store_true", help="允许更新同一评论 ID 的已有卡片，默认保留已有内容")
    args = parser.parse_args(argv)

    try:
        data = json.loads(args.source.read_text(encoding="utf-8-sig"))
        candidates, stats = convert(data, args.min_length, args.summary_length, after=args.after)
        cards, skipped, added, updated = plan_additions(args.output, candidates, args.overwrite)
        if cards and not args.dry_run:
            write_cards(args.output, cards, args.overwrite)
    except (OSError, ValueError, RecursionError) as exc:
        print(f"转换失败：{exc}", file=sys.stderr)
        return 1

    print(f"扫描 {stats['total']} 条评论；跳过其他作者 {stats['other_authors']} 条，"
          f"短文或空文 {stats['short']} 条，重复评论 {stats['duplicates']} 条，"
          f"不晚于指定时间 {stats['before_cutoff']} 条。")
    if args.after is not None:
        print(f"时间条件：发布时间 > {args.after.isoformat(sep=' ')}（北京时间）")
    print(f"符合筛选 {len(candidates)} 张，跳过已有卡片 {skipped} 张。")
    print(f"{'预计' if args.dry_run else '已'}新增 {added} 张，更新 {updated} 张：")
    for collection in COLLECTIONS:
        count = sum(path.parts[0] == collection for path, _ in cards)
        print(f"  {collection}: {count}")
    if not cards:
        print("没有需要新增或更新的卡片，未写入文件。")
    elif not args.dry_run:
        print(f"输出目录：{args.output.resolve()}（已更新各目录的 filelist.txt）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
