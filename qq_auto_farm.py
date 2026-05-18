# -*- coding: utf-8 -*-
"""
QQ幻想 自动打怪脚本（技术学习用途）
====================================
说明：本脚本仅供学习 Python 自动化技术（OCR文字识别、鼠标控制、状态检测）使用。
      在线上游戏中使用可能违反用户协议，导致账号被处罚，请仅用于单机或私服学习环境。
启动：python qq_auto_farm.py
停止：按 F8 紧急停止
"""

import time         # 延时等待
import random       # 随机数，用于模拟人类操作间隔，降低检测风险
import threading    # 多线程，让热键监听与主循环同时运行

import numpy as np              # 数值计算，配合图像处理
import pyautogui                # 屏幕截图、鼠标移动点击、屏幕尺寸获取
import easyocr                  # OCR 文字识别，从游戏画面中识别怪物名字
import keyboard                 # 全局热键监听（按 F8 停止脚本）

# ========================== 可配置参数区 ==========================
# 根据你的实际环境修改以下参数

CONFIG = {
    # ========== 屏幕 & 窗口（在这里填你的游戏分辨率） ==========
    # window_region 定义了游戏画面在屏幕上的位置和大小
    # 格式: (左上角X, 左上角Y, 画面宽度, 画面高度)
    # 全屏模式填 None；窗口模式示例: (0, 0, 1920, 1080)
    # ↓↓↓ 如果你的游戏是 1920x1080 全屏，填 None 即可 ↓↓↓
    "window_region": (160,90,160,880),          # ← 这里填窗口区域，None=全屏
    # ↑↑↑ 窗口模式示例: (100, 50, 1280, 720) ↑↑↑
    # ↑↑↑ 意思是游戏窗口左上角在屏幕(100,50)位置，窗口宽1280高720 ↑↑↑

    # ========== 怪物名字列表（必须配置） ==========
    # 把游戏里要打的怪物名字写在这里，用中文引号括起来，逗号分隔
    # 示例: ["小妖", "树精", "野狼", "骷髅兵"]
    "monster_names": ["树妖"],            # ← 这里填怪物名字，如 ["小妖", "树精"]
    "name_match_mode": "contains",  # 匹配模式: "exact"=完全一致, "contains"=包含即可
                                    # contains 模式下，"树精" 可以匹配 "树精·精英"

    # ========== OCR 识别参数 ==========
    "ocr_languages": ["ch_sim"],    # OCR 语言: ["ch_sim"]=简体中文, ["en"]=英文
                                    # 可同时支持中英文: ["ch_sim", "en"]
    "ocr_min_confidence": 0.3,      # OCR 文字置信度最低阈值 (0~1)，低于此值的识别结果被丢弃
                                    # 游戏字体可能比较花哨，阈值不宜太高，0.25~0.35 为佳
    "ocr_gpu": True,                # 是否启用 GPU 加速（有 NVIDIA 显卡保持 True）
    "ocr_text_height_min": 14,      # 识别出的文字最小高度（像素），1760x970下名字约20-35px

    # ========== 鼠标操作 ==========
    "click_delay": (0.08, 0.18),    # 点击按下到释放的间隔范围（秒），随机取中间值模拟人类
    "move_duration": (0.15, 0.35),  # 鼠标移动到目标的时间范围（秒）
    "click_offset_range": (-8, 8),  # 点击位置随机偏移像素范围，避免每次都点同一个坐标
    "click_y_offset": (35, 55),     # Y轴额外偏移（像素），名字在怪物头顶，需要往下点
                                    # 随机取 35~55px，确保点击在怪物身体上而不是名字标签

    # ========== 战斗判断 ==========
    "attack_timeout": 8.0,          # 单次攻击最大等待时间（秒），超时认为怪物已死或卡住
                                    # 调大一点给角色足够时间打死怪物
    "death_ocr_interval": 2.0,      # 死亡检测：每隔多少秒用 OCR 扫一次看名字还在不在
                                    # 全屏 OCR 较慢（1-3秒），间隔不宜太短

    # ========== 技能栏 ==========
    "skill_slots": [],              # 技能快捷键列表，按顺序释放，如 ["1", "2", "3"]
                                    # 留空则只用鼠标左键普通攻击

    # ========== 循环控制 ==========
    "search_interval": (0.3, 0.6),  # 每次搜索怪物后的等待间隔（秒），随机化避免太规律
    "after_kill_delay": (0.5, 1.0), # 怪物死亡后的停顿（秒）
    "max_loops": 0,                 # 最大循环次数，0 表示无限循环
    "pause_hotkey": "f7",           # 暂停/恢复 快捷键
    "stop_hotkey": "f8",            # 紧急停止 快捷键
}

