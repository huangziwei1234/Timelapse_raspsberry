import os
import sys
import time
from datetime import datetime, timedelta
from suntime import Sun, SunTimeException
import subprocess
import pytz
from PIL import Image
import numpy as np
import csv
import re  # 正则表达式模块

# 设置网络路径和经纬度（北京）
network_path = "/home/raspberry_pi_timelapse" #NAS或者cloud地址
temp_dng_path = "/home/timelapse" #树莓派本地地址
csv_path = os.path.join(network_path, "exposure_log.csv")
latitude = 39.9042
longitude = 116.4074
sun = Sun(latitude, longitude)
beijing_tz = pytz.timezone('Asia/Shanghai')

#     """重启程序的函数"""
def restart_program():
    log("程序出现错误，准备重启...", level="CRITICAL")
    time.sleep(5)  # 等待 5 秒钟再重启
    python = sys.executable
    os.execv(python, ['python'] + sys.argv)  # 使用当前的命令行参数重新启动脚本

# 优化版日志输出函数
def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {msg}")


# 检查文件是否已存在
def already_taken(time_tag):
    raw_path = os.path.join(network_path, f"{time_tag}.raw")
    return os.path.exists(raw_path)


# 拍摄预览图分析亮度 20250422+
def analyze_brightness(raw_photo_path):
    img = Image.open(raw_photo_path).convert("L")  # 转换为灰度图像
    arr = np.array(img)
    avg = np.mean(arr)
    highlight_pixels = np.sum(arr >= 253)
    total_pixels = arr.size
    highlight_ratio = highlight_pixels / total_pixels
    log(f"平均亮度: {avg:.2f}, 高光比例: {highlight_ratio:.4f}")
    return avg, highlight_ratio


