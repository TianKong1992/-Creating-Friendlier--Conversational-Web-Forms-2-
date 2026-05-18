# -*- coding: utf-8 -*-
"""
鼠标移动到指定文字并点击
==========================
功能：截取屏幕指定区域，OCR 识别指定文字，移动鼠标到文字位置并点击

用法（命令行）:
  python movemouse.py "树妖"                          # 全屏搜索"树妖"并点击
  python movemouse.py "树妖" --region 0 0 1920 1080   # 在指定区域搜索
  python movemouse.py "树妖" --no-click                # 只移动不点击（预览模式）
  python movemouse.py "树妖" --confidence 0.5          # 调高置信度阈值
  python movemouse.py "树妖" --y-offset 40             # 点击位置下移40像素

也可以作为模块导入:
  from movemouse import find_and_click
  find_and_click("树妖", region=(0, 0, 1920, 1080))
"""

import argparse     # 命令行参数解析
import time         # 延时
import random       # 随机偏移

import numpy as np
import pyautogui
import easyocr

# ========================== 全局 OCR 实例 ==========================

_ocr_reader = None  # 懒加载，第一次使用时初始化

def _get_ocr():
    """获取 OCR 实例（懒加载，首次调用会下载模型）"""
    global _ocr_reader
    if _ocr_reader is None:
        print("[OCR] 正在加载模型（首次运行需下载，约50-100MB）...")
        _ocr_reader = easyocr.Reader(["ch_sim"], gpu=True)
        print("[OCR] 模型就绪")
    return _ocr_reader

# ========================== 截图 ==========================

def capture(region=None):
    """
    截取屏幕画面
    参数:
        region: (left, top, width, height)，None 为全屏
    返回:
        numpy RGB 数组
    """
    if region is not None:
        left, top, width, height = region
        screenshot = pyautogui.screenshot(region=(left, top, width, height))
    else:
        screenshot = pyautogui.screenshot()
    return np.array(screenshot)

# ========================== 文字搜索 ==========================

def find_text(screen_image, target_text, confidence=0.3, min_text_height=12):
    """
    在画面中搜索指定文字，返回匹配位置的坐标列表
    参数:
        screen_image:   numpy RGB 图像数组
        target_text:    要搜索的文字
        confidence:     OCR 置信度阈值 (0~1)
        min_text_height: 最小文字高度（像素），过滤噪点
    返回:
        列表，每项 {"text", "center": (x,y), "confidence"}
        按置信度从高到低排序
    """
    reader = _get_ocr()

    # OCR 识别画面中所有文字
    results = reader.readtext(screen_image, detail=1, paragraph=False)

    matches = []
    for detection in results:
        if len(detection) < 3:
            continue

        box, text, conf = detection  # 解包：边界框、文字、置信度

        # 置信度过滤
        if conf < confidence:
            continue

        # 文字高度过滤
        text_height = abs(box[2][1] - box[0][1])
        if text_height < min_text_height:
            continue

        # 文字匹配（包含关系）
        text = text.strip()
        if not text or target_text not in text:
            continue

        # 计算文字中心点
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx = int(sum(xs) / len(xs))
        cy = int(sum(ys) / len(ys))

        matches.append({
            "text": text,                     # OCR 识别到的完整文字
            "center": (cx, cy),               # 文字中心坐标
            "confidence": round(conf, 3),     # 置信度
        })

    # 按置信度降序
    matches.sort(key=lambda x: x["confidence"], reverse=True)
    return matches

# ========================== 鼠标操作 ==========================

def move_and_click(x, y, y_offset=0, move_duration=(0.15, 0.3), click_delay=(0.08, 0.15)):
    """
    移动鼠标到指定坐标并点击
    参数:
        x, y:          目标坐标
        y_offset:      Y 轴额外下移量（文字在目标上方时使用）
        move_duration: 移动耗时范围（秒），随机取
        click_delay:   按下到释放的时长范围（秒），随机取
    """
    # 确保安全设置
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.01

    final_x = x + random.randint(-5, 5)       # X 随机微调
    final_y = y + y_offset + random.randint(-3, 3)  # Y 加上偏移和微调

    # 鼠标移动（先快后慢的缓动曲线）
    duration = random.uniform(*move_duration)
    pyautogui.moveTo(final_x, final_y, duration=duration, tween=pyautogui.easeOutQuad)

    # 点击
    hold_time = random.uniform(*click_delay)
    pyautogui.mouseDown(button="left")
    time.sleep(hold_time)
    pyautogui.mouseUp(button="left")