# ========================== 全局状态 ==========================

class State:
    """全局运行状态，线程安全"""
    def __init__(self):
        self.running = True         # 主循环是否继续运行
        self.paused = False         # 是否暂停
        self.lock = threading.Lock()  # 线程锁，保证多线程读写安全

    def is_running(self):
        """检查是否应该继续运行（未停止且未暂停）"""
        with self.lock:
            return self.running and not self.paused

    def is_stopped(self):
        """检查是否已完全停止"""
        with self.lock:
            return not self.running

    def set_running(self, value):
        """设置运行状态"""
        with self.lock:
            self.running = value

    def set_paused(self, value):
        """设置暂停状态"""
        with self.lock:
            self.paused = value

state = State()  # 全局状态实例

# ========================== 全局变量 ==========================

ocr_reader = None  # OCR 阅读器实例，初始化一次后全局复用（easyocr 加载模型很慢）

# ========================== 初始化 ==========================

def init_pyautogui():
    """初始化 pyautogui 安全设置"""
    pyautogui.FAILSAFE = True       # 鼠标移动到屏幕左上角 (0,0) 时立即抛出异常，作为紧急停止手段
    pyautogui.PAUSE = 0.01          # 每次 pyautogui 操作后的最小暂停（秒），避免操作过快
    # 获取屏幕实际分辨率并打印
    screen_w, screen_h = pyautogui.size()
    print(f"[初始化] 屏幕实际分辨率: {screen_w} x {screen_h}")
    # 如果配置了窗口区域，提示实际的游戏画面大小
    region = CONFIG["window_region"]
    if region is not None:
        print(f"[初始化] 游戏窗口区域: 左上({region[0]},{region[1]}) 宽{region[2]} 高{region[3]}")
    else:
        print(f"[初始化] 游戏画面: 全屏 ({screen_w}x{screen_h})")

def init_ocr():
    """初始化 OCR 阅读器（只需执行一次，首次会下载模型文件，耗时较长）"""
    global ocr_reader
    langs = CONFIG["ocr_languages"]
    gpu = CONFIG["ocr_gpu"]
    print(f"[OCR] 正在加载 OCR 模型，语言: {langs}，GPU: {gpu}")
    print(f"[OCR] 首次运行会下载模型文件（约 50-100MB），请耐心等待...")
    # 初始化 easyocr Reader，加载中英文识别模型
    ocr_reader = easyocr.Reader(langs, gpu=gpu)
    print(f"[OCR] 模型加载完成")

# ========================== 屏幕截图 ==========================

def capture_game_region():
    """截取游戏画面区域，返回 numpy RGB 图像数组（easyocr 需要 RGB 格式）"""
    region = CONFIG["window_region"]

    if region is not None:
        # 窗口模式：截取指定区域 (left, top, width, height)
        left, top, width, height = region
        # 使用 pyautogui 截取指定区域
        screenshot = pyautogui.screenshot(region=(left, top, width, height))
    else:
        # 全屏模式：截取整个屏幕
        screenshot = pyautogui.screenshot()

    # 将 PIL Image 转为 numpy RGB 数组（easyocr 需要 RGB 格式）
    rgb_image = np.array(screenshot)
    return rgb_image

# ========================== 怪物检测（OCR 文字识别） ==========================

