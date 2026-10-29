#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置模板 —— 复制成 config.py 再填自己的值。

  copy config.example.py config.py

config.py 已经在 .gitignore 里，不会被提交。
"""

# ==================== 必填 ====================

# 机器人的 QQ 号（NapCat 登录的那个号）
SELF_ID = 0

# 你自己的 QQ 号（"主人"）
OWNER_ID = 0

# NapCat 的 OneBot 令牌（在 NapCat 的配置里设置）
ONEBOT_TOKEN = ""

# DeepSeek API Key（https://platform.deepseek.com/）
API_KEY = ""

# ==================== 可选 ====================

# NapCat 的 OneBot 端口
ONEBOT_PORT = 3399

# 模型选择
MODEL = "deepseek-v4-pro"        # 私聊（强）
MODEL_GROUP = "deepseek-flash"   # 群聊（便宜）
MODEL_MEM = "deepseek-flash"     # 记忆提取（便宜）
MODEL_VISION = "deepseek-flash"  # 看图（pro 不支持图像）

# 主动聊天（空着就用默认值）
PROACTIVE_WINDOW = (9, 23)       # 只在几点到几点主动
PROACTIVE_IDLE_H = 3             # 你多久没说话她才惦记
PROACTIVE_MIN_GAP_H = 4          # 距上次主动至少多久
PROACTIVE_MAX_PER_DAY = 3        # 每天最多几次

# 语音（可选，不配就用 edge-tts）
GSV_URL = ""                     # GPT-SoVITS 服务地址，如 http://127.0.0.1:9880/tts
GSV_REF_AUDIO = ""               # 参考音频（自己录 6-10 秒）
GSV_REF_TEXT = ""                # 参考音频对应的文字

# 表情包（可选）
STICKER_JSON = "stickers-screened.json"

# ==================== 外部服务路径（按自己的安装位置改）====================
GSV_ROOT = r"D:\gptsovits\src\GPT-SoVITS-main"
GSV_PY = r"D:\gptsovits\venv\Scripts\python.exe"
WHISPER_EXE = r"D:\whisper\bin\Release\whisper-cli.exe"
WHISPER_MODEL = r"D:\whisper\ggml-small.bin"
SENSEVOICE_LIB = r"D:\sensevoice\lib"
SENSEVOICE_DIR = r"D:\sensevoice\model"
LAUNCH_BAT = r"D:\dsh-downloads\napcat\Shell\napcat\start-napcat-user.bat"
NAPCAT_QR = r"D:\dsh-downloads\napcat\Shell\napcat\cache\qrcode.png"
EDGE_TTS_LIB = r"D:\edge-tts\lib"
EDGE_OUT = r"D:\edge-tts\out"
GSV_REF_AUDIO = r"D:\gptsovits\ref\new_ref.wav"
GSV_OUT = r"D:\gptsovits\ref\reply"
