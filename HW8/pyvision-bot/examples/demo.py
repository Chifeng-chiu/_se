"""pyvision-bot 範例：從終端機實際跑一次找圖流程。

用法：
    python examples/demo.py matcher
    python examples/demo.py screen
    python examples/demo.py find button.png
    python examples/demo.py click button.png --yes
    python examples/demo.py adb --serial emulator-5554
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from pyvision_bot import TemplateMatcher, VisionBot


def cmd_matcher(_args: argparse.Namespace) -> int:
    """用合成圖片測試找圖，不會控制滑鼠。"""

    rng = np.random.default_rng(42)
    screen = rng.integers(0, 256, (240, 320, 3), dtype=np.uint8)
    template = screen[80:120, 150:210].copy()

    result = TemplateMatcher(threshold=0.9).find(screen, template)
    if result is None:
        print("找不到模板")
        return 1

    print("螢幕尺寸:", screen.shape)
    print("匹配框:", (result.x, result.y, result.width, result.height))
    print("中心點:", result.center)
    print("信心:", round(result.confidence, 4))
    return 0


def cmd_screen(args: argparse.Namespace) -> int:
    """抓取桌面截圖並存檔。"""

    bot = VisionBot(mode="desktop")
    screen = bot.screenshot()
    output = Path(args.output)
    cv2.imwrite(str(output), screen)
    print("已儲存桌面截圖:", output.resolve())
    print("尺寸:", screen.shape)
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    """在桌面上尋找模板，只印出座標，不點擊。"""

    bot = VisionBot(mode="desktop")
    result = bot.find(args.template, threshold=args.threshold)
    if result is None:
        print("找不到:", args.template)
        return 1

    print("找到:", (result.x, result.y, result.width, result.height))
    print("中心點:", result.center)
    print("信心:", round(result.confidence, 4))
    return 0


def cmd_click(args: argparse.Namespace) -> int:
    """在桌面上尋找模板並點擊；預設只預演，加 --yes 才會真的點。"""

    bot = VisionBot(mode="desktop")
    result = bot.find(args.template, threshold=args.threshold)
    if result is None:
        print("找不到:", args.template)
        return 1

    print("找到:", result.center, "信心:", round(result.confidence, 4))
    if not args.yes:
        print("目前是預演模式；加上 --yes 才會真的點擊。")
        return 0

    bot.click(*result.center, jitter=args.jitter)
    print("已點擊:", result.center)
    return 0


def cmd_adb(args: argparse.Namespace) -> int:
    """抓取 Android 裝置截圖並存檔。"""

    bot = VisionBot(mode="adb", device_serial=args.serial)
    screen = bot.screenshot()
    output = Path(args.output)
    cv2.imwrite(str(output), screen)
    print("已儲存 Android 截圖:", output.resolve())
    print("尺寸:", screen.shape)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="pyvision-bot 範例：合成找圖、桌面截圖、ADB 截圖"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    matcher = subparsers.add_parser(
        "matcher", help="用合成圖片測試找圖（安全，不控制滑鼠）"
    )
    matcher.set_defaults(func=cmd_matcher)

    screen = subparsers.add_parser("screen", help="抓取桌面截圖並存檔")
    screen.add_argument("--output", default="desktop.png")
    screen.set_defaults(func=cmd_screen)

    find = subparsers.add_parser("find", help="在桌面上尋找模板（不點擊）")
    find.add_argument("template", help="模板圖片路徑")
    find.add_argument("--threshold", type=float, default=0.85)
    find.set_defaults(func=cmd_find)

    click = subparsers.add_parser("click", help="在桌面上尋找模板並點擊")
    click.add_argument("template", help="模板圖片路徑")
    click.add_argument("--threshold", type=float, default=0.85)
    click.add_argument("--jitter", type=int, default=3)
    click.add_argument(
        "--yes",
        action="store_true",
        help="真的執行點擊；沒有這個旗標時只預演",
    )
    click.set_defaults(func=cmd_click)

    adb = subparsers.add_parser("adb", help="抓取 Android 截圖並存檔")
    adb.add_argument("--serial", default=None, help="ADB 裝置序號")
    adb.add_argument("--output", default="android.png")
    adb.set_defaults(func=cmd_adb)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