def find_monsters_by_name(screen_image):
    """
    对屏幕进行 OCR 文字识别，找到所有匹配怪物名字的文本位置
    参数:
        screen_image: numpy RGB 图像数组
    返回:
        (monsters, ocr_time): monsters列表, ocr耗时(秒)
    """
    global ocr_reader
    if ocr_reader is None:
        print("[错误] OCR 未初始化")
        return [], 0

    target_names = CONFIG["monster_names"]
    if not target_names:
        print("[错误] 请在 CONFIG['monster_names'] 中填写要识别的怪物名字")
        return [], 0

    mode = CONFIG["name_match_mode"]
    min_conf = CONFIG["ocr_min_confidence"]
    min_text_height = CONFIG["ocr_text_height_min"]

    # 调用 easyocr 对画面进行文字识别
    # detail=1 返回详细信息列表，每项: (边界框, 文字, 置信度)
    # paragraph=False 逐行识别，适合游戏中的名字标签
    ocr_start = time.time()  # 记录 OCR 开始时间
    results = ocr_reader.readtext(screen_image, detail=1, paragraph=False)
    ocr_elapsed = time.time() - ocr_start  # OCR 耗时

    monsters = []
    for detection in results:
        if len(detection) < 3:
            continue  # 跳过格式异常的结果

        box, text, confidence = detection  # 解包：边界框坐标、识别文字、置信度

        # 用置信度过滤低质量的识别结果
        if confidence < min_conf:
            continue

        # 用文字高度过滤太小的噪点（游戏怪物名字通常有一定高度）
        # box 是四个角的坐标 [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
        text_height = abs(box[2][1] - box[0][1])  # 左下角Y - 左上角Y = 文字高度
        if text_height < min_text_height:
            continue

        # 去掉文本两端的空白字符
        text = text.strip()
        if not text:
            continue

        # 检查识别出的文字是否包含目标怪物名字
        matched_name = None
        for name in target_names:
            if mode == "exact":
                # 精确匹配：识别文字必须完全等于怪物名字
                if text == name:
                    matched_name = name
                    break
            else:
                # contains 模式：识别文字中包含怪物名字即可
                if name in text:
                    matched_name = name
                    break

        if matched_name is None:
            continue  # 不匹配任何目标怪物名字，跳过

        # 计算文字边界框的中心点坐标（用于鼠标点击）
        # box 顺序: [左上, 右上, 右下, 左下]（或类似顺序，因 OCR 引擎而定）
        xs = [p[0] for p in box]  # 所有角点的 X 坐标
        ys = [p[1] for p in box]  # 所有角点的 Y 坐标
        center_x = int(sum(xs) / len(xs))  # 中心 X = 所有 X 的平均值
        center_y = int(sum(ys) / len(ys))  # 中心 Y = 所有 Y 的平均值

        # 记录识别到的怪物信息
        monsters.append({
            "name": text,                       # OCR 识别到的原始文字
            "matched_name": matched_name,       # 匹配到的怪物名字
            "center": (center_x, center_y),     # 文字中心（点击目标坐标）
            "confidence": round(confidence, 3), # 识别置信度
            "box": box,                         # 文字边界框
        })

    # 按置信度从高到低排序，优先攻击识别最清晰的目标
    monsters.sort(key=lambda x: x["confidence"], reverse=True)
    return monsters, ocr_elapsed  # 返回怪物列表和 OCR 耗时（秒）

# ========================== 鼠标操作 ==========================

def click_monster(target_x, target_y):
    """移动鼠标到目标位置并点击左键攻击"""
    move_min, move_max = CONFIG["move_duration"]
    click_min, click_max = CONFIG["click_delay"]
    offset_min, offset_max = CONFIG["click_offset_range"]
    y_offset_min, y_offset_max = CONFIG["click_y_offset"]

    # 在目标位置基础上添加随机偏移，模拟人类操作的不精确性
    offset_x = random.randint(offset_min, offset_max)
    offset_y = random.randint(offset_min, offset_max)
    # Y 轴额外下移：怪物名字在头顶，需要点击名字下方才是怪物身体
    body_y_offset = random.randint(y_offset_min, y_offset_max)
    final_x = target_x + offset_x
    final_y = target_y + offset_y + body_y_offset

    # 计算移动耗时（秒），随机值让行为节奏不规律
    duration = random.uniform(move_min, move_max)

    # 使用缓动方式移动鼠标到目标位置
    # pyautogui.easeOutQuad：先快后慢的移动曲线，更像人类手部动作
    pyautogui.moveTo(final_x, final_y, duration=duration, tween=pyautogui.easeOutQuad)

    # 短暂随机停顿，模拟鼠标定位后的视觉确认反应时间
    time.sleep(random.uniform(0.03, 0.08))

    # 按下鼠标左键
    pyautogui.mouseDown(button="left")

    # 随机按下持续时间（秒），模拟点击动作的自然差异
    hold_time = random.uniform(click_min, click_max)
    time.sleep(hold_time)

    # 释放鼠标左键
    pyautogui.mouseUp(button="left")

def use_skills():
    """按顺序使用技能快捷键"""
    for key in CONFIG["skill_slots"]:
        if not state.is_running():
            return  # 已被用户停止，中断技能释放
        # 按下技能快捷键
        pyautogui.press(key)
        # 技能之间加一个很小的间隔防止按键冲突
        time.sleep(random.uniform(0.05, 0.12))

# ========================== 战斗状态判断 ==========================