# ========================== 核心函数 ==========================

def find_and_click(target_text, region=None, confidence=0.3, y_offset=40, dry_run=False):
    """
    搜索指定文字并点击（一步到位）
    参数:
        target_text: 要搜索和点击的文字
        region:      搜索区域 (left, top, width, height)，None=全屏
        confidence:  OCR 置信度阈值
        y_offset:    点击位置 Y 轴下移像素（文字通常在被点目标上方）
        dry_run:     True=只移动鼠标不点击（预览模式）
    返回:
        True=找到并点击了, False=未找到
    """
    # 1. 截图
    region_desc = f"区域{region}" if region else "全屏"
    print(f"[截图] 正在截取画面 ({region_desc})...")
    screen = capture(region)

    # 2. OCR 搜索
    print(f"[搜索] 正在搜索文字: \"{target_text}\"")
    t0 = time.time()
    matches = find_text(screen, target_text, confidence=confidence)
    elapsed = time.time() - t0
    print(f"[搜索] 耗时 {elapsed:.1f}秒，找到 {len(matches)} 个匹配")

    if not matches:
        print(f"[结果] 未找到 \"{target_text}\"")
        return False

    # 3. 显示匹配结果
    for i, m in enumerate(matches[:5]):
        print(f"  {i+1}. \"{m['text']}\" 置信度={m['confidence']} 位置=({m['center'][0]},{m['center'][1]})")

    # 4. 取置信度最高的，移动并点击
    best = matches[0]
    cx, cy = best["center"]

    # 如果截了局部区域，坐标要加上区域偏移
    if region is not None:
        cx += region[0]  # 加上 left
        cy += region[1]  # 加上 top

    print(f"[点击] 最佳匹配: \"{best['text']}\" 置信度={best['confidence']}")
    print(f"[点击] 鼠标移动到 ({cx}, {cy})，Y下移{y_offset}px")

    if dry_run:
        # 预览模式：只移动不点击
        pyautogui.moveTo(cx, cy + y_offset, duration=0.3)
        print("[预览] 已移动鼠标到目标位置（未点击）")
    else:
        move_and_click(cx, cy, y_offset=y_offset)
        print("[点击] 点击完成")

    return True

# ========================== 命令行入口 ==========================

def main():
    parser = argparse.ArgumentParser(
        description="在屏幕指定范围搜索文字并将鼠标移动过去点击",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python movemouse.py "树妖"                        全屏搜索"树妖"并点击
  python movemouse.py "树妖" -r 0 0 1920 1080       在区域(0,0,1920,1080)搜索
  python movemouse.py "树妖" --no-click             只移动不点击（预览）
  python movemouse.py "树妖" -c 0.5 -y 50           置信度0.5，下移50px
        """,
    )

    parser.add_argument("text", help="要搜索的文字（例如: 树妖）")
    parser.add_argument(
        "-r", "--region", nargs=4, type=int, metavar=("LEFT", "TOP", "WIDTH", "HEIGHT"),
        help="搜索区域（左上X 左上Y 宽度 高度），不指定则全屏搜索",
    )
    parser.add_argument(
        "-c", "--confidence", type=float, default=0.3,
        help="OCR 置信度阈值，默认 0.3（游戏文字建议 0.25~0.4）",
    )
    parser.add_argument(
        "-y", "--y-offset", type=int, default=40,
        help="点击位置向下偏移像素数，默认 40（文字在目标上方时使用）",
    )
    parser.add_argument(
        "--no-click", action="store_true",
        help="预览模式：只移动鼠标到目标位置，不点击",
    )

    args = parser.parse_args()

    # 处理 region 参数
    region = None
    if args.region is not None:
        region = tuple(args.region)

    # 执行
    success = find_and_click(
        target_text=args.text,
        region=region,
        confidence=args.confidence,
        y_offset=args.y_offset,
        dry_run=args.no_click,
    )

    if not success:
        print("[退出] 未找到目标文字")

if __name__ == "__main__":
    main()