# 拍照函数
def capture_image(time_tag):
    jpg_photo_name = f"{time_tag}.jpg"
    jpg_temp_path = os.path.join(temp_dng_path, jpg_photo_name)
    jpg_final_path = os.path.join(network_path, jpg_photo_name)

    dng_photo_name = f"{time_tag}.dng"
    dng_temp_path = os.path.join(temp_dng_path, dng_photo_name)
    dng_final_path = os.path.join(network_path, dng_photo_name)

    # -------- 初始化必要变量，防止后面未定义 --------
    highlight_ratio = 0.0
    score = 0.0

    # 📸 初步拍一张用于亮度分析（固定 gain=1，避免自动增益干扰）
    try:
        result = subprocess.run([
            "libcamera-still",
            #"--raw", #这个在试拍时候应该没用20250426
            "--gain", "1",  # 固定 ISO=100
            "--awb", "indoor",
            "--output", jpg_temp_path,
            "--nopreview",
            "-v"  # verbose 模式，会打印实际参数
        ], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        log(f"libcamera-still 执行失败: {e}", level="ERROR")
        restart_program()  # 出现错误时重启程序
    except Exception as e:
        log(f"预览拍照过程失败: {e}", level="ERROR")
        restart_program()  # 出现错误时重启程序

    try:
        preview_avg, _ = analyze_brightness(jpg_temp_path)
    except Exception as e:
        log(f"亮度分析失败: {e}", level="ERROR")
        restart_program()  # 出现错误时重启程序

    # 从stderr中抓取曝光时间
    exposure_time = None
    for line in result.stderr.splitlines():
        # 使用正则表达式抓取曝光时间（单位微秒）
        match = re.search(r"Exposure time: (\d+)", line)
        if match:
            exposure_time = match.group(1)  # 捕获曝光时间的数字部分

    if exposure_time:
        log(f"曝光时间: {exposure_time} 微秒")
    else:
        log("未找到曝光时间。", level="WARNING")

    preview_shutter = exposure_time if exposure_time else "auto"  # 使用抓取到的曝光时间，或者使用'auto'作为默认值
    preview_gain = "1"  # 假设增益值固定为1

    log(f"[预览] 使用曝光: shutter={preview_shutter}, gain={preview_gain}")

    final_avg = preview_avg
    final_params = {
        "shutter": "0",  # 默认自动曝光
        "gain": "1",
        "awb": "indoor",
        "brightness": "0",
    }
    score = None

    if preview_avg < 90:  #cutoff avg is 90
        if preview_avg < 10:
            base = 4000000  # 4 秒
            delta = int(base * 0.25)
        elif preview_avg < 30:
            base = 1000000  # 1 秒
            delta = int(base * 0.33)
        elif preview_avg < 60:
            base = 250000  # 0.25 秒
            delta = int(base * 0.33)
        else:
            base = 30000  # 0.03 秒
            delta = int(base * 0.33)

        candidates = [base - 3 * delta, base - 2 * delta, base - delta, base, base + delta, base + 2 * delta,
                      base + 3 * delta]
        best_diff = float("inf")

        # 试拍，选取高光最小、亮度接近110 20250422+
        best_score = float("inf")
        best_candidate = None
        final_avg = preview_avg
        final_highlight = None

        for candidate in candidates:
            try:
                subprocess.run([
                    "libcamera-still",
                    #"--raw", #这个在试拍时候应该没用20250426
                    "--shutter", str(candidate),
                    "--gain", "1",
                    "--awb", "indoor",
                    "--output", jpg_temp_path,
                    "--nopreview"
                ], check=True)
                avg, highlight_ratio = analyze_brightness(jpg_temp_path)
                score = highlight_ratio * 1000 + abs(avg - 110)  # 重点考虑高光，其次考虑亮度接近程度，如果需要改写110，则在这里改
                if score < best_score:
                    best_score = score
                    best_candidate = candidate
                    final_avg = avg
                    final_highlight = highlight_ratio
                    final_params["shutter"] = str(candidate)
            except subprocess.CalledProcessError as e:
                log(f"试拍失败: {e}", level="ERROR")
                restart_program()  # 出现错误时重启程序
            except Exception as e:
                log(f"试拍分析失败: {e}", level="ERROR")
                restart_program()  # 出现错误时重启程序

    # 实际使用推荐参数再次拍照（统一固定 ISO100、4500K）
    cmd = [
        "libcamera-still",
        "--raw",
        "--shutter", final_params["shutter"],
        "--gain", final_params["gain"],
        "--awb", final_params["awb"],
        "--output", jpg_temp_path,
        "--nopreview"
    ]

    if final_params["shutter"] != "0":
        cmd.extend(["--brightness", final_params["brightness"]])

    try:
        subprocess.run(cmd, check=True)
        subprocess.run(["cp", jpg_temp_path, jpg_final_path], check=True)
        log(f"照片保存成功：{jpg_final_path}")
        subprocess.run(["cp", dng_temp_path, dng_final_path], check=True)
        log(f"DNG文件保存成功：{dng_final_path}")
    except subprocess.CalledProcessError as e:
        log(f"最终拍摄或拷贝失败: {e}", level="ERROR")
        restart_program()  # 出现错误时重启程序

    # 清理临时文件
    if os.path.exists(jpg_temp_path):
        os.remove(jpg_temp_path)
    if os.path.exists(dng_temp_path):
        os.remove(dng_temp_path)

    # ✍️ 写入日志，区分文件类型
    record_exposure_data(
        time_tag,
        preview_avg,
        final_params,
        preview_shutter=preview_shutter,
        preview_gain=preview_gain,
        final_avg=final_avg,
        highlight_ratio=highlight_ratio,
        score=score,
        file_type="jpg"  # 可以根据文件类型传递 "jpg" 或 "dng"
    )
    record_exposure_data(
        time_tag,
        preview_avg,
        final_params,
        preview_shutter=preview_shutter,
        preview_gain=preview_gain,
        final_avg=final_avg,
        highlight_ratio=highlight_ratio,
        score=score,
        file_type="dng"  # 第二次记录 DNG 类型
    )


# 记录曝光数据函数
def record_exposure_data(time_tag, preview_avg, final_params, preview_shutter="auto", preview_gain="auto",
                         final_avg=None, highlight_ratio=None, score=None, file_type="jpg"):
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, mode="a", newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "time_tag", "preview_avg", "preview_shutter", "preview_gain",
                "final_shutter", "final_gain", "brightness", "final_avg",
                "highlight_ratio", "score", "file_type"
            ])
        writer.writerow([
            time_tag,
            round(preview_avg, 2),
            preview_shutter,
            preview_gain,
            final_params["shutter"],
            final_params["gain"],
            final_params["brightness"],
            round(final_avg, 2) if final_avg is not None else "",
            round(highlight_ratio, 2) if highlight_ratio is not None else "",
            round(score, 2) if score is not None else "",
            file_type  # 记录文件类型
        ])
    log(f"曝光数据记录完成：{time_tag}, 文件类型：{file_type}")