def is_current_target_dead():
    """
    检测当前攻击目标是否已死亡，通过 OCR 检查目标名字是否还存在
    思路：点击怪物后，游戏通常会显示目标血条和名字。如果 OCR 再识别不到
          该怪物的名字，说明目标已死亡或丢失。
    返回: True=怪物已死/丢失, False=还在战斗中
    """
    global ocr_reader
    if ocr_reader is None:
        return False  # OCR 不可用时跳过检测，交给超时机制处理

    # 截取当前画面
    screen = capture_game_region()

    # 对当前画面进行 OCR，看是否还有匹配的怪物名字
    # 这里复用 find_monsters_by_name，检测是否有任何目标怪物还在画面上
    alive, _ = find_monsters_by_name(screen)  # 解包元组，不需要 OCR 耗时

    # 如果找不到任何匹配的怪物名字，认为当前目标已死亡
    # 注意：这依赖于同一时间画面上通常不会有大量同名怪物在屏幕外的情况
    return len(alive) == 0

def wait_for_combat_end(timeout):
    """
    等待战斗结束（怪物死亡或被打断），通过定时 OCR 检测怪物名字是否消失
    策略：主要靠超时兜底，OCR 作为提前结束的优化手段（间隔较长，因为全屏 OCR 慢）
    返回: "dead"=怪物已死, "timeout"=超时, "stopped"=用户停止
    """
    start_time = time.time()
    check_interval = CONFIG["death_ocr_interval"]  # OCR 检测间隔（秒）

    while time.time() - start_time < timeout:
        # 检查是否被用户停止或暂停
        if not state.is_running():
            return "stopped"

        # 先等待一段时间，再执行 OCR 检测
        # OCR 本身耗时 1-3 秒，所以实际间隔 = sleep时间 + OCR耗时
        time.sleep(check_interval)

        # 用 OCR 检测怪物名字是否消失（消失=死亡）
        # 注意：全屏 OCR 较慢（1-3秒/次），这是我们不做高频检测的原因
        if is_current_target_dead():
            return "dead"

    # 超时：可能怪物血量太高、角色输出不够、或角色被卡住
    return "timeout"

# ========================== 主循环 ==========================

def farming_loop():
    """主循环：找怪(OCR) -> 点击攻击 -> 等待战斗结束 -> 再次找怪"""
    loop_count = 0
    max_loops = CONFIG["max_loops"]

    print("\n[开始] 自动打怪已启动（按 F8 紧急停止，按 F7 暂停/恢复）\n")
    print(f"[目标] 追踪怪物: {', '.join(CONFIG['monster_names'])}")

    while state.is_running():  # 外层循环：只要没停止就一直跑
        # 如果设置了最大循环次数，达到后退出
        if max_loops > 0 and loop_count >= max_loops:
            print(f"[完成] 已达到最大循环次数 {max_loops}，退出")
            break

        loop_count += 1
        print(f"\n--- 第 {loop_count} 轮 ---")

        # ---- 第1步：截取游戏画面 ----
        print("[截图] 正在截取游戏画面...")
        screen = capture_game_region()

        # ---- 第2步：用 OCR 识别画面中的怪物名字 ----
        print("[搜索] 正在 OCR 识别怪物名字...")
        monsters, ocr_elapsed = find_monsters_by_name(screen)  # 返回怪物列表和 OCR 耗时

        if not monsters:
            # 打印未找到时的详细信息，方便调试
            wait_time = random.uniform(*CONFIG["search_interval"])
            print(f"[结果] 未找到怪物，{wait_time:.1f}秒后重新搜索...")
            time.sleep(wait_time)
            continue

        print(f"[结果] 找到 {len(monsters)} 个怪物目标 (OCR耗时 {ocr_elapsed:.1f}秒):")
        for i, m in enumerate(monsters[:5]):  # 最多显示前5个，避免刷屏
            print(f"  {i+1}. [{m['matched_name']}] OCR文字=\"{m['name']}\" 置信度={m['confidence']} 位置=({m['center'][0]},{m['center'][1]})")

        # ---- 第3步：按置信度从高到低依次攻击 ----
        for i, monster in enumerate(monsters):
            if not state.is_running():
                break  # 用户停止了脚本，跳出遍历

            matched_name = monster["matched_name"]
            cx, cy = monster["center"]
            conf = monster["confidence"]
            print(f"[目标] 攻击第{i+1}个: \"{matched_name}\" (识别文字:\"{monster['name']}\") 置信度={conf}")

            # ---- 第4步：鼠标移动到怪物名字下方（加Y偏移）并点击攻击 ----
            y_off = CONFIG["click_y_offset"]
            print(f"[攻击] 鼠标移到 ({cx},{cy}) 并下移{y_off[0]}~{y_off[1]}px 后左键点击...")
            click_monster(cx, cy)

            # 点击后稍微等一下，让角色开始攻击动作（走到怪物面前/抬手）
            time.sleep(random.uniform(0.2, 0.4))

            # ---- 第5步：如果有配置技能，按顺序释放 ----
            if CONFIG["skill_slots"]:
                print("[技能] 释放技能...")
                use_skills()

            # ---- 第6步：等待战斗结束 ----
            timeout = CONFIG["attack_timeout"]
            print(f"[战斗] 等待战斗结束（超时 {timeout} 秒）...")
            result = wait_for_combat_end(timeout)

            if result == "dead":
                print("[战斗] 怪物已死亡 ✓")
                # 死亡后的短暂停顿，等待拾取物品或经验结算动画
                delay = random.uniform(*CONFIG["after_kill_delay"])
                time.sleep(delay)

            elif result == "timeout":
                print(f"[战斗] 超时（{timeout}秒），可能怪物未死或角色卡住，继续下一个目标")

            elif result == "stopped":
                break  # 用户停止了脚本

        # ---- 第7步：本轮怪物处理完毕，短暂等待后进入下一轮搜索 ----
        wait_time = random.uniform(*CONFIG["search_interval"])
        time.sleep(wait_time)

    print("\n[结束] 自动打怪已退出")

