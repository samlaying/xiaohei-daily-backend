"""截图质量自检 — 检测 macOS 屏幕录制权限是否生效。

原理：未授权时 screencapture 不报错，而是偷偷返回「只剩壁纸、抹掉所有窗口」的图。

三路信号综合判断（任一显示有内容即判正常，大幅降低误报）：
  1. 锐利边缘比例（主信号）：文字/UI边框产生极锐利边缘，自然壁纸没有。
     实测：纯壁纸 0.02%，飞书窗口 0.51%，区分度 25 倍。
  2. 多帧窗口区变化：正常工作时屏幕总在变(光标/时钟/滚动)。
     实测：纯壁纸 0.000%，真实内容位移 15.5%。
  3. Laplacian 方差（辅助）：有窗口时高频细节更多。

这样即使用户在自检期间静止不动（多帧信号失效），
单帧的锐利边缘信号仍能正确判定「有窗口内容」。
"""

import time
import numpy as np
from PIL import Image

# 阈值（基于真实数据校准，飞书窗口 vs 湖景壁纸）
SHARP_EDGE_THRESHOLD = 0.10   # 锐利边缘占比 %：壁纸0.02 / 飞书0.51
LAPLACIAN_THRESHOLD = 600     # Laplacian方差：壁纸~400 / 飞书~940
WINDOW_CHANGE_THRESHOLD = 0.20  # 窗口区变化 %：壁纸0.000 / 真实>0.5
MENU_BAR_HEIGHT = 32
PIXEL_DIFF_THRESHOLD = 8
SHARP_EDGE_ABS = 200          # Laplacian 绝对值超过此值算"锐利边缘"


def _window_region(arr: np.ndarray) -> np.ndarray:
    """取窗口区域（排除顶部菜单栏和底部 dock）。"""
    h = arr.shape[0]
    return arr[MENU_BAR_HEIGHT:int(h * 0.96), :]


def _laplacian(win: np.ndarray) -> np.ndarray:
    return (win[:-2, 1:-1] + win[2:, 1:-1]
            + win[1:-1, :-2] + win[1:-1, 2:]
            - 4 * win[1:-1, 1:-1])


def analyze_single_frame(path: str) -> dict:
    """单帧分析：锐利边缘比例 + Laplacian方差。"""
    arr = np.array(Image.open(path).convert("L"), dtype=np.float64)
    win = _window_region(arr)
    lap = _laplacian(win)
    al = np.abs(lap)
    return {
        "sharp_ratio": round(float((al > SHARP_EDGE_ABS).mean()) * 100, 3),
        "laplacian_var": round(float(lap.var()), 1),
    }


def compare_two_frames(path_a: str, path_b: str) -> dict:
    """多帧对比：窗口区变化率 + 菜单栏变化率。"""
    a = _window_region(np.array(Image.open(path_a).convert("L"), dtype=np.float64))
    b = _window_region(np.array(Image.open(path_b).convert("L"), dtype=np.float64))
    full_a = np.array(Image.open(path_a).convert("L"), dtype=np.float64)
    full_b = np.array(Image.open(path_b).convert("L"), dtype=np.float64)
    menu_a, menu_b = full_a[:MENU_BAR_HEIGHT], full_b[:MENU_BAR_HEIGHT]

    window_change = float((np.abs(a - b) > PIXEL_DIFF_THRESHOLD).mean()) * 100
    menu_change = float((np.abs(menu_a - menu_b) > PIXEL_DIFF_THRESHOLD).mean()) * 100
    return {
        "window_change": round(window_change, 3),
        "menu_change": round(menu_change, 3),
    }


def diagnose(path_a: str, path_b: str = None) -> dict:
    """
    综合诊断。返回:
        status: 'ok' | 'wallpaper'
        signals: dict 各信号值
        verdict: str 结论
    """
    single = analyze_single_frame(path_a)
    signals = {"sharp_edge%": single["sharp_ratio"],
               "laplacian_var": single["laplacian_var"]}

    # 信号1：单帧锐利边缘（主信号，不依赖屏幕是否在动）
    if single["sharp_ratio"] > SHARP_EDGE_THRESHOLD:
        verdict = (f"✅ 权限正常：检测到 UI 文字/边缘 "
                   f"(锐利边缘 {single['sharp_ratio']}%, Laplacian {single['laplacian_var']:.0f})。"
                   f"能抓到真实工作内容。")
        return {"status": "ok", "signals": signals, "verdict": verdict}

    # 信号2/3：多帧对比（屏幕静止时单帧已失效，看动态）
    if path_b:
        frame = compare_two_frames(path_a, path_b)
        signals.update(frame)
        if frame["window_change"] > WINDOW_CHANGE_THRESHOLD:
            verdict = (f"✅ 权限正常：窗口区在变化 ({frame['window_change']}%)。"
                       f"能抓到真实工作内容。")
            return {"status": "ok", "signals": signals, "verdict": verdict}

        # 单帧无内容 + 多帧静止 → 壁纸模式
        if frame["menu_change"] > 0.1:
            reason = ("菜单栏在变化 (%.2f%%) 但窗口区完全静止 (%.3f%%)，"
                      "应用窗口被 macOS 抹掉了。" % (frame["menu_change"], frame["window_change"]))
        else:
            reason = ("窗口区无 UI 内容 (锐利边缘 %.2f%%) 且屏幕静止 "
                      "(窗口区变化 %.3f%%)。" % (single["sharp_ratio"], frame["window_change"]))
        verdict = f"⚠️ 权限未生效：{reason}"
        return {"status": "wallpaper", "signals": signals, "verdict": verdict}

    # 仅单帧，无内容信号
    verdict = (f"❓ 单帧无 UI 内容信号 (锐利边缘 {single['sharp_ratio']}%, "
               f"Laplacian {single['laplacian_var']:.0f})。可能是纯桌面。")
    return {"status": "wallpaper", "signals": signals, "verdict": verdict}


def run_startup_check(capture_fn, wait_seconds: int = 3) -> dict:
    """启动自检：截两张图，间隔几秒。capture_fn 返回截图路径。"""
    path_a = capture_fn()
    time.sleep(wait_seconds)
    path_b = capture_fn()
    return diagnose(path_a, path_b)


def print_permission_guide():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  ⚠️  屏幕录制权限未生效 — 截图抓不到应用窗口内容                    ║
╠══════════════════════════════════════════════════════════════════╣
║  macOS 未授权时，screencapture 会偷偷返回「只剩壁纸」的图。         ║
║                                                                  ║
║  解决步骤：                                                       ║
║  1. 系统设置 → 隐私与安全性 → 屏幕录制                            ║
║  2. 找到运行本服务的终端 (Terminal / iTerm / Warp / VSCode)        ║
║  3. 打开开关 ✅                                                   ║
║  4. 完全退出终端 (⌘+Q) 再重新打开 — 权限需进程重启才生效           ║
║  5. 重新运行: python3 main.py                                    ║
║                                                                  ║
║  已确认是纯桌面/想跳过检查:                                       ║
║     SKIP_PERMISSION_CHECK=1 python3 main.py                      ║
╚══════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        result = diagnose(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 2:
        result = diagnose(sys.argv[1])
    else:
        print("用法: python permission_check.py <a.png> [b.png]")
        sys.exit(1)
    print(result["verdict"])
    for k, v in result["signals"].items():
        print(f"  {k}: {v}")
    if result["status"] == "wallpaper":
        print_permission_guide()