# 主函数（仅在接近拍摄时间点时触发分析与拍摄）
def main():
    log("=== Timelapse run start ===")
    now = datetime.now(beijing_tz)
    today = now.date()

    try:
        # 计算北京今日 7:00 -> UTC 对应时间
        beijing_midnight_naive = datetime(today.year, today.month, today.day, 7, 0)
        beijing_midnight = beijing_tz.localize(beijing_midnight_naive)
        utc_midnight = beijing_midnight.astimezone(pytz.utc).replace(tzinfo=None)

        # 获取日出日落时间
        sunrise_utc = sun.get_sunrise_time(utc_midnight)
        sunset_utc = sun.get_sunset_time(utc_midnight) + timedelta(hours=48) # 由于日落时间有bug，所以+48小时能够换算为当日时间

        sunrise_beijing = sunrise_utc.astimezone(beijing_tz)
        sunset_beijing = sunset_utc.astimezone(beijing_tz)

        # 中午两个时间点
        midday_early = beijing_tz.localize(datetime(today.year, today.month, today.day, 12, 59))
        midday_late = beijing_tz.localize(datetime(today.year, today.month, today.day, 13, 1))

        # 生成今日目标拍摄时间点（共 44 张）
        targets = []
        for i in range(21):
            shot_sunrise = sunrise_beijing - timedelta(minutes=40) + timedelta(minutes=4 * i)
            shot_sunset = sunset_beijing - timedelta(minutes=40) + timedelta(minutes=4 * i)
            if shot_sunrise.date() == today:
                targets.append(shot_sunrise)
            if shot_sunset.date() == today:
                targets.append(shot_sunset)
        targets.append(midday_early)
        targets.append(midday_late)

        # 用于检测
        # print("今日拍摄计划：")

        # for shot_time in targets:
        #    time_tag = shot_time.strftime("%Y%m%d_%H%M")
        #    raw_path = os.path.join(network_path, f"{time_tag}.raw")
        #    if os.path.exists(raw_path):
        #        print(f"{shot_time.strftime('%Y-%m-%d %H:%M')} - 已拍摄")
        #    else:
        #        print(f"{shot_time.strftime('%Y-%m-%d %H:%M')} - 未拍摄")

        # 检查是否接近某个拍摄点
        for target_time in targets:
            if abs((now - target_time).total_seconds()) <= 120:
                time_tag = target_time.strftime("%Y%m%d_%H%M")
                if not already_taken(time_tag):
                    log(f"当前时间接近拍摄时间点：{time_tag}")
                    capture_image(time_tag)
                else:
                    log(f"{time_tag} 已拍摄，跳过。")
                break

    except SunTimeException as e:
        log(f"获取日出日落失败: {e}", level="ERROR")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"程序出现严重错误，准备重启: {e}", level="CRITICAL")
        restart_program()  # 出现错误时重启程序