# ========================== 热键回调 ==========================

def on_pause_hotkey():
    """暂停/恢复 热键回调"""
    # 切换暂停状态
    state.set_paused(not state.paused)
    if state.paused:
        print("\n[暂停] 打怪已暂停，再按 F7 恢复")
    else:
        print("\n[恢复] 打怪已恢复")

def on_stop_hotkey():
    """紧急停止 热键回调"""
    print("\n[停止] 收到停止信号，正在安全退出...")
    state.set_running(False)  # 通知主循环停止
    state.set_paused(False)   # 如果正在暂停，取消暂停以便退出

def register_hotkeys():
    """注册全局热键"""
    # 注册 F7 为暂停/恢复
    keyboard.add_hotkey(CONFIG["pause_hotkey"], on_pause_hotkey)
    # 注册 F8 为紧急停止
    keyboard.add_hotkey(CONFIG["stop_hotkey"], on_stop_hotkey)
    print(f"[热键] {CONFIG['pause_hotkey'].upper()}=暂停/恢复  {CONFIG['stop_hotkey'].upper()}=紧急停止")

# ========================== 前置检查 ==========================

def pre_flight_check():
    """运行前环境检查"""
    print("=" * 50)
    print("QQ幻想 自动打怪脚本（OCR文字识别版）")
    print("=" * 50)

    # 检查是否配置了怪物名字
    if not CONFIG["monster_names"]:
        print("[错误] 未配置怪物名字！")
        print("[提示] 请在 CONFIG['monster_names'] 中填写游戏里要打的怪物名字")
        print("[示例] 'monster_names': ['小妖', '树精', '野狼']")
        return False

    # 打印已配置的怪物名字
    print(f"[配置] 目标怪物: {', '.join(CONFIG['monster_names'])}")
    return True

# ========================== 程序入口 ==========================

def main():
    """主函数：串联初始化、热键注册、主循环"""

    # ---- 运行前检查 ----
    if not pre_flight_check():
        print("[提示] 配置好怪物名字后请重新运行本脚本")
        return

    # ---- 初始化 pyautogui ----
    init_pyautogui()

    # ---- 初始化 OCR（会下载模型，第一次运行较慢） ----
    init_ocr()

    # ---- 注册热键 ----
    register_hotkeys()

    # ---- 启动主循环（在独立线程中运行，以便热键能正常响应） ----
    farm_thread = threading.Thread(target=farming_loop, daemon=True)
    farm_thread.start()

    try:
        # 主线程持续等待，直到 state.running 变为 False（用户按 F8）
        while state.is_running():
            time.sleep(0.1)
    except KeyboardInterrupt:
        # 用户按了 Ctrl+C
        print("\n[退出] 收到 Ctrl+C，正在停止...")
        state.set_running(False)

    # 等待打怪线程结束
    farm_thread.join(timeout=3)
    # 清理热键注册
    keyboard.unhook_all()
    print("[退出] 脚本已完全停止")

if __name__ == "__main__":
    main()
