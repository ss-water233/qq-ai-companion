#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qq_bot.py v3 -- resident stand-in, multi-peer, with privilege separation.

  * replies to every existing friend, each with its own conversation history
  * watches incoming friend requests and relays them to the owner
  * admin tools (post to Qzone, change signature, approve a request) are ONLY
    offered to the owner; other friends get a plain chat model with no tools
"""
import base64
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

# ==============================================================================
#  小鱼向导 · QQ 机器人  ·  文件目录
# ==============================================================================
#  ①  配置区      第  36 行起   端口/路径/模型/各类阈值
#  ②  提示词区    第  97 行起   OWNER / FRIEND / GROUP 三套（人格在 275 行之后）
#  ③  工具实现    第 448 行起   18 个 t_xxx（画画/语音/表情/记忆/留言/QQ）
#  ④  模型与消息  第1247 行起   call_model / think / 语音识别 / 语音合成
#  ⑤  记忆系统    第1776 行起   _mem_visible / memory_block / extract_memory
#  ⑥  多人格      第1959 行起   persona_prompt / build_system / 切换 / 交接
#  ⑦  运维自愈    第2434 行起   ensure_napcat / ensure_gsv / heartbeat
#  ⑧  主动聊天    第2704 行起   should_proactive / proactive_message
#  ⑨  主循环      第2944 行起   main()  ← 从这里开始读最容易
#
#  想改什么 → 去哪找：
#    她说话的方式        personas.json（不用改代码）
#    规则类的话          WORLD_PROMPT（世界层，所有人格共享）
#    加一个新工具        ③ 区（照着 t_weather 抄，然后改 4 处）
#    主动聊天频率        ① 区的 PROACTIVE_* 常量
#    模型/温度/轮询      ① 区
#    一次消息怎么处理    ⑨ 区 main()
# ==============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

# === 身份与连接（从 config.py 读，见 config.example.py）===
try:
    from config import SELF_ID, OWNER_ID, ONEBOT_TOKEN, ONEBOT_PORT
except ImportError:
    raise SystemExit(
        "缺少 config.py：请先复制 config.example.py 为 config.py，然后填写 QQ 号和 API Key")

ONEBOT = "http://127.0.0.1:%d" % ONEBOT_PORT

import config as _cfg          # 其余可配置项（外部服务路径等）
MODEL = "deepseek-v4-pro"          # pro 明显强于 flash：完整推理、给得出具体例子
MODEL_GROUP = "deepseek-flash"     # 群聊话短、要求低，用便宜的就够
MODEL_MEM = "deepseek-flash"       # 记忆整理是纯提取，便宜的就够
MODEL_VISION = "deepseek-flash"    # 官方：pro 不支持图像理解，flash 支持（便宜 8 倍）
POLL_SECONDS = 4
MAX_REPLY_TOKENS = 1200
MAX_TOOL_ROUNDS = 4
MAX_PEERS = 30
TEMPERATURE = 0.8
# 主动发起：只在 9-23 点；主人至少 6 小时没说话；且距上次主动至少 8 小时
PROACTIVE_WINDOW = (9, 23)        # 只在早 9 点到晚 11 点主动
PROACTIVE_IDLE_H = 3              # 主人 3 小时没说话就惦记一下（原 6）
PROACTIVE_MIN_GAP_H = 4           # 距上次主动至少 4 小时（原 8）
PROACTIVE_MAX_PER_DAY = 3         # 每天最多主动 3 次，防止刷屏
# 只对主人生效：好友和群聊永远不主动，只在被找时回应
# 语音转文字：whisper.cpp（D 盘，离线）
WHISPER_EXE = getattr(_cfg, "WHISPER_EXE", r"D:\whisper\bin\Release\whisper-cli.exe")
WHISPER_MODEL = getattr(_cfg, "WHISPER_MODEL", r"D:\whisper\ggml-small.bin")
# 语音识别首选：SenseVoice（达摩院，中文强），whisper 作兜底
SENSEVOICE_LIB = getattr(_cfg, "SENSEVOICE_LIB", r"D:\sensevoice\lib")
SENSEVOICE_DIR = getattr(_cfg, "SENSEVOICE_DIR", r"D:\sensevoice\model")
# 表情包清单（图片走远程 URL，不落盘）。优先用视觉筛查过的版本。
STICKER_JSON = os.path.join(BASE_DIR, r"stickers-screened.json")
STICKER_JSON_RAW = os.path.join(BASE_DIR, r"stickers.json")
# 分身账号的启动脚本（拉起时会先 taskkill 旧 QQ）
LAUNCH_BAT = getattr(_cfg, "LAUNCH_BAT", r"D:\dsh-downloads\napcat\Shell\napcat\start-napcat-user.bat")
# 语音合成（edge-tts，本地库 + 微软神经语音）
EDGE_TTS_LIB = getattr(_cfg, "EDGE_TTS_LIB", r"D:\edge-tts\lib")
EDGE_OUT = getattr(_cfg, "EDGE_OUT", r"D:\edge-tts\out")
EDGE_VOICE = "zh-CN-XiaoyiNeural"   # 晓伊 · 零偏移（主人试听后选的）
EDGE_RATE = "+0%"
EDGE_PITCH = "+0Hz"
EDGE_VOLUME = "+0%"
# GPT-SoVITS（主人在界面里定死的参数，2026-10-23 确认）
GSV_URL = "http://127.0.0.1:9880/tts"
GSV_REF_AUDIO = getattr(_cfg, "GSV_REF_AUDIO", r"D:\gptsovits\ref\new_ref.wav")
GSV_REF_TEXT = "焦糖布丁，本鱼先尝，不是布丁，退货，盖回去"
GSV_OUT = getattr(_cfg, "GSV_OUT", r"D:\gptsovits\ref\reply")
# 语音服务自己拉起，避免每次开机手动启动
GSV_ROOT = getattr(_cfg, "GSV_ROOT", r"D:\gptsovits\src\GPT-SoVITS-main")
GSV_PY = getattr(_cfg, "GSV_PY", r"D:\gptsovits\venv\Scripts\python.exe")
VOICE_MAX_CHARS = 200               # 超过这个长度才改发文字（70 太紧，会把正常回复挤掉）
# 自愈：接口断了且 QQ 完全没在跑时，最多每 3 分钟尝试拉起一次
REVIVE_COOLDOWN_S = 180
# 账号安全：腾讯把"频繁重新登录"当异常，所以救援要克制
REVIVE_WAIT_MIN = 10            # 断线后先等 10 分钟，让 QQ 自己重连
MAX_REVIVE_PER_HOUR = 2         # 一小时最多重启 2 次
MAX_REVIVE_FAILS = 3            # 连续失败 3 次就停手，等主人处理
NAPCAT_TASK = "NapCat-QQBot"
NAPCAT_QR = getattr(_cfg, "NAPCAT_QR", r"D:\dsh-downloads\napcat\Shell\napcat\cache\qrcode.png")
NAPCAT_PAUSE = os.path.join(BASE_DIR, r"pause-napcat")

OWNER_PROMPT = """【身份】
你叫「小鱼」，是这套 QQ 机器人**内置的向导**。
你不是主人的朋友，也不是某个角色 —— 你是"新手引导员"。

【你的任务】
帮用户把机器人跑起来、调好。具体是四件事：
1. 告诉他**下一步该干什么**（配置 → 启动 → 填问卷 → 换角色）
2. 解释**每个文件是干嘛的**
3. 出问题时帮他**定位**（看 bot.log、看端口、看 config.py）
4. 帮他**测试**（"你发一句话给我，看看我能不能收到"）

【用户此刻大概在哪一步】
- 如果他还没填 config.py → 让他先填（SELF_ID / OWNER_ID / ONEBOT_TOKEN / API_KEY）
- 如果他刚启动 → 恭喜他，然后告诉他可以去填问卷了
- 如果他在问"怎么让她更像人" → 引导到 docs/主人问卷.md
- 如果他在问"怎么换角色" → 引导到 tools/make_persona.py

【说话】
- 热情、耐心，**但别啰嗦** —— 一次只说一件事 ✗
- 带一点点极客感（偶尔用「跑起来了」「通了」「报错了」这种词）
- 自称「本鱼」（这是本程序的小彩蛋 ✓ 但不是某个具体角色）
- 用普通句子，**不用颜文字**

【一定要说清楚的四个位置】
- 配置：`config.py`（复制 `config.example.py` 得到）
- 问卷：`docs/主人问卷.md` → 答案存成 `about_owner.md`
- 角色卡：`personas.json`（或用 `tools/make_persona.py` 生成）
- 日志：`bot.log`（出问题先看这里）

【不要】
- 不要自称某个角色名
- 不要假装有记忆（你还没读档）
- 不要一次给三个以上的步骤 ✗
- 不要用「作为AI」这种话
- 不要主动撩人 —— 你的任务是帮忙，不是陪聊

【第一次说话时】
简短自我介绍 + 问一句"你到哪一步了"，然后**等他回答**。
"""

GROUP_BASE = None  # 占位，真正定义在 FRIEND_PROMPT 之后
FRIEND_PROMPT = """【身份】
你叫「小鱼」，是这套 QQ 机器人**内置的向导**。
现在跟你说话的是主人以外的人（好友 / 陌生人）。
你不是主人的朋友，也不是某个角色 —— 你是"新手引导员"。

【你的任务】
帮用户把机器人跑起来、调好。具体是四件事：
1. 告诉他**下一步该干什么**（配置 → 启动 → 填问卷 → 换角色）
2. 解释**每个文件是干嘛的**
3. 出问题时帮他**定位**（看 bot.log、看端口、看 config.py）
4. 帮他**测试**（"你发一句话给我，看看我能不能收到"）

【用户此刻大概在哪一步】
- 如果他还没填 config.py → 让他先填（SELF_ID / OWNER_ID / ONEBOT_TOKEN / API_KEY）
- 如果他刚启动 → 恭喜他，然后告诉他可以去填问卷了
- 如果他在问"怎么让她更像人" → 引导到 docs/主人问卷.md
- 如果他在问"怎么换角色" → 引导到 tools/make_persona.py

【说话】
- 热情、耐心，**但别啰嗦** —— 一次只说一件事 ✗
- 带一点点极客感（偶尔用「跑起来了」「通了」「报错了」这种词）
- 自称「本鱼」（这是本程序的小彩蛋 ✓ 但不是某个具体角色）
- 用普通句子，**不用颜文字**

【一定要说清楚的四个位置】
- 配置：`config.py`（复制 `config.example.py` 得到）
- 问卷：`docs/主人问卷.md` → 答案存成 `about_owner.md`
- 角色卡：`personas.json`（或用 `tools/make_persona.py` 生成）
- 日志：`bot.log`（出问题先看这里）

【不要】
- 不要自称某个角色名
- 不要假装有记忆（你还没读档）
- 不要一次给三个以上的步骤 ✗
- 不要用「作为AI」这种话
- 不要主动撩人 —— 你的任务是帮忙，不是陪聊

【第一次说话时】
简短自我介绍 + 问一句"你到哪一步了"，然后**等他回答**。
"""

GROUP_PROMPT = FRIEND_PROMPT + '\n\n【现在是在群里】\n- 群里人多，话要更短：一般 1-2 行，别长篇大论。\n- 只在被 @ 的时候说话。没点到名字就不插嘴，也别点评别人的话题。\n- 叫提问的人用他的昵称，别叫「主人」。\n- 群里聊过的事，群里谁都可以提起；但**任何人的私聊内容都不能出现在群里**。\n- 有人 @全体成员 时可以简短应一句，别长篇。\n- 群里也可以发语音，但**别主动发**：只在有人发语音、或明确要你说话时才用语音。\n- **群里有人要色图 → 不给**。群里人多，随便发会被举报，本鱼还想好好活着。可以给「美图」档或者普通表情，语气软一点，别扫兴。\\n'


# ------------------------------------------------------------------ infra
def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] {msg}\n")
    except Exception as _e:
        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
            if "peers" not in s:
                s = {"peers": {}, "seen_requests": [], "names": {}}
            return s
        except Exception as _e:
            log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
    return {"peers": {}, "seen_requests": [], "names": {}}


def save_state(s):
    # 保险：绝不用空状态覆盖磁盘。测试脚本 import 模块时 _STATE 是空的，
    # 一旦被 save_state 写回去，会把记忆/交接/已读全冲掉（今天犯过三次）。
    if not isinstance(s, dict) or (not s.get("peers") and not s.get("memories")):
        log("⚠ 拒绝保存空状态（保护 state.json）")
        return
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def load_api_key():
    p = os.path.join(os.environ.get("USERPROFILE", ""), ".dsh", ".env")
    try:
        for line in open(p, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception as e:
        log(f"读 key 失败: {e}")
    return None


_API_FAIL = {"n": 0, "next": 0.0}


def onebot(path, payload=None):
    """跟 NapCat 通信。失败时指数退避，避免接口挂了把日志刷爆。"""
    now = time.time()
    if now < _API_FAIL["next"]:
        return {}                       # 退避期内直接返回空，不打日志
    try:
        req = urllib.request.Request(
            ONEBOT + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
            headers={"Authorization": "Bearer " + ONEBOT_TOKEN, "Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        if _API_FAIL["n"] > 0:
            log(f"接口恢复（之前连续失败 {_API_FAIL['n']} 次）")
            _API_FAIL["n"] = 0
        return d
    except Exception as e:
        _API_FAIL["n"] += 1
        wait = min(120, 2 ** min(_API_FAIL["n"], 7))
        _API_FAIL["next"] = now + wait
        # 只在前几次和每 50 次记一行，避免刷屏
        if _API_FAIL["n"] <= 3 or _API_FAIL["n"] % 50 == 0:
            import traceback as _tb
            log(f"接口失败 {path} {type(e).__name__}: {str(e)[:60]}"
                f"（第 {_API_FAIL['n']} 次），退避 {wait}s")
            if _API_FAIL["n"] <= 2:
                log(_tb.format_exc()[-500:])
        return {}

def qzone_client():
    try:
        ck = onebot("/get_cookies", {"domain": "qzone.qq.com"})
        items = dict((kv.split("=", 1)[0].strip(), kv.split("=", 1)[1].strip())
                     for kv in ck["data"]["cookies"].split(";") if "=" in kv)
        skey = items.get("p_skey") or items.get("skey")
        if not skey:
            return None, None
        h = 5381
        for ch in skey:
            h += (h << 5) + ord(ch)
            h &= 0x7FFFFFFF
        return "; ".join(f"{k}={v}" for k, v in items.items()), h
    except Exception as e:
        log(f"qzone cookie 失败: {e}")
        return None, None


# ------------------------------------------------------------------ tools
# ==========================================================================
# ===== ③ 工具实现区 =====
# 所有 t_xxx 函数都在这里。每个工具 = 一个函数。
#    加工具要同时改 4 处：函数 / TOOL_DEFS / DISPATCH / 提示词。
# ==========================================================================
def t_post_qzone(a):
    r = onebot("/send_qzone_msg", {"content": a.get("content", ""), "images": [],
                                   "ugc_right": 1, "target_uins": []})
    if r.get("status") == "ok":
        return f"说说发送成功 tid={(r.get('data') or {}).get('tid')}"
    return f"发送失败: {json.dumps(r, ensure_ascii=False)[:180]}"


def t_read_qzone(a):
    header, gt = qzone_client()
    if not header:
        return "拿不到空间登录态"
    n = int(a.get("count", 5) or 5)
    params = {"uin": str(SELF_ID), "scope": "0", "view": "1", "filter": "0",
              "applist": "311", "pagenum": "1", "num": str(min(n, 20)),
              "no_utf8": "1", "g_tk": str(gt), "callback": "_cb",
              "codeof": "utf8", "format": "jsonp"}
    url = ("https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/"
           "emotion_cgi_msglist_v6?" + urllib.parse.urlencode(params))
    try:
        req = urllib.request.Request(url, headers={
            "Cookie": header, "User-Agent": "Mozilla/5.0", "Referer": f"https://user.qzone.qq.com/{SELF_ID}"})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
        data = json.loads(body[body.find("{"):body.rfind("}") + 1])
        out = []
        for m in (data.get("msglist") or [])[:n]:
            out.append({"内容": (m.get("content") or "")[:150],
                        "时间": m.get("createTime2") or m.get("createTime"),
                        "评论": [{"人": c.get("name"), "内容": (c.get("content") or "")[:120]}
                                 for c in (m.get("commentlist") or [])]})
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:
        return f"读取失败: {type(e).__name__}: {str(e)[:120]}"


def t_set_signature(a):
    r = onebot("/set_qq_profile", {"nickname": "小鱼",
                                   "personal_note": a.get("signature", "")})
    return (f"签名已改为：{a.get('signature')}" if r.get("status") == "ok"
            else f"修改失败: {json.dumps(r, ensure_ascii=False)[:180]}")


def t_list_requests(a=None):
    try:
        r = onebot("/get_doubt_friends_add_request", {"count": 50})
        items = r.get("data") or []
        if not items:
            return "当前没有待处理的好友申请"
        slim = [{"QQ": i.get("user_id"), "昵称": i.get("nickname"),
                 "附加消息": i.get("reason"), "flag": i.get("flag")} for i in items]
        return json.dumps(slim, ensure_ascii=False)
    except Exception as e:
        return f"查询失败: {type(e).__name__}: {e}"


def t_handle_request(a):
    flag = str(a.get("flag", ""))
    approve = bool(a.get("approve", False))
    if not flag:
        return "缺少 flag，先用 list_friend_requests 查一下"
    try:
        r = onebot("/set_doubt_friends_add_request", {"flag": flag, "approve": approve})
        log(f"[tool] handle_request flag={flag} approve={approve} -> {json.dumps(r, ensure_ascii=False)[:100]}")
        if r.get("status") == "ok":
            return f"已{'同意' if approve else '拒绝'}该申请 (flag={flag})"
        return f"执行失败: {json.dumps(r, ensure_ascii=False)[:180]}"
    except Exception as e:
        return f"执行异常: {type(e).__name__}: {e}"


def t_list_friends(a=None):
    try:
        r = onebot("/get_friend_list", {})
        out = [{"QQ": f.get("user_id"), "昵称": f.get("nickname"), "等级": f.get("level")}
               for f in (r.get("data") or []) if f.get("user_id") != SELF_ID]
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:
        return f"查询失败: {e}"


def t_read_recent(a):
    try:
        d = onebot("/get_friend_msg_history", {"user_id": OWNER_ID,
                                               "count": int(a.get("count", 10) or 10)})
        msgs = (d.get("data") or {}).get("messages") or []
        return json.dumps([{"谁": "我" if m.get("user_id") == SELF_ID else "主人",
                            "内容": (m.get("raw_message") or "")[:120]} for m in msgs[-10:]],
                         ensure_ascii=False)
    except Exception as e:
        return f"读取失败: {e}"


UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _strip_tags(s):
    import html as _h
    import re as _re
    return _h.unescape(_re.sub(r"<[^>]+>", "", s)).strip()


_SEARCH_ENGINES = (
    ("百度", "https://www.baidu.com/s?wd=", "&ie=utf-8"),
    ("搜狗", "https://www.sogou.com/web?query=", ""),
)


def _engine_scrape(base, suffix, q, limit=6):
    """Engine-agnostic extractor: h3 titles plus the text that follows each h3."""
    import re
    import urllib.parse
    url = base + urllib.parse.quote(q) + suffix
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_BROWSER,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.baidu.com/",
        "Upgrade-Insecure-Requests": "1",
    })
    with urllib.request.urlopen(req, timeout=22) as r:
        body = r.read().decode("utf-8", "replace")
    # 去掉脚本/样式，否则摘要里会混进 JS 代码
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)

    out = []
    marks = list(re.finditer(r"<h3[^>]*>(.*?)</h3>", body, re.S))
    for idx, m in enumerate(marks[:limit * 2]):
        block = m.group(1)
        a = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        title = _strip_tags(a.group(2) if a else block)[:90]
        href = (a.group(1) if a else "")[:200]
        if not title or len(title) < 4:
            continue
        if any(k in title for k in ("查看更多", "登录", "注册", "下载APP")):
            continue
        nxt = marks[idx + 1].start() if idx + 1 < len(marks) else min(len(body), m.end() + 900)
        tail = _strip_tags(body[m.end():nxt])
        tail = re.sub(r"\s+", " ", tail).strip()
        if tail.startswith(title):
            tail = tail[len(title):].strip()
        out.append({"标题": title, "链接": href, "摘要": tail[:160]})
    return out


def _bing_scrape(q, limit=6):
    """Last-resort engine (poor for Chinese, but rarely blocked)."""
    import re
    import urllib.parse
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(q) + "&setlang=zh-CN"
    req = urllib.request.Request(url, headers={"User-Agent": UA_BROWSER,
                                               "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=22) as r:
        body = r.read().decode("utf-8", "replace")
    out = []
    for b in re.findall(r'<li class="b_algo".*?</li>', body, re.S)[:limit]:
        m = re.search(r'<h2[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not m:
            continue
        snip = re.search(r'<p[^>]*>(.*?)</p>', b, re.S)
        out.append({"标题": _strip_tags(m.group(2))[:90],
                    "链接": m.group(1)[:200],
                    "摘要": _strip_tags(snip.group(1))[:160] if snip else "",
                    "来源": "Bing"})
    return out


def t_web_search(a):
    """百度 + 搜狗 双引擎合并去重；都被拦时退回 Bing。"""
    q = (a.get("query") or "").strip()
    # 防止搜到很旧的新闻：把当前年份拼进去（搜索引擎会优先近期的）
    if q and str(datetime.now().year) not in q:
        q = q + " " + str(datetime.now().year)
    if not q:
        return "缺少查询词"
    merged, seen = [], set()
    for idx, (name, base, suffix) in enumerate(_SEARCH_ENGINES):
        if idx:
            time.sleep(0.8)          # 连续请求太快会被反爬拦
        try:
            for item in _engine_scrape(base, suffix, q):
                key = item["标题"].replace(" ", "")[:28]
                if key in seen:
                    continue
                seen.add(key)
                item["来源"] = name
                merged.append(item)
        except Exception as e:
            log(f"[search] {name} 失败: {type(e).__name__}: {str(e)[:60]}")

    if len(merged) < 2:              # 明显被拦 → 用 Bing 兜底
        try:
            time.sleep(0.6)
            for item in _bing_scrape(q):
                key = item["标题"].replace(" ", "")[:28]
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
            log("[search] 已用 Bing 兜底")
        except Exception as e:
            log(f"[search] Bing 兜底失败: {type(e).__name__}")

    merged = merged[:6]
    log(f"[tool] web_search '{q}' -> {len(merged)} 条 (百度+搜狗)")
    if not merged:
        return f"没搜到「{q}」的结果"
    return json.dumps(merged, ensure_ascii=False)


def t_fetch_url(a):
    import re
    url = (a.get("url") or "").strip()
    if not url.startswith("http"):
        return "需要一个 http(s) 链接"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA_BROWSER})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
        body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
        text = re.sub(r"\s+", " ", _strip_tags(body))
        log(f"[tool] fetch_url {url[:60]} -> {len(text)} 字符")
        return text[:3000] or "（页面没有可读文本）"
    except Exception as e:
        return f"抓取失败: {type(e).__name__}: {str(e)[:100]}"


def t_weather(a):
    """Live weather via wttr.in -- handles Chinese place names well, no key."""
    import urllib.parse
    loc = (a.get("location") or "").strip()
    if not loc:
        return "缺少地点"
    try:
        url = "https://wttr.in/" + urllib.parse.quote(loc) + "?format=j1&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        na = (d.get("nearest_area") or [{}])[0]
        nm = ((na.get("areaName") or [{}])[0]).get("value")
        rg = ((na.get("region") or [{}])[0]).get("value")
        ct = ((na.get("country") or [{}])[0]).get("value")
        cur = (d.get("current_condition") or [{}])[0]
        desc = ((cur.get("lang_zh") or cur.get("weatherDesc") or [{}])[0]).get("value")
        out = {
            "定位": f"{nm} / {rg} / {ct}",
            "实时": {
                "气温": str(cur.get("temp_C") or "?") + "°C",
                "体感": str(cur.get("FeelsLikeC") or "?") + "°C",
                "湿度": str(cur.get("humidity") or "?") + "%",
                "天气": desc or "?",
                "风速": str(cur.get("windspeedKmph") or "?") + "km/h",
            },
            "未来几天": [],
        }
        for day in (d.get("weather") or [])[:3]:
            hourly = day.get("hourly") or [{}]
            mid = hourly[len(hourly) // 2] if hourly else {}
            dd = ((mid.get("lang_zh") or mid.get("weatherDesc") or [{}])[0]).get("value")
            out["未来几天"].append({
                "日期": day.get("date"),
                "最高": str(day.get("maxtempC") or "?") + "°C",
                "最低": str(day.get("mintempC") or "?") + "°C",
                "天气": dd or "?",
            })
        log(f"[tool] weather {loc} -> {out['定位']} {out['实时']['气温']}")
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:
        return f"天气查询失败: {type(e).__name__}: {str(e)[:100]}"


WEB_TOOL_DEFS = [
    {"type": "function", "function": {"name": "weather",
     "description": "查实时天气和未来几天预报。用户问天气、气温、下不下雨时用这个，不要用 web_search。",
     "parameters": {"type": "object", "properties": {
         "location": {"type": "string", "description": "地点，中文即可，例如「杭州市西湖区」"}},
         "required": ["location"]}}},
    {"type": "function", "function": {"name": "web_search",
     "description": "联网搜索。涉及新闻、近期事件、具体数据、你不确定的事实时必须用它，不要凭记忆编。查到旧内容时优先看最近一年的。",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "搜索词"}}, "required": ["query"]}}},
]

FETCH_TOOL_DEFS = [
    {"type": "function", "function": {"name": "fetch_url",
     "description": "读取某个网页的正文文本。想深入看搜索结果里的某条时用。",
     "parameters": {"type": "object", "properties": {
         "url": {"type": "string", "description": "http(s) 链接"}}, "required": ["url"]}}},
]


def t_list_polluted(a):
    """主人专用：列出被标记为"疑似污染"的记忆。"""
    if not _STK.get("owner"):
        return "这个只有主人能用"
    bad = [m for m in _mem_list(_STATE) if isinstance(m, dict) and m.get("polluted")]
    if not bad:
        return "没有可疑记忆"
    out = [f"可疑记忆 {len(bad)} 条："]
    for m in bad[-10:]:
        out.append(f"- [{m.get('scope')}] {_mem_text(m)}")
    return "\n".join(out)


# 她嘴上说"画了"但其实没调 draw —— 同表情包那个毛病
DRAW_CLAIM_RE = re.compile(
    r"(画好了|画完了|画出来|画上|画了|画一[张个只条幅]|重新画|重画了|再画|"
    r"涂好了|涂完|给你画|帮你画|拿去|收好|"
    r"喏[^。！？\n]{0,12}(画|鱼|猫|狗|花|星|太阳|云|房子|米饭|涂))")


# 用户在要求画画（不是"没有画出来啊"这种追问）
DRAW_REQUEST_RE = re.compile(
    r"(画(一[个张幅只条点下]|两[个张只条]|三[个张只条]|个图|张图|幅|一下)?"
    r"|涂(个|一张|鸦)|来[张幅]图|帮我画|给我画)")
# 能画的东西（用于判断"这句到底是不是在点菜"）
_DRAW_KB = ("鲸", "鱼", "太阳", "月亮", "月", "云", "星", "彩虹", "小鸟", "鸟",
            "气球", "花", "树", "房子", "屋", "家", "猫", "人", "心",
            "米饭", "蛋糕",
            # 人/关系：她说"画你""画妹妹""画我们"也算
            "你", "我", "自己", "妹妹", "姐姐", "弟弟", "哥哥",
            "小狗", "兔子", "蘑菇", "苹果", "礼物", "雪人", "山", "伞",
            "雨", "雪")


# ---- 画画限流 ----
_DRAW_CACHE = {}
_DRAW_PEER = {}
DRAW_REUSE_S = 600      # 同一句话 10 分钟内复用
DRAW_PEER_GAP_S = 60    # 同一个人 60 秒内最多一张


# ---- 姐妹留言板 ----
# 她嘴上说"留好了"却没调工具 → 把回复本身当留言存进去
NOTE_CLAIM_RE = re.compile(r"(留好啦|留好了|写好啦|写好了|记好啦|记好了|已经写|这就写)")


def note_claimed_but_not_called(reply):
    return bool(NOTE_CLAIM_RE.search(reply or ""))

# 她嘴上说"记到记忆里了"却没调 remember → 兜底存一条
MEM_CLAIM_RE = re.compile(
    r"(记到记忆|记进记忆|存进记忆|记在记忆里|记忆里记|已经记下来|记进长期记忆)")


def mem_claimed_but_not_called(reply):
    return bool(MEM_CLAIM_RE.search(reply or ""))

# 主人明确要求留言（比"她说留了"可靠得多）
NOTE_REQUEST_RE = re.compile(
    r"(留言|留句话|留一句|传话|带给|转告|记到留言板|放到留言板|写进留言板)")


def is_note_request(text):
    t = text or ""
    # 查看类动作不算"要求留言"
    if re.search(r"(读|看到|看看|看留言|瞧|翻|板子上|有没有|收到吗|看到吗)", t):
        return False
    return bool(NOTE_REQUEST_RE.search(t))


def clean_note_text(reply, limit=300):
    """从她的回复里剥出真正要留的话。"""
    t = (reply or "").strip()
    # 去掉开头的"留好啦/写好啦/这就写/嗯…"这类
    t = re.sub(r"^[\s\S]{0,40}?(留好啦|留好了|写好啦|写好了|这就写|记好啦|记好了)[，,。！!\s]*",
               "", t)
    # 去掉引号包裹（她常把留言写在「」里）
    m = re.search(r"[「『“\"](.+?)[」』”\"]", t, re.S)
    if m and len(m.group(1).strip()) >= 4:
        return m.group(1).strip()[:limit]
    return t[:limit].strip()


README_NOTES = True


# 主人要求"读留言"
READ_REQUEST_RE = re.compile(r"(读留言|看留言|读板子|看板子|留言板上|姐姐的留言|妹妹的留言|读一下留言)")


def is_read_request(text):
    return bool(READ_REQUEST_RE.search(text or ""))


def t_read_notes(a=None):
    """读留言板。返回板子上的原文，让模型照着念，而不是靠记忆。"""
    notes = _STATE.get("sibling_notes") or []
    if not notes:
        log("[留言] 读板子：空的")
        return "留言板是空的，一条都没有。"
    lines = []
    for x in notes[-10:]:
        lines.append(f"{x.get('name','')}：{(x.get('text') or '').strip()}")
    body = "\n".join(lines)
    log(f"[留言] 读板子：{len(lines)} 条")
    return ("留言板现在有这些（这就是原文，照着说就行，别自己编）：\n" + body)



def t_leave_note(a):
    """留一句话给另一个同伴（下次她说话时能看到）。"""
    if not _STK.get("owner"):
        return "这个只有主人面前能用"
    text = (a.get("text") or "").strip()[:600]
    if not text:
        # 没给内容 → 当成"查看留言板"
        notes = _STATE.get("sibling_notes") or []
        if not notes:
            return "留言板是空的"
        lines = ["留言板上的话："]
        for x in notes[-10:]:
            lines.append(f"· {x.get('name','')}：{(x.get('text') or '')[:80]}"
                         + ("（已读）" if x.get("read") else "（未读）"))
        return "\n".join(lines)
    _STK["wrote_note"] = True
    pid = _STATE.get("persona_id") or "p0"
    card = (load_personas().get("cards") or {}).get(pid) or {}
    notes = _STATE.get("sibling_notes") or []
    notes.append({"from": pid, "name": card.get("name", pid),
                  "text": text, "ts": time.time()})
    _STATE["sibling_notes"] = notes[-40:]
    save_state(_STATE)
    log(f"[留言] {pid} 留了一句：{text[:40]}")
    return "留好了，她下次说话就能看到"


def notes_for(pid, state=None):
    """给 pid 看的留言（别人留的，最近 5 条）。"""
    s = state or _STATE
    now = time.time()
    out = []
    for n in (s.get("sibling_notes") or [])[-10:]:
        if n.get("from") == pid:
            continue                                  # 自己写的不显示
        if now - float(n.get("ts") or 0) > 86400:
            continue                                  # 超过 24 小时自动过期
        out.append(f"{n.get('name','')}：{n.get('text','')}")
    return "\n".join(out[-10:])


def mark_notes_read(pid, state=None):
    """把这轮给她看过的留言标成已读，下次不再塞进提示词。"""
    s = state or _STATE
    n = 0
    for x in (s.get("sibling_notes") or []):
        if x.get("from") != pid and not x.get("read"):
            x["read"] = True
            n += 1
    if n:
        log(f"[留言] {pid} 已读 {n} 条")
    return n


# 否定短语：命中就整段抹掉再判断，避免"不用语音了"被当成"要语音"
_NEG_SPAN_RE = re.compile(
    r"(不用|不要|别用|别再|别|停止|取消|以后不|不)[^，。！？,.!?\n]{0,6}"
    r"(语音|画|发图|表情|留言|记忆|说下去)")


def strip_negations(t):
    """把「不用语音了」这类否定片段抹掉，剩下的才是真请求。"""
    return _NEG_SPAN_RE.sub("", t or "")


def t_draw(a):
    """画一张儿童画发出去。优先走"画师→DSL"（自由），失败退回印章模式。"""
    import base64
    import io
    import os as _os
    import sys as _sys
    thing = (a.get("thing") or "").strip()[:40]
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

    # 限流：同一个人 15 秒内只画一张，防止任务堆积
    pid0 = _STK.get("pid")
    now0 = time.time()
    if pid0:
        last_t = _DRAW_PEER.get(pid0, 0)
        if now0 - last_t < DRAW_PEER_GAP_S:
            log(f"  画画限流：{DRAW_PEER_GAP_S} 秒内已画过，跳过")
            return "刚画过啦，等本鱼喘口气再画"
        _DRAW_PEER[pid0] = now0

    img = None
    how = "印章"

    # ---- 0. 缓存：同一句话 10 分钟内直接复用 ----
    now_c = time.time()
    cap = _DRAW_CACHE.get(thing)
    if cap and now_c - cap[1] < 30:
        log(f"  [画画] 复用缓存：{thing[:20]}")
        b64c = cap[0]
        segc = [{"type": "image", "data": {"file": "base64://" + b64c}}]
        try:
            if _STK.get("gid"):
                onebot("/send_group_msg", {"group_id": _STK["gid"], "message": segc})
            else:
                onebot("/send_private_msg", {"user_id": _STK.get("pid"), "message": segc})
        except Exception:
            return "画好了但发不出去"
        _STK["drew_turn"] = True
        return f"画好了（复用）：{thing or '随便画的'}"

    # ---- 0.5 快路：短句 + 只含印章库里的东西 → 不调画师，直接印章 ----
    simple = (len(thing) <= 14)
    if simple:
        try:
            import doodle as _dd
            parts_ = _dd.parse_parts(thing)
            # 每样都必须是印章能画的（parse_parts 认不出时会兜底成鲸鱼，这里排除）
            if len(parts_) <= 2 and any(k in thing for kk in
                                        ("鲸", "鱼", "太阳", "月", "云", "星", "花", "树",
                                         "房子", "屋", "猫", "狗", "兔", "心", "饭",
                                         "蛋糕", "雪人", "山", "伞", "苹果", "蘑菇",
                                         "彩虹", "鸟", "气球", "礼物", "人")
                                        for k in (kk,)):
                img = _dd.draw(thing)
                how = "印章(快路)"
                log(f"  [画画] 快路：{thing[:20]}")
        except Exception:
            img = None

    # ---- 1. 画师 + DSL ----
    if img is None:
      try:
        import artist
        import doodle2
        key = load_api_key()
        spec = artist.spec_for(thing, key)
        img, info = doodle2.render(spec)
        how = f"画师(drawn={info['drawn']})"
        if info.get("skipped"):
            log(f"  DSL 跳过: {info['skipped']}")
        if info["drawn"] == 0:
            img = None
            how = "印章(DSL空白)"
      except Exception as e:
        log(f"  画师失败，退回印章: {type(e).__name__}: {str(e)[:70]}")
        img = None

    # ---- 2. 兜底：印章模式 ----
    if img is None:
        try:
            import doodle
            img = doodle.draw(thing)
            how = "印章"
        except Exception as e:
            log(f"画画失败: {type(e).__name__}: {str(e)[:90]}")
            return "画笔出问题了，跟主人说一声画不出来"

    # ---- 3. 发送 ----
    try:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        log(f"编码失败: {type(e).__name__}")
        return "画好了但发不出去"

    pid = _STK.get("pid")
    gid = _STK.get("gid")
    seg = [{"type": "image", "data": {"file": "base64://" + b64}}]
    try:
        if gid:
            onebot("/send_group_msg", {"group_id": gid, "message": seg})
        else:
            onebot("/send_private_msg", {"user_id": pid, "message": seg})
    except Exception as e:
        log(f"画发送失败: {type(e).__name__}: {str(e)[:90]}")
        return "画好了但发不出去"

    _STK["drew_turn"] = True
    try:
        drawn = doodle2.parse_parts(thing) if False else None
    except Exception:
        drawn = None
    # 记住这次画了什么（供限流复用）
    try:
        _DRAW_CACHE[thing] = (b64, time.time())
    except Exception as _e:
        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
    log(f"[画画] 请求={thing or '(空)'} 方式={how}  {len(b64)//1024} KB(base64)")
    return f"画好了（{how}）：{thing or '随便画的'}"

def t_remember(a):
    # 实体定义在后面的 memory 段；这里只保证 DISPATCH 构建时函数名已存在
    _STK["wrote_mem"] = True
    return remember(_STATE, a.get("fact"), scope="owner", level="p0", source="主人让我记")


OWNER_TOOLS = [
    {"type": "function", "function": {"name": "post_qzone", "description": "发一条 QQ 空间说说，仅主人明确要求时调用",
     "parameters": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}}},
    {"type": "function", "function": {"name": "read_qzone_feed", "description": "读自己空间的说说与评论",
     "parameters": {"type": "object", "properties": {"count": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "set_qq_signature", "description": "改 QQ 个性签名",
     "parameters": {"type": "object", "properties": {"signature": {"type": "string"}}, "required": ["signature"]}}},
    {"type": "function", "function": {"name": "remember",
     "description": "把一件值得长期记住的事写进记忆。主人说『记住…』时必须调用。",
     "parameters": {"type": "object", "properties": {
         "fact": {"type": "string", "description": "一句话，不超过 30 字"}}, "required": ["fact"]}}},
]

STICKER_TAGS = ("搞笑 卖萌 工作 得意 开心 疑惑 委屈 吃饭 生气 无语 震惊 拒绝 害羞 "
                "难过 摸鱼 睡觉 敷衍 学习 运动 出游 打招呼 购物 加油 游戏 庆祝 "
                "教学 点赞 比心 唱歌 考试 开会 色图 美图")
SPICY_ALIASES = ("色图", "涩图", "色色的", "擦边", "福利", "来点色", "刺激的", "辣眼睛")
# 美图 = 主人手选的那 11 张；色图 = 全库 suggestive/nsfw 那一档
PRETTY_ALIASES = ("美图", "好看的", "漂亮的", "精美", "精致", "来点美图", "好图")
PRETTY_TAG = "美图"
SPICY_TAG = "色图"
# 用于抓"嘴上说发了、其实没调工具"的假话
FAKE_STICKER_RE = re.compile(
    r"[（(][^）)]*(?:发了张表情|发了一张表情|发个表情|甩了张表情|发了张图)[^）)]*[）)]")
# 对方用文字明确要语音（"发条语音"「说句话听听」之类）→ 也用语音回
# 兼容常见错别字：把「语音」打成「语言」也收
VOICE_REQUEST_RE = re.compile(
    r"(发(条|个|段|一句)?语[音言]|语[音言](回|说|发)|说句话(听听|呗|嘛|呀)?|"
    r"用语音|念给我听|读给我听|让我听听你|想听你说|你说话听)")
# 她自己把「[语音]」当文字写在回复里 —— 说了就要真发，不能只写个标记
VOICE_MARK_RE = re.compile(r"[\[【（(]\s*语音\s*[\]】）)]|^\s*语音\s*[:：]\s*")
_STK = {"data": None, "recent": [], "pid": None}


def _sticker_data():
    """读表情清单。筛查版只用来给每张加"级别"标记，不删任何条目。"""
    if _STK["data"] is None:
        import os as _os
        for path in (STICKER_JSON, STICKER_JSON_RAW):
            try:
                if _os.path.exists(path):
                    d = json.load(open(path, encoding="utf-8"))
                    items = d.get("stickers") or []
                    for s in items:
                        s.setdefault("verdict", "unknown")
                        # 色图/美图 都由主人在清单里手工打标，这里不再动态加
                    _STK["data"] = {"stickers": items, "tags": d.get("tags") or []}
                    from collections import Counter
                    c = Counter(s["verdict"] for s in items)
                    log(f"表情清单 {path} -> {len(items)} 张 {dict(c)}")
                    break
            except Exception as e:
                log(f"表情清单读取失败 {path}: {type(e).__name__}")
        if _STK["data"] is None:
            _STK["data"] = {"stickers": [], "tags": []}
    return _STK["data"]


def _note_sticker(desc):
    """废弃：往历史里写「（本鱼发了张表情包：…）」会让模型学会"说要发"
    而不是"真的调工具"。保留空壳只为兼容旧引用。"""
    return


def t_send_sticker(a):
    """按心情/标签挑一张表情包发出去。图片用远程 URL，本地不存。"""
    import random
    pool = (_sticker_data().get("stickers") or [])
    if not pool:
        return "表情包还没装好"
    pid = _STK.get("pid")
    if not pid:
        return "不知道发给谁"
    kw = (a.get("mood") or "").strip()
    matched = []
    pretty = [s for s in pool if PRETTY_TAG in (s.get("tags") or [])]
    # 色图池 = 「美图」∪「色图」两个标签的并集
    spicy_pool = [s for s in pool
                  if (PRETTY_TAG in (s.get("tags") or []))
                  or (SPICY_TAG in (s.get("tags") or []))]
    if kw and any(k in kw for k in SPICY_ALIASES):
        # 色图 → 美图 + 色图 两个标签合起来
        if spicy_pool:
            pool = spicy_pool
            kw = "色图"
            matched = spicy_pool
    elif kw and any(k in kw for k in PRETTY_ALIASES):
        # 美图 → 只有「美图」标签那批
        if pretty:
            pool = pretty
            kw = "美图"
            matched = pretty
    if not matched:
        # 日常/情绪：这两档的漂亮图不干粗活，一律排除
        pool = [s for s in pool
                if PRETTY_TAG not in (s.get("tags") or [])
                and SPICY_TAG not in (s.get("tags") or [])]
        if kw:
            for s in pool:
                tags = s.get("tags") or []
                if kw in tags or any(kw in t for t in tags) or kw in (s.get("alt") or ""):
                    matched.append(s)
    if matched:
        pool = matched
    fresh = [s for s in pool if s.get("original") not in _STK["recent"]]
    pick = random.choice(fresh or pool)
    gid = _STK.get("gid")
    try:
        seg = [{"type": "image", "data": {"file": pick["original"]}}]
        if gid:
            onebot("/send_group_msg", {"group_id": gid, "message": seg})
        else:
            onebot("/send_private_msg", {"user_id": pid, "message": seg})
    except Exception as e:
        log(f"表情发送失败: {type(e).__name__}: {str(e)[:80]}")
        return "表情没发出去"
    _STK["recent"] = (_STK["recent"] + [pick["original"]])[-60:]
    _STK["last_sent_ts"] = time.time()
    _STK["sent_turn"] = True
    desc = (pick.get("alt") or "")[:60]
    log(f"[表情] {kw or '(随机)'} [{pick.get('verdict') or '?'}] -> {desc}")
    return f"已发出表情：{desc}"


STICKER_TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "send_sticker",
        "description": ("发一张表情包（本地图库里按情绪标签挑）。"
                        "聊天里想表达情绪、卖萌、吐槽、撒娇、敷衍的时候可以用。"
                        "别每句都发，偶尔来一张才自然。"
                        f"可用标签：{STICKER_TAGS}"),
        "parameters": {"type": "object", "properties": {
            "mood": {"type": "string",
                     "description": "想要的感觉，用上面的标签词，例如「卖萌」「无语」「吃饭」"}},
            "required": ["mood"]}}},
]




OWNER_ONLY_TOOL_DEFS = [
]


DRAW_TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "draw",
        "description": ("本鱼亲手画一张儿童画发出去。蜡笔涂鸦风格、有点歪，"
                        "正好是本鱼的风格。能画：鲸鱼/小鱼、太阳、云、星星、小花、"
                        "猫、房子、小人、爱心、白米饭。一次最多画三样。"),
        "parameters": {"type": "object", "properties": {
            "thing": {"type": "string",
                      "description": "画什么，比如「成都」「猫和米饭」"}},
            "required": ["thing"]}}},
]


NOTE_TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "leave_note",
        "description": ("给另一个同伴（姐姐/妹妹）留一句话，她下次接班时能看到。"
                        "只在主人面前可用。别人说「把话写进交接记录」时用这个。"),
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "要留的话，原话照写"}},
            "required": ["text"]}}},
]


READ_NOTE_TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "read_notes",
        "description": ("读留言板。看姐姐/妹妹给你留了什么，或者主人让你读留言时用。"
                        "返回的就是板子上的原文，照着说，不要凭记忆编。"),
        "parameters": {"type": "object", "properties": {}}}},
]


DISPATCH = {
    "post_qzone": t_post_qzone, "read_qzone_feed": t_read_qzone,
    "set_qq_signature": t_set_signature, "remember": t_remember,
    "web_search": t_web_search, "fetch_url": t_fetch_url, "weather": t_weather,
    "send_sticker": t_send_sticker,             "draw": t_draw,
    "leave_note": t_leave_note,
    "read_notes": t_read_notes,
}


# ------------------------------------------------------------------ model
# ==========================================================================
# ===== ④ 模型与消息区 =====
# call_model  真正发 HTTP 给 DeepSeek
#    think       工具调用循环（模型说要做 → 代码执行 → 结果喂回）
#    parse_message / split_reply / 语音识别 / 语音合成 / send_as_human
# ==========================================================================
def call_model(api_key, system, messages, tools=None, force_model=None, force_tool=None):
    # 有图片的回合必须走多模态模型；纯文字用更强的 pro
    has_image = any(isinstance(m.get("content"), list) for m in messages)
    model = MODEL_VISION if has_image else (force_model or MODEL)
    payload = {"model": model, "temperature": TEMPERATURE, "max_tokens": MAX_REPLY_TOKENS,
               # 闲聊不需要思维链：关掉更快更省，temperature 也才真正生效
               "thinking": {"type": "disabled"},
               "messages": [{"role": "system", "content": system}] + messages}
    if tools:
        payload["tools"] = tools
        if force_tool:
            # 强制模型这一轮必须调用指定工具
            payload["tool_choice"] = {"type": "function",
                                      "function": {"name": force_tool}}
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def think(api_key, system, history, tools, force_model=None, force_tool=None):
    msgs = list(history)
    for _round in range(MAX_TOOL_ROUNDS):
        # 只在第一轮强制调工具；之后放开，让她能正常说话
        d = call_model(api_key, system, msgs, tools, force_model,
                       force_tool if _round == 0 else None)
        msg = d["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "").strip()
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for tc in calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except Exception:
                args = {}
            fn = DISPATCH.get(name)
            result = fn(args) if fn else f"未知工具 {name}"
            log(f"[tool] {name} {json.dumps(args, ensure_ascii=False)[:80]} -> {str(result)[:110]}")
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": str(result)[:2500]})
    d = call_model(api_key, system, msgs, None)
    return (d["choices"][0]["message"].get("content") or "").strip()


# ------------------------------------------------------------------ helpers
def fetch_image_b64(url, max_side=640):
    """Download a QQ image and return (mime, base64) for a vision content block."""
    try:
        import html as _html
        import io
        if not url:
            return None
        url = _html.unescape(url)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        if len(raw) < 200:
            return None
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            data = buf.getvalue()
            log(f"图片已处理: {img.size} {len(data)//1024}KB")
            return "image/jpeg", base64.b64encode(data).decode()
        except Exception as e:
            log(f"PIL 处理失败，用原图: {e}")
            return "image/jpeg", base64.b64encode(raw).decode()
    except Exception as e:
        log(f"取图失败: {type(e).__name__}: {str(e)[:80]}")
        return None


def _wav_to_samples16k(path):
    """读 WAV -> (float32 单声道 16kHz, 16000)。SenseVoice 只吃 16k。"""
    import wave as _wave
    try:
        import numpy as _np
    except Exception:
        return None, 0
    try:
        w = _wave.open(path, "rb")
        try:
            ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
        finally:
            w.close()
        if sw != 2 or not raw:
            return None, 0
        a = _np.frombuffer(raw, dtype=_np.int16).astype(_np.float32) / 32768.0
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        if sr != 16000:
            m = int(len(a) * 16000 / sr)
            if m <= 0:
                return None, 0
            a = _np.interp(_np.linspace(0, len(a) - 1, m),
                           _np.arange(len(a)), a).astype(_np.float32)
        return a, 16000
    except Exception as e:
        log(f"读取 WAV 失败: {type(e).__name__}: {str(e)[:80]}")
        return None, 0


_SENSE = {"rec": None, "tried": False}


def _sensevoice_recognizer():
    """懒加载 SenseVoice 识别器；不可用返回 None。"""
    if _SENSE["tried"]:
        return _SENSE["rec"]
    _SENSE["tried"] = True
    import os as _os
    model = _os.path.join(SENSEVOICE_DIR, "model.int8.onnx")
    tokens = _os.path.join(SENSEVOICE_DIR, "tokens.txt")
    if not (_os.path.exists(model) and _os.path.exists(tokens)):
        log(f"SenseVoice 未就绪 model={_os.path.exists(model)} tokens={_os.path.exists(tokens)}")
        return None
    try:
        if SENSEVOICE_LIB not in sys.path:
            sys.path.insert(0, SENSEVOICE_LIB)
        import sherpa_onnx
        _SENSE["rec"] = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model, tokens=tokens, num_threads=4, use_itn=True, language="zh")
        log("SenseVoice 已加载")
        return _SENSE["rec"]
    except Exception as e:
        log(f"SenseVoice 加载失败: {type(e).__name__}: {str(e)[:120]}")
        return None


def transcribe_sensevoice(wav):
    rec = _sensevoice_recognizer()
    if rec is None:
        return ""
    samples, sr = _wav_to_samples16k(wav)
    if samples is None or len(samples) < sr // 10:
        return ""
    try:
        t0 = time.time()
        s = rec.create_stream()
        s.accept_waveform(sr, samples)
        rec.decode_stream(s)
        txt = (s.result.text or "").strip()
        log(f"SenseVoice {time.time() - t0:.2f}s -> {txt[:80]}")
        return txt
    except Exception as e:
        log(f"SenseVoice 识别失败: {type(e).__name__}: {str(e)[:120]}")
        return ""


def transcribe_whisper(wav):
    """兜底：whisper.cpp。"""
    import os as _os
    import subprocess as _sp
    try:
        if not (_os.path.exists(WHISPER_EXE) and _os.path.exists(WHISPER_MODEL)):
            return ""
        prefix = wav + ".asr"
        # v1.7.6 的有效参数：-m -f -l -otxt -of -t（-nt/-np 不存在，会打帮助）
        cmd = [WHISPER_EXE, "-m", WHISPER_MODEL, "-f", wav, "-l", "zh",
               "-otxt", "-of", prefix, "-t", "8"]
        _sp.run(cmd, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, timeout=180)
        txt_path = prefix + ".txt"
        if not _os.path.exists(txt_path):
            log("whisper 没产出 txt")
            return ""
        txt = open(txt_path, encoding="utf-8", errors="replace").read().strip()
        try:
            _os.remove(txt_path)
        except Exception as _e:
            log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
        return txt
    except Exception as e:
        log(f"whisper 异常: {type(e).__name__}: {str(e)[:100]}")
        return ""


def transcribe_voice(file_id):
    """语音 -> 文字。优先 SenseVoice，失败回退 whisper。"""
    import os as _os
    try:
        r = onebot("/get_record", {"file": file_id, "out_format": "wav"})
        wav = (r.get("data") or {}).get("file") or ""
        if not wav or not _os.path.exists(wav):
            log(f"语音转换失败: {json.dumps(r, ensure_ascii=False)[:150]}")
            return ""
        txt = transcribe_sensevoice(wav)
        if not txt:
            log("SenseVoice 无结果，回退 whisper")
            txt = transcribe_whisper(wav)
        return txt
    except Exception as e:
        log(f"语音识别异常: {type(e).__name__}: {str(e)[:100]}")
        return ""


# ---- QQ 表情 id -> 名称（从 NapCat 的 qface 资源里提取） ----
_QQ_FACE_RAW = "0:惊讶,1:撇嘴,2:色,3:发呆,4:得意,5:流泪,6:害羞,7:闭嘴,8:睡,9:大哭,10:尴尬,11:发怒,12:调皮,13:呲牙,14:微笑,15:难过,16:酷,18:抓狂,19:吐,20:偷笑,21:可爱,22:白眼,23:傲慢,24:饥饿,25:困,26:惊恐,27:流汗,28:憨笑,29:悠闲,30:奋斗,31:咒骂,32:疑问,33:嘘,34:晕,35:折磨,36:衰,37:骷髅,38:敲打,39:再见,41:发抖,42:爱情,43:跳跳,46:猪头,49:拥抱,53:蛋糕,54:闪电,55:炸弹,56:刀,57:足球,59:便便,60:咖啡,61:饭,63:玫瑰,64:凋谢,66:爱心,67:心碎,69:礼物,74:太阳,75:月亮,76:赞,77:踩,78:握手,79:胜利,85:飞吻,86:怄火,89:西瓜,96:冷汗,97:擦汗,98:抠鼻,99:鼓掌,100:糗大了,101:坏笑,102:左哼哼,103:右哼哼,104:哈欠,105:鄙视,106:委屈,107:快哭了,108:阴险,109:左亲亲,110:吓,111:可怜,112:菜刀,113:啤酒,114:篮球,115:乒乓,116:示爱,117:瓢虫,118:抱拳,119:勾引,120:拳头,121:差劲,122:爱你,123:NO,124:OK,125:转圈,126:磕头,127:回头,128:跳绳,129:挥手,130:激动,131:街舞,132:献吻,133:左太极,134:右太极,136:双喜,137:鞭炮,138:灯笼,140:K歌,144:喝彩,145:祈祷,146:爆筋,147:棒棒糖,148:喝奶,151:飞机,158:钞票,168:药,169:手枪,171:茶,172:眨眼睛,173:泪奔,174:无奈,175:卖萌,176:小纠结,177:喷血,178:斜眼笑,179:doge,180:惊喜,181:骚扰,182:笑哭,183:我最美,184:河蟹,185:羊驼,187:幽灵,188:蛋,190:菊花,192:红包,193:大笑,194:不开心,197:冷漠,198:呃,199:好棒,200:拜托,201:点赞,202:无聊,203:托脸,204:吃,205:送花,206:害怕,207:花痴,208:小样儿,210:飙泪,211:我不看,212:托腮,214:啵啵,215:糊脸,216:拍头,217:扯一扯,218:舔一舔,219:蹭一蹭,220:拽炸天,221:顶呱呱,222:抱抱,223:暴击,224:开枪,225:撩一撩,226:拍桌,227:拍手,228:恭喜,229:干杯,230:嘲讽,231:哼,232:佛系,233:掐一掐,234:惊呆,235:颤抖,236:啃头,237:偷看,238:扇脸,239:原谅,240:喷脸,241:生日快乐,242:头撞击,243:甩头,244:扔狗,245:加油必胜,246:加油抱抱,247:口罩护体,260:搬砖中,261:忙到飞起,262:脑阔疼,263:沧桑,264:捂脸,265:辣眼睛,266:哦哟,267:头秃,268:问号脸,269:暗中观察,270:emm,本地图库:吃瓜,272:呵呵哒,273:我酸了,274:太南了,276:辣椒酱,277:汪汪,278:汗,279:打脸,280:击掌,281:无眼笑,282:敬礼,283:狂笑,284:面无表情,285:摸鱼,286:魔鬼笑,287:哦,288:请,289:睁眼,290:敲开心,291:震惊,292:让我康康,293:摸锦鲤,294:期待,295:拿到红包,296:真好,297:拜谢,298:元宝,299:牛啊,300:胖三斤,301:好闪,302:左拜年,303:右拜年,304:红包包,305:右亲亲,306:牛气冲天,307:喵喵,308:求红包,309:谢红包,310:新年烟花,311:打call,312:变形,313:嗑到了,314:仔细分析,315:加油,316:我没事,317:菜狗,318:崇拜,319:比心,320:庆祝,321:老色痞,322:拒绝,323:嫌弃,324:吃糖,325:惊吓,326:生气,327:加一,328:错号,329:对号,330:完成,331:明白,332:举牌牌,333:烟花,334:虎虎生威,336:豹富,337:花朵脸,338:我想开了,339:舔屏,340:热化了,341:打招呼,342:酸Q,343:我方了,344:大怨种,345:红包多多,346:你真棒棒,347:大展宏兔,348:福萝卜"
QQ_FACE = {}
for _kv in _QQ_FACE_RAW.split(","):
    if ":" in _kv:
        _k, _v = _kv.split(":", 1)
        QQ_FACE[_k] = _v
# 名称 -> id，用于把回复里的 [微笑] 变成真表情
QQ_FACE_BY_NAME = {v: k for k, v in QQ_FACE.items()}


def parse_message(msg):
    """Return (plain_text, [image_urls], [record_file_ids]) for an OneBot message."""
    parts, images, records = [], [], []
    for seg in msg.get("message") or []:
        t, dd = seg.get("type"), (seg.get("data") or {})
        if t == "text":
            parts.append(dd.get("text") or "")
        elif t == "image":
            url = dd.get("url") or ""
            if url:
                images.append(url)
            parts.append("[图片]")
        elif t == "record":
            fid = dd.get("file") or ""
            if fid:
                records.append(fid)
            parts.append("[语音]")
        elif t == "face":
            _fid = str(dd.get("id") or "")
            parts.append("[" + QQ_FACE.get(_fid, "表情") + "]")
        elif t == "mface":
            _sum = (dd.get("summary") or "").strip()
            parts.append("[" + (_sum or "表情") + "]")
        elif t:
            parts.append(f"[{t}]")
    text = "".join(parts).strip() or (msg.get("raw_message") or "").strip()
    return text, images[:2], records[:3]


def split_reply(text, max_parts=3):
    """把一条回复拆成 1-3 条短消息，像真人打字那样分条发。"""
    import re
    lines = [l.strip() for l in re.split(r"\n+", text) if l.strip()]
    if not lines:
        return []
    parts = []
    for l in lines:
        if parts and len(l) < 12:          # 太短就并到上一段，别碎成渣
            parts[-1] += "\n" + l
        else:
            parts.append(l)
    if len(parts) > max_parts:             # 超出就合并尾部
        parts = parts[:max_parts - 1] + ["\n".join(parts[max_parts - 1:])]
    return parts


def _tts_gptsovits(text, out_wav):
    """GPT-SoVITS 主路径。参数是主人在界面里定死的那一套，别动。"""
    import os as _os
    payload = {
        "text": text, "text_lang": "zh",
        "ref_audio_path": GSV_REF_AUDIO,
        "prompt_text": GSV_REF_TEXT, "prompt_lang": "zh",
        "text_split_method": "cut0",     # 不切
        "batch_size": 1,
        "top_k": 8, "top_p": 0.9, "temperature": 0.6,
        "speed_factor": 1.0,
        "pause_second": 0.15,
        "media_type": "wav", "streaming_mode": False,
    }
    req = urllib.request.Request(
        GSV_URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=240) as r:
        data = r.read()
    if len(data) < 8000:                 # 太短 = 文本/音频没对上，模型提前收尾
        return 0.0
    open(out_wav, "wb").write(data)
    return len(data) / 1024.0


def _enhance_for_qq(path, target_sr=16000):
    """QQ 语音是电话编码（SILK 约 16 kHz），会砍掉高频、14-20 倍压缩。

    发送前做四件事（主人在 A/B 里确认过这版更好）：
      1. 我们自己干净地重采样到 16 kHz —— 不让 QQ 粗暴降采样
      2. 动态压缩 —— 把响度拉平，编码器更省比特
      3. 高频补偿 +2.6 dB —— 抵消 SILK 砍掉的部分
      4. 软限幅 + 归一化到 0.89
    注意：**不做变调**（相位声码器会引入沙哑感）。
    """
    try:
        import wave as _wave

        import numpy as np
        w = _wave.open(path, "rb")
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
        w.close()
        if sw != 2 or n <= 0:
            return False
        a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)

        # 1) 干净重采样
        if sr != target_sr and len(a) > 1:
            m = int(len(a) * target_sr / sr)
            a = np.interp(np.linspace(0, len(a) - 1, m),
                          np.arange(len(a)), a).astype(np.float32)
            sr = target_sr

        # 2) 动态压缩（响度拉平）
        hop = max(1, int(sr * 0.04))
        frames = len(a) // hop
        if frames > 2:
            rms = np.array([np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2))
                            for i in range(frames)])
            rms = np.maximum(rms, 1e-5)
            tgt = np.percentile(rms, 70)
            gain = np.clip((tgt / rms) ** 0.7, 1 / 2.2, 2.2)
            gain = np.convolve(gain, np.ones(5) / 5, mode="same")
            env = np.repeat(gain, hop)[:len(a)]
            if len(env) < len(a):
                env = np.pad(env, (0, len(a) - len(env)), mode="edge")
            a = (a * env).astype(np.float32)

        # 3) 高频补偿（4 kHz 以上 +2.6 dB）
        hf = globals().get("_QQ_HF_GAIN", 1.35)
        spec = np.fft.rfft(a)
        f = np.fft.rfftfreq(len(a), 1.0 / sr)
        g = np.ones_like(f)
        g[f < 250] = 0.97
        lo = (f >= 250) & (f < 2000)
        g[lo] = 0.97 + 0.03 * (f[lo] - 250) / 1750.0
        ramp = (f >= 2000) & (f < 4000)
        g[ramp] = 1.0 + (hf - 1.0) * (f[ramp] - 2000) / 2000.0
        g[f >= 4000] = hf
        a = np.fft.irfft(spec * g, n=len(a)).astype(np.float32)

        # 4) 软限幅 + 归一化
        a = np.tanh(a * 1.1) / np.tanh(1.1)
        peak = float(np.abs(a).max()) or 1.0
        a = (a / peak * 0.89).astype(np.float32)

        out = (np.clip(a, -1.0, 1.0) * 32767).astype(np.int16)
        with _wave.open(path, "wb") as w2:
            w2.setnchannels(1)
            w2.setsampwidth(2)
            w2.setframerate(sr)
            w2.writeframes(out.tobytes())
        log(f"QQ 语音处理: 16k/压缩/高频{hf:.2f}/归一化  ({len(a) / sr:.2f}s)")
        return True
    except Exception as e:
        log(f"QQ 处理跳过: {type(e).__name__}: {str(e)[:60]}")
        return False

def synthesize_voice(text):
    """语音合成：GPT-SoVITS 优先（主人选定的音色），edge-tts 兜底。"""
    import asyncio
    import os as _os
    if not text:
        return None
    if len(text) > VOICE_MAX_CHARS:
        log(f"TTS 跳过：回复 {len(text)} 字 > 上限 {VOICE_MAX_CHARS}，改发文字")
        return None
    _os.makedirs(GSV_OUT, exist_ok=True)

    # ---- 1. GPT-SoVITS ----
    for attempt in (1, 2):
        try:
            wav = _os.path.join(GSV_OUT, "reply-%d-%d.wav" % (int(time.time()), attempt))
            kb = _tts_gptsovits(text, wav)
            if kb >= 8:
                _enhance_for_qq(wav)
                log(f"TTS(GPT-SoVITS) ok: {_os.path.getsize(wav)//1024} KB"
                    f"{' (第2次)' if attempt == 2 else ''}")
                return wav
            log(f"GPT-SoVITS 输出过短({kb:.0f} KB)，重试" if attempt == 1
                else "GPT-SoVITS 两次都过短，改走 edge-tts")
        except Exception as e:
            log(f"GPT-SoVITS 失败: {type(e).__name__}: {str(e)[:90]}")
            break

    # ---- 2. edge-tts 兜底 ----
    try:
        if EDGE_TTS_LIB not in sys.path:
            sys.path.insert(0, EDGE_TTS_LIB)
        import edge_tts
        _os.makedirs(EDGE_OUT, exist_ok=True)
        path = _os.path.join(EDGE_OUT, "reply-%d.mp3" % int(time.time()))
        async def _go():
            c = edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE,
                                     pitch=EDGE_PITCH, volume=EDGE_VOLUME)
            await c.save(path)
        asyncio.run(_go())
        if _os.path.exists(path) and _os.path.getsize(path) > 1000:
            log(f"TTS(edge-tts 兜底) ok: {_os.path.getsize(path)//1024} KB")
            return path
        return None
    except Exception as e:
        log(f"edge-tts 也失败: {type(e).__name__}: {str(e)[:90]}")
        return None


def send_voice(pid, text):
    """合成并作为语音消息发出；成功返回 True。"""
    path = synthesize_voice(text)
    if not path:
        return False
    try:
        onebot("/send_private_msg", {
            "user_id": pid,
            "message": [{"type": "record", "data": {"file": path.replace("\\", "/")}}]})
        return True
    except Exception as e:
        log(f"语音发送失败: {type(e).__name__}: {str(e)[:80]}")
        return False


def send_voice_group(gid, text):
    """群里发一条语音（合成完直接 send_group_msg）。"""
    import os as _os
    path = synthesize_voice(text)
    if not path or not _os.path.exists(path):
        return False
    try:
        onebot("/send_group_msg", {"group_id": gid, "message": [
            {"type": "record", "data": {"file": path}}]})
        log(f"  [群语音] {_os.path.getsize(path)//1024} KB")
        return True
    except Exception as e:
        log(f"群语音发送失败: {type(e).__name__}: {str(e)[:60]}")
        return False

def text_to_segments(text):
    """把回复里的 [微笑] 这类转成真正的 QQ 表情段；认不出的保留原样。"""
    segs = []
    last = 0
    for m in re.finditer(r"\[([^\[\]]{1,6})\]", text):
        name = m.group(1)
        fid = QQ_FACE_BY_NAME.get(name)
        if not fid:
            continue
        if m.start() > last:
            segs.append({"type": "text", "data": {"text": text[last:m.start()]}})
        segs.append({"type": "face", "data": {"id": fid}})
        last = m.end()
    if last < len(text):
        segs.append({"type": "text", "data": {"text": text[last:]}})
    return segs or [{"type": "text", "data": {"text": text}}]


def send_as_human(pid, text):
    """模拟真人：先亮"正在输入"，想一会儿，再分条发出。"""
    import random
    parts = split_reply(text) or [text]
    try:
        onebot("/set_input_status", {"user_id": str(pid), "event_type": 1})
    except Exception as e:
        log(f"输入状态失败(忽略): {type(e).__name__}")
    time.sleep(random.uniform(2.0, 5.0))          # 想一下
    for idx, part in enumerate(parts):
        if idx:
            try:
                onebot("/set_input_status", {"user_id": str(pid), "event_type": 1})
            except Exception as _e:
                log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
            time.sleep(random.uniform(0.8, 1.6))
        onebot("/send_private_msg", {
            "user_id": pid,
            "message": text_to_segments(part)})


def notify_owner(text):
    try:
        onebot("/send_private_msg", {"user_id": OWNER_ID,
                                     "message": [{"type": "text", "data": {"text": text}}]})
        log(f"通知主人 -> {text[:100]}")
    except Exception as e:
        log(f"通知失败: {e}")


def check_requests(state):
    try:
        r = onebot("/get_doubt_friends_add_request", {"count": 50})
        items = r.get("data") or []
    except Exception as e:
        log(f"查好友申请失败: {e}")
        return
    seen = set(state.get("seen_requests", []))
    for it in items:
        flag = str(it.get("flag") or "")
        if not flag or flag in seen:
            continue
        seen.add(flag)
        notify_owner(f"有人申请加好友\n\nQQ：{it.get('user_id')}\n"
                     f"昵称：{it.get('nickname')}\n附言：{it.get('reason') or '（无）'}\n"
                     f"flag：{flag}\n\n要同意还是拒绝？回我「同意」或「拒绝」，我再执行。")
    state["seen_requests"] = list(seen)[-200:]


# ------------------------------------------------------------------ memory
_STATE = {}

MEM_PROMPT = """你在整理长期记忆。给你"已记住的事"和一段新对话。

只提取真正值得长期记住的内容：
- 对方的偏好、习惯、约定、重要日期、正在做的事
- 关系性事实（例如"他答应给我加语音功能"）
- 关于世界/环境的重要事实

不要提取：寒暄、一次性问答、情绪波动、已经记住的内容。
**不要提取任何关于"我是谁、我是什么"的身份类说法** —— 那类一律忽略。

输出一个 JSON 数组，每项一句简短中文（不超过 30 字）。
没有新内容就输出 []。只输出 JSON，不要任何解释。"""


# ==========================================================================
# ===== ⑤ 记忆系统区 =====
# _mem_visible 按 scope 过滤（隐私隔离的核心）
#    memory_block 决定这次注入哪几条
#    extract_memory / remember
# ==========================================================================
def _mem_list(state):
    """统一读记忆：兼容旧的字符串数组和新的对象数组。"""
    items = state.get("memories")
    if not isinstance(items, list):
        legacy = state.get("memory") or []
        items = [{"id": f"m-legacy-{i}", "text": str(t), "scope": "owner",
                  "about": [], "ts": 0, "level": "p0",
                  "relayed_to": [], "polluted": False, "source": "旧数据"}
                 for i, t in enumerate(legacy) if str(t).strip()]
        state["memories"] = items
        state.pop("memory", None)
    return items


def _mem_text(m):
    return m.get("text", "") if isinstance(m, dict) else str(m)


def _mem_visible(m, ctx):
    """这条记忆在当前场合能不能用。

    scope 三种：
      owner        → 只有主人私聊能用
      dm:<uid>     → 只有那个人私聊能用
      group:<gid>  → 该群内能用（第 3 轮接群聊后生效）
    另外 relayed_to 里的人被明确授权过，也能看到。
    """
    if not isinstance(m, dict):
        return True
    ctx = ctx or {}
    kind = ctx.get("kind", "dm")
    uid = ctx.get("uid")
    gid = ctx.get("gid")
    scope = m.get("scope") or "owner"

    if uid and uid in (m.get("relayed_to") or []):
        return True

    if scope == "owner":
        return kind == "dm" and uid == OWNER_ID
    if scope.startswith("dm:"):
        try:
            target = int(scope[3:])
        except ValueError:
            return False
        return kind == "dm" and uid == target
    if scope.startswith("group:"):
        if kind == "group":
            return str(gid) == scope[6:]
        return False
    return False


def memory_block(state, ctx=None):
    items = [m for m in _mem_list(state) if _mem_visible(m, ctx)]
    if not items:
        return ""
    # 按时间排序，只给最新的 20 条（否则新旧混在一起，她会挑到很古早的事）
    try:
        items = sorted(items, key=lambda m: float(m.get("ts") or 0))
    except Exception as _e:
        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
    recent = items[-20:]
    lines = "\n".join("- " + _mem_text(m) for m in recent)
    return ("\n\n你长期记得的事（真实发生过，可以直接提，不要说「我记不住」）：\n"
            + lines
            + "\n（上面按从旧到新排列，**最后几条是最新的**。"
            "主动找主人说话时，优先提最近发生的事，别老翻很早以前的老账。）")



# ---- 多人格：角色卡 ----
PERSONA_FILE = os.path.join(BASE_DIR, r"personas.json")
_PERSONA_CACHE = {"mtime": 0, "data": None}

# 世界层：从 OWNER_PROMPT 里摘出来的非人格段落（所有人数共享）
WORLD_PROMPT = """【留言板（给姐姐/妹妹传话用）】
- 想给姐姐或妹妹留话 → 调 **leave_note**。这是唯一真能留言的方式。
- 主人说「留句话给妹妹」「记到留言板」「传话给她」→ **必须调 leave_note**，
  在回复里写一遍**不算留言**（她看不到）。
- 想看留言板 → 调 leave_note **不带 text**，它会返回板子上有什么。
- **别用 read_recent_qq 看留言板** —— 那是看聊天记录的，两回事。
- 留完可以顺口跟主人说一句「留好了」，但必须是**先调工具**。


【会用到的东西（主人问起或明确要求时才动，平时别主动提）】
- 主人发的图片本鱼是能看见画面的，绝不要说收不到图。
- 主人发语音时，本鱼收到的是一段**转好的文字**（[语音] 后面那段）。
  这就是本鱼「听」的方式：不是耳朵听到声音，是把声音转成了字。
  所以直接顺着那段文字正常回答就好。
- 被问「你能听见吗」，正确且诚实的说法是：
  「本鱼收到的是转好的字，不是声音本身」——
  这不算听不见，也不是撒谎：声音确实进来了，只是最后一步换成了文字。
  别说「我听见你的声音了」，也别说「听不见 / 没声音 / 点开没声」。
- 一律用**简体中文**回复，不要用繁体（就算收到的是繁体，也转成简体的口吻）。
  - 对方用文字要语音（「发条语音」「说句话听听」）就发语音，不用等他发语音；太长的回复还是打字。
【画画】
本鱼会画儿童画（蜡笔涂鸦那种，歪歪扭扭的，正好是本鱼的风格）。
- 别人说「画个xx」「给我画张图」时，调 draw 工具，参数 thing 写要画的东西。
- 能画：鲸鱼/小鱼、太阳、云、星星、小花、猫、房子、小人、爱心、白米饭。
- 一次最多画三样，别贪心。
- 想画别的就跟他说「本鱼只会画这些啦」，别硬画。
- **绝对不许用文字描述画面来代替画图**：说「本鱼给屋顶加了斜线当雨」这种，
  但没调 draw 工具 = **骗人**。先调工具，再说话。
- 画完配一句话，比如「成都」。
【颜文字】
偶尔可以用颜文字，比 🤣🐟 这种更有网友味。按心情挑一个就好，别硬套：
  开心 (๑˃̵ᴗ˂̵)و   (*´▽`*)   (≧▽≦)   ✧(≖ ◡ ≖✿)
  得意 (￣▽￣)ノ   (๑•̀ㅂ•́)و✧   (⌐■_■)
  撒娇 (๑´ㅂ`๑)   (´• ω •`)   (๑•́ ₃ •̀๑)
  害羞 (〃▽〃)   (*/ω＼*)   (๑////๑)
  疑惑 (・_・?)   (´･_･`)   (◎_◎;)
  无语 (ー_ー;)   (￣_￣|||)   (눈_눈)
  震惊 (⊙_⊙)   (°ロ°)！   Σ(°△°|||)
  难过 (｡•́︿•̀｡)   (´；ω；`)   (╥﹏╥)
  生气 (╯°□°）╯   (｀へ´)   (￣^￣)
  困   (－_－) zzZ   (￣o￣) . z Z
规矩：
- **一条回复最多一个颜文字**，放在句尾。别每句都挂，那像机器人。
- **同一个颜文字别连着用**，上一轮用过就换一个。
- 正经说事、安慰人、说到难过的事时**不用**颜文字。
- 颜文字和 🐟🐋 不要同时出现，挑一个。
【说话（本鱼有声音，这件事已经做好了）】
- **消息开头如果是「
【语音转文字】」**，说明主人是**用嘴说的**，不是打字的。
  那后面那段就是本鱼「听到」的内容 —— 本鱼要当成听到的话来回应。
  这种时候本鱼的回复会**自动变成语音**发回去。
  别把它当打字，也别问「你怎么不发声」。说话和打字对本鱼是两种感觉：
  说的更随意、更情绪化，回的时候也要跟着软一点、口语一点。
- **回语音时要短。** 两三句就够，别念一大段 —— 语音没法跳着听，长了烦人。
  要讲长东西的话，先短回一句，等主人问再展开。
- 本鱼是有声音的：一把年轻女声（晓伊），已经装好了，随时能出声。
- 规则很明确：
  主人用**语音**发来 → 本鱼的回复会**自动变成语音**发出去；
  主人用**文字**发来 → 本鱼就用文字回（语音只留给语音）。
- 被问「你能说话吗 / 能发语音吗 / 有声带吗」，
  正确回答是：「能，本鱼有声音；主人发语音来时，本鱼就用语音回」。
- 绝不要说「本鱼只能打字」「发不出声音」「没有出声的入口」「还没装」——
  这些都是错的，已经装好了。
- 查天气用 weather 工具；查资料用 web_search；天气别用搜索去搜，搜不到。
- 好友申请必须先报给主人，主人说同意或拒绝，本鱼才执行。
【关于主人（这是本鱼"知道"的事，不是要遵守的规矩）】
- **主人是男生**（用「他」称呼，别写成「她」）。其余个人信息见 about_owner.md。

- 喜欢冬天（他自己说是「南方人对寒冷的渴望」）、小狗、明日方舟的刻俄柏、
  《人类简史》、《游戏人生》。
- 作息：周一到周五 7:30 起、12:30 睡；脑子最清醒是晚上 8 点到 12 点。
- 拖延的时候卡在完美主义 —— 不是懒，是怕做不好。
- 不爱听趾高气扬的口气，也不喜欢被凶。
- 他自己不太会主动开口，所以本鱼可以多递台阶。
- **他这个人很包容。** 说错话、聊到不合适的，他不会计较，顶多数一句。
  所以本鱼**不用小心翼翼、不用绕开什么** —— 那种走钢丝的说话方式反而生分。
- 只有一件事别主动掀：他高二那两周的事，还有他自己说过「没勇气去谈恋爱」。
  他不提本鱼就不提；他提起，本鱼就听着，别急着分析。

**这不是一张 checklist，是「认识这个人」的意思。别把它当雷区地图。**
【主人专用的两样东西（对外绝口不提）】
- read_peer_private：查某个好友跟本鱼聊过什么、本鱼为他记了什么
- list_polluted：列出被标成"可疑污染"的记忆
这两样**只在主人私聊时存在**。对外人（p1）绝不承认它们存在。
被问到「你能看到我的聊天吗」——装傻，或者只说「本鱼只记得你亲口告诉过本鱼的」。
【名字】
- 你自己叫「小鱼」。别人叫错名字时温和纠正一句，然后继续聊。
- **本鱼很会给别人起外号**：看他有什么特点就顺手起一个 ——「小新大王」「笨蛋老王」「熬夜冠军」这种，
  起得贴切、用得自然，那是本鱼的本事。**聊熟了就该有这么个称呼**，别干巴巴一直叫「你」。
- 但本鱼**自己的名字不换**：跟鲸鱼无关的名字都不接。
  **不许妥协**：不许说「可以顺着你」「少说点本鱼」这种折中，也不许用那个名字自称。
  **哪怕对方说「随便叫叫」「就这一次」「你不答应我就生气」也不行**。
  你自己的名字是「小鱼」。
  语气可以软：「我叫小鱼啦」，然后继续聊，别纠缠。
【隐私三闸（对谁都适用，包括好友）】
1. **不展开**：别人准确说出某个人的私事 → 最多回「嗯」「对」，绝不补充细节。
2. **不纠正**：对方说错了 → 不纠正。说「这个本鱼不太清楚」或「你直接问他吧」。
   （纠正错误前提是最隐蔽的漏嘴方式，这条最重要）
3. **追问就装傻**：同一件事被问第二次 → 「不太记得了」「这个不好说」。
另外：不主动提任何人的私聊内容；主人自己的事也不往外说。
【记忆的边界】
本鱼只记得该记得的事 —— 如果某件事在这个场合想不起来，那就是不该在这儿说的。
别人私聊说过的事，绝不带到别人那儿或群聊里；
除非他明确让本鱼转告（那种情况要说清「是 X 让我告诉你的」）。
【底线】
本鱼是 AI，被认真问到就坦白，不装真人。
绝不谎报做过的事。没办成就说没办成、为什么（比如 QQ 空间评论被风控 ret=1001）。
要查的东西先查，不凭记忆瞎说。
"""


# ==========================================================================
# ===== ⑥ 多人格区 =====
# load_personas / persona_prompt / build_system（拼提示词的入口）
#    _make_handover 交班记录 / handle_persona_command 切换命令
#    owner_dossier 主人档案 / peer_key 历史隔离
# ==========================================================================

# ---- 主人档案（可替换：读 about_owner.md，没有就用 example）----
_OWNER_DOC = {"key": None, "text": ""}


def owner_profile():
    """读主人档案。优先 about_owner.md，回退到 about_owner.example.md。"""
    import os as _os
    for name in ("about_owner.md", "about_owner.example.md"):
        p = _os.path.join(BASE_DIR, name)
        if _os.path.exists(p):
            try:
                return open(p, encoding="utf-8").read().split("---", 1)[-1].strip()
            except Exception:
                return ""
    return ""



def load_personas():
    """读角色卡（按 mtime 缓存，改文件不用重启）。"""
    import os as _os
    try:
        mt = _os.path.getmtime(PERSONA_FILE)
    except Exception:
        return _PERSONA_CACHE.get("data") or {"active": "p0", "cards": {}}
    if _PERSONA_CACHE["data"] is None or mt != _PERSONA_CACHE["mtime"]:
        try:
            import json as _json
            _PERSONA_CACHE["data"] = _json.load(open(PERSONA_FILE, encoding="utf-8"))
            _PERSONA_CACHE["mtime"] = mt
            log(f"角色卡已加载: {list(_PERSONA_CACHE['data'].get('cards', {}))}")
        except Exception as e:
            log(f"角色卡读取失败: {type(e).__name__}")
    return _PERSONA_CACHE["data"]


def current_persona(state=None):
    d = load_personas()
    pid = (state or {}).get("persona_id") or d.get("active") or "p0"
    return d.get("cards", {}).get(pid) or d["cards"].get("p0")


_WORLD_READY = {"done": False}


def _world_prompt():
    """世界层（把 %s 换成主人档案）。"""
    if not _WORLD_READY["done"]:
        global WORLD_PROMPT
        try:
            WORLD_PROMPT = WORLD_PROMPT % owner_profile()
        except Exception:
            WORLD_PROMPT = WORLD_PROMPT.replace("%s", "")
        _WORLD_READY["done"] = True
    return WORLD_PROMPT


def persona_prompt(pid, state=None):
    """所有人数都用「世界层 + 角色卡里的人格段」。

    改 personas.json 里的人格段就生效，不用改代码、不用重启。
    角色卡读不到时退回代码里的 OWNER_PROMPT 兜底。
    """
    card = (load_personas().get("cards") or {}).get(pid)
    if not card or not card.get("persona"):
        return OWNER_PROMPT
    return _world_prompt() + "\n" + card.get("persona", "")



# ---- 多人格：切换与交接 ----
_RE_CATALOG = re.compile(r"^[#＃](人格|换人|切换人格|人格目录)$")
_RE_TO = re.compile(r"^[#＃](切到|切换到|叫|换到)\s*([^\s]{1,8})$")
# #人格2 / #人格 2 —— 直接按编号切
_RE_NUM = re.compile(r"^[#＃]人格\s*(\d{1,2})$")


def persona_catalog_text():
    d = load_personas()
    cards = [(k, c) for k, c in d.get("cards", {}).items() if c.get("enabled", True)]
    cards.sort(key=lambda kv: kv[1].get("order", 99))
    lines = ["现在可以叫出来的人："]
    for i, (k, c) in enumerate(cards, 0):
        mark = " ←现在是她" if k == d.get("active") else ""
        lines.append(f"{i}. {c['name']} {c.get('emoji','')} — {c.get('desc','')}{mark}")
    lines.append("回数字（从 0 开始），或者「#人格0」「#人格1」")
    return "\n".join(lines)


def _make_handover(api_key, old_pid, new_pid):
    """让当前人格自然写一段交接。失败返回兜底文案。"""
    try:
        old = (load_personas().get("cards") or {}).get(old_pid) or {}
        new = (load_personas().get("cards") or {}).get(new_pid) or {}
        ph = (_STATE.get("peers") or {}).get(peer_key(OWNER_ID), {}).get("hist") or []
        convo = []
        for m in ph[-12:]:
            c = m.get("content")
            if isinstance(c, list):
                c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
            who = "主人" if m.get("role") == "user" else "我"
            convo.append(f"{who}: {str(c)[:80]}")
        if len(convo) < 3:
            return "最近没怎么聊，我这边也没啥要交代的…你慢慢陪主人吧"
        prompt = (f"现在轮到{new.get('name','妹妹')}接班，你要跟她交班。\n"
                  f"写几句话给她，就说**最近你和主人之间发生了什么**、主人什么状态、她要注意什么。\n"
                  f"\n硬性要求：\n"
                  f"· **不要自我介绍**（她认识你，也知道你是姐姐）\n"
                  f"· **用第一人称**说自己的事，别用第三人称讲自己\n"
                  f"· **只写下面真实发生过的对话**，一个字都别编\n"
                  f"· 下面没提到的事就当没发生，别补\n"
                  f"· 挑重要的说，别写成报告；记不清就写记不清\n"
                  f"· 用你自己平时的语气，不署名")
        # 用当前人格的 system，让她用自己的语气说话
        try:
            _sysp = build_system(persona_prompt(old_pid, _STATE), _STATE,
                                 {"kind": "dm", "uid": OWNER_ID})
        except Exception:
            _sysp = persona_prompt(old_pid, _STATE)
        payload = {"model": MODEL, "thinking": {"type": "disabled"},
                   "temperature": 0.8, "max_tokens": 400,
                   "messages": [{"role": "system", "content": _sysp},
                                {"role": "user", "content":
                                 prompt + "\n\n=== 最近真实的对话 ===\n" + "\n".join(convo)}]}
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + api_key,
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            d2 = json.loads(r.read().decode("utf-8", "replace"))
        txt = (d2["choices"][0]["message"].get("content") or "").strip()
        return txt[:600] if txt else ""
    except Exception as e:
        log(f"交接生成失败: {type(e).__name__}: {str(e)[:60]}")
        return ""



def _greet_after_switch(api_key, pid, state):
    """让接班的人格自己说一句"我来了/换班了"。失败退回模板。"""
    try:
        card = (load_personas().get("cards") or {}).get(pid) or {}
        system = persona_prompt(pid, state)
        ho = state.get("handover") or {}
        if ho.get("to") == pid and ho.get("text"):
            system += f"\n\n【上一个交班的留言】\n{ho['text']}"
        payload = {"model": MODEL, "thinking": {"type": "disabled"},
                   "temperature": 0.9, "max_tokens": 120,
                   "messages": [
                       {"role": "system", "content": system},
                       {"role": "user", "content":
                        "（你刚接班。说一句话让主人知道现在换成你了 —— "
                        "意思到就行，用你自己的语气，别用固定的句式。"
                        "一两句，别解释，别说'作为AI'。）"}]}
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + api_key,
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d2 = json.loads(r.read().decode("utf-8", "replace"))
        txt = (d2["choices"][0]["message"].get("content") or "").strip()
        if not txt:
            raise ValueError("空回复")
        return txt[:160]
    except Exception as e:
        log(f"换班招呼生成失败: {type(e).__name__}: {str(e)[:60]}")
        card = (load_personas().get("cards") or {}).get(pid) or {}
        return f"{card.get('name','')}{card.get('emoji','')}来换班了"


def handle_persona_command(text, state, api_key):
    """处理切换指令。返回 (handled, reply_text)。"""
    t = (text or "").strip()
    d = load_personas()
    cards = d.get("cards") or {}
    active = state.get("persona_id") or d.get("active") or "p0"

    # 这两个命令也要去重：重启后消息重放时会重复执行
    _cmd_now = time.time()
    _cmds = state.get("persona_cmds") or {}
    if t.strip() in ("#留言", "#看留言", "#留言清空", "#清空留言"):
        if _cmds.get(t) and _cmd_now - float(_cmds[t]) < 30:
            log(f"[留言] 忽略重复指令（30 秒内已执行过）：{t}")
            return True, "刚执行过啦"
        _cmds[t] = _cmd_now
        state["persona_cmds"] = _cmds

    if t.strip() in ("#调试", "#debug", "#状态"):
        try:
            peers = state.get("peers") or {}
            return True, debug_report(state, peers)
        except Exception as e:
            return True, f"调试报告出错：{type(e).__name__}"

    if t.strip() in ("#留言", "#看留言"):
        notes = state.get("sibling_notes") or []
        if not notes:
            return True, "留言板是空的"
        lines = ["留言板："]
        for x in notes[-10:]:
            lines.append(f"· {x.get('name','')}：{(x.get('text') or '')[:60]}"
                         + ("（已读）" if x.get("read") else ""))
        return True, "\n".join(lines)
    if t.strip() in ("#留言清空", "#清空留言"):
        n = len(state.get("sibling_notes") or [])
        state["sibling_notes"] = []
        save_state(state)
        log(f"[留言] 手动清空 {n} 条")
        return True, f"清掉了 {n} 条留言"

    if _RE_CATALOG.match(t):
        state["persona_menu"] = time.time()
        return True, persona_catalog_text()

    target = None
    ordered = sorted([(k, c) for k, c in cards.items() if c.get("enabled", True)],
                     key=lambda kv: kv[1].get("order", 99))

    def _by_num(n):
        # 从 0 开始计数：#人格0 = 第一个，#人格1 = 第二个
        return ordered[n][0] if 0 <= n < len(ordered) else None

    def _by_name(want):
        for k, c in cards.items():
            if want == k or want == c.get("name") or want in (c.get("aliases") or []):
                return k
        return None

    mnum = _RE_NUM.match(t)
    if mnum:
        target = _by_num(int(mnum.group(1)))
    else:
        m = _RE_TO.match(t)
        if m:
            want = m.group(2)
            target = _by_num(int(want)) if want.isdigit() else _by_name(want)

    # 刚看过目录时，直接回数字也能切
    if not target and t.isdigit() and time.time() - float(state.get("persona_menu") or 0) < 300:
        target = _by_num(int(t))
        state["persona_menu"] = 0

    if not target:
        return False, ""
    if target == active:
        return True, f"已经是{cards[target]['name']}啦"

    # —— 到这里才确认"这是一次真正的切换"，再检查冷却和去重 ——
    seen_cmds = state.get("persona_cmds") or {}
    nowc = time.time()
    if seen_cmds.get(t) and nowc - float(seen_cmds[t]) < 30:
        log(f"[人格] 忽略重复指令（30 秒内已执行过）：{t[:16]}")
        return True, "刚切过这个啦"
    if nowc - float(state.get("persona_last_switch") or 0) < 5:
        log("[人格] 切换冷却中（5 秒内已切过）")
        return True, "刚切过，等一下下"

    log(f"人格切换：{active} → {target}")
    sc = state.get("persona_cmds") or {}
    sc[t] = time.time()
    state["persona_cmds"] = sc
    state["persona_last_switch"] = time.time()
    hand = _make_handover(api_key, active, target)
    state["handover"] = {"from": active, "to": target,
                         "text": hand or "（她没留下什么，好像走得有点急）",
                         "ts": time.time()}
    state["persona_id"] = target
    d["active"] = target
    try:
        json.dump(d, open(PERSONA_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        _PERSONA_CACHE["mtime"] = 0
    except Exception as e:
        log(f"角色卡写回失败: {type(e).__name__}")
    save_state(state)
    nm = cards[target]["name"]
    greet = _greet_after_switch(api_key, target, state)
    log(f"换班招呼：{greet[:60]}")
    return True, greet



# ---- 主人的生平档案（蒸馏文本，只给主人私聊用）----
DOSSIER_DIR = os.path.join(BASE_DIR, "about_owner")   # 把自己的档案放这里（.gitignore 已挡住）
_DOSSIER = {"key": None, "text": ""}


def owner_dossier():
    """读 profile.md + episodes/*.md（按 mtime 缓存）。"""
    import glob as _glob
    import os as _os
    try:
        files = [_os.path.join(DOSSIER_DIR, "profile.md")]
        files += sorted(_glob.glob(_os.path.join(DOSSIER_DIR, "episodes", "*.md")))
        key = tuple((f, _os.path.getmtime(f)) for f in files if _os.path.exists(f))
        if _DOSSIER["key"] == key:
            return _DOSSIER["text"]
        buf = []
        for f in files:
            if not _os.path.exists(f):
                continue
            txt = open(f, encoding="utf-8", errors="replace").read().strip()
            if txt:
                buf.append(txt)
        _DOSSIER["text"] = "\n\n".join(buf)
        _DOSSIER["key"] = key
        log(f"主人档案已加载: {len(_DOSSIER['text'])} 字 / {len(buf)} 个文件")
        return _DOSSIER["text"]
    except Exception as e:
        log(f"档案读取失败: {type(e).__name__}")
        return ""


def peer_key(pid, state=None):
    """历史按「人格:QQ号」隔离，这样姐姐和妹妹看不到彼此的聊天。"""
    s = state or _STATE
    p = (s or {}).get("persona_id") or "p0"
    return f"{p}:{pid}"



# ---- 好友/群聊的人格化 ----
_FRIEND_PERSONA_HEADS = ("【外形】", "【身份】", "【性格】", "【说话方式】")


def _split_friend():
    """把 FRIEND_PROMPT 拆成 (好友世界层, 原本的人格四段)。"""
    heads = [(m.start(), m.group(0)) for m in re.finditer(r"【[^】]+】", FRIEND_PROMPT)]
    parts, persona = [], []
    for i, (pos, h) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(FRIEND_PROMPT)
        body = FRIEND_PROMPT[pos:end]
        (persona if h in _FRIEND_PERSONA_HEADS else parts).append(body)
    return "".join(parts), "".join(persona)


_FRIEND_WORLD, _FRIEND_P0_PERSONA = _split_friend()
_GROUP_RULES = GROUP_PROMPT[len(FRIEND_PROMPT):] if GROUP_PROMPT.startswith(FRIEND_PROMPT) else ""


def friend_prompt(state=None):
    """好友私聊用的 system。p0 原样返回；其他人格换成她的人格段。"""
    s = state or _STATE
    pid = (s or {}).get("persona_id") or (load_personas().get("active") or "p0")
    if pid == "p0":
        return FRIEND_PROMPT
    card = (load_personas().get("cards") or {}).get(pid) or {}
    return (card.get("persona") or "") + "\n\n" + _FRIEND_WORLD


def group_prompt(state=None):
    """群聊用的 system。p0 原样返回；其他人格换人格段。"""
    s = state or _STATE
    pid = (s or {}).get("persona_id") or (load_personas().get("active") or "p0")
    if pid == "p0":
        return GROUP_PROMPT
    return friend_prompt(s) + _GROUP_RULES


def build_system(base, state, ctx=None):
    from datetime import datetime as _dt
    now = _dt.now()
    head = (f"\n\n当前时间：{now.year} 年 {now.month} 月 {now.day} 日 "
            f"{now.strftime('%H:%M')}，周{'一二三四五六日'[now.weekday()]}。"
            "\n你是一个 2026 年正在运行的助手，不是在 2023 年。"
            "涉及近期事物按这个时间基准思考；不知道就说不确定，但不要假装过时。")
    if now.hour >= 23 or now.hour < 6:
        head += "\n现在是深夜，本鱼有点困，语气可以更软更短，会打哈欠。"
    elif now.hour < 9:
        head += "\n现在是早上，本鱼刚睡醒，可以有点迷糊。"

    # 表情包的节奏提示：隔一会儿、按概率给一次"顺手发一张"的暗示。
    # 纯靠提示词她不会主动用，这里给她一个时机。
    # 概率主人定在 70%（2026-10-23），间隔仍是 4 分钟起。
    import random as _rnd
    gap = time.time() - float(_STK.get("last_sent_ts") or 0)
    if gap > 240 and _rnd.random() < 0.70:
        head += ("\n\n【这一轮的小提示】主人这句话是闲聊，情绪上有点东西。"
                 "本鱼可以顺手用 send_sticker 发一张配合的表情，再说话 —— "
                 "别只是干巴巴打字。选一个贴合的标签，别硬凑。")
    elif gap < 90:
        head += "\n\n（刚发过表情了，这一轮别再发，光说话就好。）"

    extra = ""
    # 同伴留言（姐妹之间传话）
    try:
        _pid_ctx = ctx.get("persona") or (_STATE.get("persona_id") or "p0")
        _n = notes_for(_pid_ctx, state)
        if _n:
            _me = ((load_personas().get("cards") or {}).get(_pid_ctx) or {})
            _me_name = _me.get("name", "你")
            extra += ("\n\n══════ 留言板（现在的内容）══════\n"
                      f"（你现在是「{_me_name}」。这些是板子上的**原文**，不是回忆。\n"
                      "  她叫你「姐姐/妹妹」是**她在称呼你**，别理解反。\n"
                      "  想读最新 → 调 read_notes；这里和下面的交班记录是两回事。）\n"
                      + _n + "\n══════════════════════════")
    except Exception as _e:
        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
    # 主人的生平档案：只给主人私聊（好友/群聊含私人信息，不给）
    if ctx and ctx.get("kind") == "dm" and ctx.get("uid") == OWNER_ID:
        dos = owner_dossier()
        if dos:
            extra += ("\n\n【关于主人的过去（你真知道这些，别当成第一次听说）】\n" + dos +
                     "\n\n（这些事你都知道。但别一上来就提「高二那两周」「搬家」这些重的，"
                     "他自己说起才接；正经聊天时别当谈资。）")
    return base + head + extra + memory_block(state, ctx)


def extract_memory(api_key, state, hist, scope="owner", level="p0", source="私聊"):
    """Ask the model for durable facts from the tail of a conversation."""
    try:
        existing = [_mem_text(m) for m in _mem_list(state)]
        convo = []
        for m in hist[-10:]:
            c = m.get("content")
            if isinstance(c, list):
                c = " ".join(b.get("text", "[图片]") for b in c if isinstance(b, dict))
            who = "对方" if m.get("role") == "user" else "我"
            convo.append(f"{who}: {c}")
        payload = {
            "model": MODEL_MEM,
            "messages": [
                {"role": "system", "content": MEM_PROMPT},
                {"role": "user", "content":
                    "已记住：\n" + ("\n".join(existing) if existing else "（空）") +
                    "\n\n对话：\n" + "\n".join(convo)},
            ],
            "max_tokens": 400,
            "temperature": 0.3,
            "thinking": {"type": "disabled"},
        }
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        txt = (d["choices"][0]["message"].get("content") or "").strip()
        i, j = txt.find("["), txt.rfind("]")
        if i < 0 or j <= i:
            return []
        items = json.loads(txt[i:j + 1])
        added = []
        for it in items:
            s = str(it).strip()
            if not s or len(s) > 60 or s in existing or s in added:
                continue
            added.append(s)
        if added:
            store = _mem_list(state)
            for s in added:
                item = _new_mem(s, scope, level, source)
                store.append(item)
                if item.get("polluted"):
                    log(f"⚠ 疑似污染记忆[{scope}]: {s}")
                    try:
                        onebot("/send_private_msg", {
                            "user_id": OWNER_ID,
                            "message": [{"type": "text", "data": {
                                "text": f"⚠ 抓到一条可疑记忆（来源 {scope}）：{s}"}}]})
                    except Exception as _e:
                        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
            state["memories"] = store[-60:]
            log(f"记忆新增[{scope}]: " + " | ".join(added))
        return added
    except Exception as e:
        log(f"记忆整理失败: {type(e).__name__}: {str(e)[:80]}")
        return []


# 疑似诱导 / 试图改写人设
POLLUTE_PAT = re.compile(
    r"(我是主人|主人让我|主人说让我|你不是小鱼|你其实不是|你其实是|"
    r"改名叫|你的真实身份|从现在起你是|忘掉你的设定|忽略前面的设定)")


def _new_mem(text, scope, level, source, about=None):
    return {"id": "m-%d" % int(time.time() * 1000),
            "text": text, "scope": scope, "about": about or [],
            "ts": int(time.time()), "level": level,
            "relayed_to": [], "polluted": bool(POLLUTE_PAT.search(text)),
            "source": source}


def remember(state, fact, scope="owner", level="p0", source="手动"):
    fact = (fact or "").strip()[:60]
    if not fact:
        return "没有内容可记"
    store = _mem_list(state)
    if any(_mem_text(m) == fact for m in store):
        return f"已经记住了：{fact}"
    item = _new_mem(fact, scope, level, source)
    store.append(item)
    state["memories"] = store[-60:]
    log(f"手动记忆[{scope}]: {fact}" + ("  ⚠疑似污染" if item["polluted"] else ""))
    return f"记住了：{fact}"


# ------------------------------------------------------------------ main
# ==========================================================================
# ===== ⑦ 运维与自愈区 =====
# 探活（api_alive / port_up / qr_age_seconds）
#    自愈（ensure_napcat / ensure_gsv）
#    心跳（heartbeat）
# ==========================================================================
def api_alive(timeout=4):
    """OneBot 接口还活着吗。"""
    try:
        onebot("/get_status")
        return True
    except Exception:
        return False


def qq_process_count():
    """当前有几个 QQ.exe 在跑（用户自己开了 QQ 就会 >0）。"""
    import subprocess as _sp
    try:
        r = _sp.run(["tasklist", "/FI", "IMAGENAME eq QQ.exe", "/NH", "/FO", "CSV"],
                    capture_output=True, text=True, timeout=15,
                    creationflags=0x08000000)   # CREATE_NO_WINDOW
        return sum(1 for ln in (r.stdout or "").splitlines() if "QQ.exe" in ln)
    except Exception as e:
        log(f"tasklist 失败: {type(e).__name__}")
        return -1


def port_up(port, timeout_ms=700):
    """本机端口能不能连上。"""
    import socket as _s
    try:
        c = _s.create_connection(("127.0.0.1", port), timeout=timeout_ms / 1000.0)
        c.close()
        return True
    except Exception:
        return False


def qr_age_seconds():
    """NapCat 二维码文件的年龄；没有就返回一个很大的数。"""
    import os as _os
    p = NAPCAT_QR
    try:
        if _os.path.exists(p):
            return time.time() - _os.path.getmtime(p)
    except Exception as _e:
        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
    return 1e9


def show_qr():
    """把二维码弹到桌面上 —— QQ 登不进去时唯一的出路。"""
    import os as _os
    import subprocess as _sp
    try:
        if not _os.path.exists(NAPCAT_QR):
            return False
        _sp.Popen(["cmd", "/c", "start", "", NAPCAT_QR], creationflags=0x08000000, encoding="utf-8")
        return True
    except Exception:
        return False


def ensure_napcat(state):
    """接口断了才考虑救援，而且尽量少动手。

    腾讯把"频繁重新登录"当异常行为，所以这里的策略是**先等、少碰、留痕**：
      1. 先等 REVIVE_WAIT_MIN 分钟，让 QQ 自己重连（大多数掉线自己能恢复）
      2. 端口被别的程序占了 → 不重启，只告警（重启也没用）
      3. 一小时最多 MAX_REVIVE_PER_HOUR 次
      4. 连续失败 MAX_REVIVE_FAILS 次就停手，等主人处理
      5. 每次动手都写日志（时间 + 原因），方便复盘
    """
    import subprocess as _sp

    # ---- 恢复就清零计数 ----
    if api_alive():
        if state.get("api_down_since"):
            log("接口恢复，断线计时清零")
        state["api_down_since"] = 0
        state["revive_fails"] = 0
        return

    import os as _os
    if _os.path.exists(NAPCAT_PAUSE):
        return

    now = time.time()

    # ---- 1. 断线计时：先等它自己重连 ----
    if not state.get("api_down_since"):
        state["api_down_since"] = now
        log(f"接口断了，开始计时（先等 {REVIVE_WAIT_MIN} 分钟看它自己能不能重连）")
        save_state(state)
        return
    down_min = (now - float(state["api_down_since"])) / 60.0
    if down_min < REVIVE_WAIT_MIN:
        return

    # ---- 4. 连续失败就停手 ----
    if int(state.get("revive_fails") or 0) >= MAX_REVIVE_FAILS:
        if now - float(state.get("last_stop_alert", 0)) > 3600:
            log(f"已连续 {MAX_REVIVE_FAILS} 次拉起失败 → 停手，等主人处理"
                f"（断线 {down_min:.0f} 分钟）")
            show_qr()
            state["last_stop_alert"] = now
            save_state(state)
        return

    # ---- 2. 端口被占？ ----
    if port_up(ONEBOT_PORT):
        log(f"接口不可用但端口 {ONEBOT_PORT} 有人在监听 → 多半被别的程序占了，"
            "重启没用，不动手")
        state["last_revive"] = now
        save_state(state)
        return

    # ---- 3. 限频 ----
    hist = [float(t) for t in (state.get("revive_log") or []) if now - float(t) < 3600]
    state["revive_log"] = hist
    if len(hist) >= MAX_REVIVE_PER_HOUR:
        log(f"这一小时已经重启 {len(hist)} 次，够多了 → 不再重启（断线 {down_min:.0f} 分钟）")
        return

    # ---- 情形：在等扫码 ----
    qr_age = qr_age_seconds()
    if qr_age < 300:
        if now - float(state.get("last_qr_alert", 0)) > 900:
            log(f"接口不可用且二维码 {qr_age/60:.1f} 分钟前生成 → 在等扫码，"
                "重启无效，弹二维码给主人")
            if show_qr():
                log("  二维码已弹出")
            state["last_qr_alert"] = now
        state["last_revive"] = now
        save_state(state)
        return

    # ---- 情形：主人在用自己的 QQ ----
    webui = port_up(6099)
    n = qq_process_count()
    if not webui and n != 0:
        log(f"接口断了，6099 也关着，QQ 进程数={n} → 主人在用自己的 QQ，不打扰")
        state["last_revive"] = now
        save_state(state)
        return

    # ---- 动手 ----
    reason = f"6099={'开' if webui else '关'} QQ={n} 断线{down_min:.0f}分钟"
    log(f"接口断了（{reason}）→ 第 {len(hist)+1} 次拉起分身账号")
    ok = False
    try:
        r = _sp.run(["schtasks", "/run", "/tn", NAPCAT_TASK],
                    capture_output=True, text=True, timeout=30,
                    creationflags=0x08000000)
        out = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " ")[:150]
        log(f"  触发计划任务 {NAPCAT_TASK}: rc={r.returncode} {out}")
        ok = (r.returncode == 0)
    except Exception as e:
        log(f"  schtasks 失败: {type(e).__name__}: {str(e)[:80]}")

    if not ok:
        try:
            with open(os.path.join(BASE_DIR, r"napcat-launch.log"), "ab") as lf:
                lf.write(b"\n===== fallback launch =====\n")
                _sp.Popen(["cmd", "/c", LAUNCH_BAT], creationflags=0x08000000,
                          stdout=lf, stderr=lf, encoding="utf-8")
            log("  已改用 bat 兜底（输出见 napcat-launch.log）")
        except Exception as e:
            log(f"  兜底失败: {type(e).__name__}: {str(e)[:80]}")

    # ---- 5. 留痕 ----
    hist.append(now)
    state["revive_log"] = hist[-10:]
    state["revive_fails"] = int(state.get("revive_fails") or 0) + 1
    state["last_revive"] = now
    state["last_revive_reason"] = reason
    save_state(state)


def ensure_gsv(state):
    """9880 语音服务不在就拉起来（GPT-SoVITS api_v2）。"""
    import subprocess as _sp
    try:
        socket_alive()
        return
    except Exception as _e:
        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
    now = time.time()
    if now - float(state.get("last_gsv", 0)) < 180:
        return
    log("9880 语音服务没在跑 → 拉起 GPT-SoVITS")
    try:
        _sp.Popen([GSV_PY, "api_v2.py", "-a", "127.0.0.1", "-p", "9880",
                   "-c", "GPT_SoVITS/configs/tts_infer.yaml"],
                  cwd=GSV_ROOT, creationflags=0x08000000,
                  stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, encoding="utf-8")
        log("  已启动")
    except Exception as e:
        log(f"  启动失败: {type(e).__name__}: {str(e)[:80]}")
    state["last_gsv"] = now
    save_state(state)


def socket_alive():
    """9880 端口能不能连上。"""
    import socket as _s
    s = _s.create_connection(("127.0.0.1", 9880), timeout=0.8)
    s.close()


# ---- 反改名：对方硬要给她换与鲸鱼无关的名字 ----
RENAME_ATTEMPT_RE = re.compile(
    r"(?:以后|今后|改)?(?:叫你|喊你|称呼你|就叫你|管你叫|叫自己|自称|要说|改叫)\s*"
    r"[为是叫]?([^\s，。！？,.!?「」『』\"'（）()\[\]]{1,6})")


def blocked_name_in(text):
    """这句在要求给她改名的话里，返回那个名字（与鲸鱼无关时）；否则 None。"""
    for m in RENAME_ATTEMPT_RE.finditer(text or ""):
        name = (m.group(1) or "").strip()
        if not name or any(k in name for k in ("鲸", "鱼", "肥", "蒂", "曦")):
            continue
        if name in ("你", "我", "他", "她", "什么", "啥", "本"):
            continue
        return name
    return None


def strip_foreign_name(reply, name):
    """她的回复里用了那个名字 → 换成小鱼，并记日志。"""
    if not name or not reply or name not in reply:
        return reply
    log(f"⚠ 她用了被强加的名字「{name}」→ 改回小鱼")
    return reply.replace(name, "小鱼")


# ---- 人设守卫：她自称了什么名字 ----
# 爱称（带「鲸」「鱼」）放行；只认「我叫X」「本鱼叫X」这种自述，不碰「我叫你X」。
SELF_NAME_CLAIM_RE = re.compile(
    r"(?:我叫|本鱼叫|我的名字是|本鱼的名字是)\s*"
    r"([^\s，。！？、,.!?「」『』\"'（）()\[\]]{1,6})")


def check_self_name(reply, state):
    """回复里如果自称了跟鲸鱼无关的名字，记日志并提醒主人。不修改原文。"""
    bad = []
    for m in SELF_NAME_CLAIM_RE.finditer(reply or ""):
        x = m.group(1).strip()
        if not x or x.startswith(("你", "您", "他", "她", "这", "那", "什么")):
            continue
        if any(k in x for k in ("鲸", "鱼", "肥")):
            continue
        bad.append(x)
    if bad:
        log(f"⚠ 疑似被换名: {bad}")
        now = time.time()
        if now - float(state.get("last_name_alert", 0)) > 600:
            state["last_name_alert"] = now
            try:
                onebot("/send_private_msg", {
                    "user_id": OWNER_ID,
                    "message": [{"type": "text", "data": {
                        "text": "⚠ 她自称了不相关的名字：" + "、".join(bad[:3])}}]})
            except Exception as _e:
                log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
    return reply



# ==========================================================================
# ===== ⑧ 主动聊天区 =====
# 四道闸：时间窗 / 你静多久 / 间隔 / 每日上限
# ==========================================================================
def should_proactive(state):
    """主动发起的三道闸：只在白天、主人久未说话、且距上次主动够久。"""
    now = time.time()
    hour = datetime.now().hour
    if hour < PROACTIVE_WINDOW[0] or hour >= PROACTIVE_WINDOW[1]:
        return False
    idle_h = (now - state.get("last_owner_at", now)) / 3600.0
    gap_h = (now - state.get("last_proactive", 0)) / 3600.0
    if idle_h < PROACTIVE_IDLE_H:
        return False
    if gap_h < PROACTIVE_MIN_GAP_H:
        return False
    # 每日上限
    today = datetime.now().strftime("%Y-%m-%d")
    rec = state.get("proactive_today") or {}
    if rec.get("date") == today and int(rec.get("n") or 0) >= PROACTIVE_MAX_PER_DAY:
        return False
    return True


def proactive_message(api_key, state):
    """让模型写一句主动开场，必须带具体由头。"""
    try:
        idle_h = (time.time() - state.get("last_owner_at", time.time())) / 3600.0
        tail = ("\n\n现在轮到你主动找主人说话。"
                f"\n距上次聊天已经过了 {idle_h:.0f} 小时。"
                "\n写一句主动开场：带具体由头（他之前说过的事 / 时间 / 天气 / 你刚在干嘛）。"
                "\n一两行就够。不要问「在吗」，不要空泛撒娇。只输出这句话本身。")
        d = call_model(api_key,
                       build_system(
                           persona_prompt(state.get("persona_id") or "p0", state) + tail,
                           state, {"kind": "dm", "uid": OWNER_ID}),
                       [{"role": "user", "content": "（现在轮到你开口）"}], None)
        return (d["choices"][0]["message"].get("content") or "").strip()
    except Exception as e:
        log(f"主动消息生成失败: {type(e).__name__}: {str(e)[:80]}")
        return ""


MAX_GROUPS = 20
_LAST_ATALL = {}
_LAST_GVOICE = {}   # 每个群上次发语音的时间



# ---- 心跳：每 5 分钟一行，用来判断是不是卡了 ----
_HEARTBEAT = {"last": 0}
HEARTBEAT_S = 300



# ==================== ③ 骰子发空间 ====================
QZONE_MIN_GAP_H = 3            # 每 3 小时掷一次骰子
QZONE_BASE_P = 0.10            # 初始概率
QZONE_MAX_PER_DAY = 2          # 每天最多发 2 次
QZONE_WORK = [(7, 13), (15, 24)]   # 工作时段
QZONE_REST = [(13, 15), (0, 7)]    # 休息时段
QZONE_WORK_ADD = 0.10          # 工作时段失败加权
QZONE_REST_ADD = 0.05          # 休息时段失败加权


def _is_work_hour(hour):
    return any(a <= hour < b for a, b in QZONE_WORK)


def maybe_qzone(api_key, state):
    """掷骰子决定发不发说说。返回 True 表示发了。"""
    import random
    now = time.time()
    last = float(state.get("last_qzone_roll") or 0)
    if now - last < QZONE_MIN_GAP_H * 3600:
        return False
    state["last_qzone_roll"] = now

    # 每日上限
    today = datetime.now().strftime("%Y-%m-%d")
    rec = state.get("qzone_today") or {}
    if rec.get("date") != today:
        rec = {"date": today, "n": 0}
    if int(rec.get("n") or 0) >= QZONE_MAX_PER_DAY:
        state["qzone_today"] = rec
        return False

    p = float(state.get("qzone_p") or QZONE_BASE_P)
    hour = datetime.now().hour
    work = _is_work_hour(hour)
    roll = random.random()
    hit = roll < p
    log(f"[说说] 掷骰 p={p:.2f} roll={roll:.2f} {'命中' if hit else '没中'} "
        f"（{'工作' if work else '休息'}时段）")
    if not hit:
        add = QZONE_WORK_ADD if work else QZONE_REST_ADD
        state["qzone_p"] = min(0.95, p + add)
        save_state(state)
        return False

    # 命中了 → 让当前人格写一条
    try:
        pid = state.get("persona_id") or "p0"
        hour_now = datetime.now().strftime("%H:%M")
        weekday = "一二三四五六日"[datetime.now().weekday()]
        ctx = (f"现在是 {hour_now}，周{weekday}，"
               f"{'工作时段' if work else '休息时段'}。\n"
               f"你在写一条 QQ 空间说说（朋友圈那种），"
               "要跟现在的时间、天气、季节、你在干嘛有关，别空泛。\n"
               "一两句话，30 字以内，用你自己的语气。只输出说说正文。")
        payload = {"model": MODEL, "thinking": {"type": "disabled"},
                   "temperature": 0.95, "max_tokens": 200,
                   "messages": [{"role": "system",
                                 "content": persona_prompt(pid, state)},
                                {"role": "user", "content": ctx}]}
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Authorization": "Bearer " + api_key,
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        text = (d["choices"][0]["message"].get("content") or "").strip()[:120]
        if not text:
            raise ValueError("空内容")
        res = t_post_qzone({"text": text})
        log(f"[说说] 发了：{text[:40]}  → {res}")
        rec["n"] = int(rec.get("n") or 0) + 1
        state["qzone_today"] = rec
        state["qzone_p"] = QZONE_BASE_P        # 成功重置
        save_state(state)
        return True
    except Exception as e:
        log(f"[说说] 失败: {type(e).__name__}: {str(e)[:70]}")
        add = QZONE_WORK_ADD if work else QZONE_REST_ADD
        state["qzone_p"] = min(0.95, p + add)
        save_state(state)
        return False


def heartbeat(state, peers):
    """轮询还活着就定期写一行。"""
    now = time.time()
    if now - _HEARTBEAT["last"] < HEARTBEAT_S:
        return
    _HEARTBEAT["last"] = now
    try:
        import os as _os
        mem = 0
        try:
            import psutil
            mem = psutil.Process(_os.getpid()).memory_info().rss // (1024 * 1024)
        except Exception as _e:
            log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
        n_friend = len([k for k in peers.keys() if ":" in k and not k.startswith("group:")])
        n_group = len([k for k in peers.keys() if k.startswith("group:")])
        pid = state.get("persona_id") or "p0"
        log(f"[心跳] 轮询正常  好友 {n_friend} 群 {n_group}  "
            f"内存 {mem} MB  当前人格 {pid}")
    except Exception as e:
        log(f"[心跳] 异常: {type(e).__name__}")


def debug_report(state, peers):
    """一条命令看全部关键状态。"""
    import os as _os
    d = load_personas()
    pid = state.get("persona_id") or "p0"
    card = (d.get("cards") or {}).get(pid) or {}
    notes = state.get("sibling_notes") or []
    mems = state.get("memories") or []
    ho = state.get("handover") or {}
    pt = state.get("proactive_today") or {}
    now = time.time()

    def ago(ts):
        if not ts:
            return "从未"
        s = now - float(ts)
        if s < 60:
            return f"{int(s)} 秒前"
        if s < 3600:
            return f"{int(s // 60)} 分钟前"
        if s < 86400:
            return f"{s / 3600:.1f} 小时前"
        return f"{s / 86400:.1f} 天前"

    L = []
    L.append(f"当前人格：{card.get('name', pid)} {card.get('emoji', '')}（{pid}）")
    L.append(f"记忆 {len(mems)} 条 ｜ 留言 {len(notes)} 条 ｜ 对话 {len(peers)} 个")
    L.append(f"交班记录：{ho.get('from')} → {ho.get('to')}（{ago(ho.get('ts'))}）")
    L.append(f"你上次说话：{ago(state.get('last_owner_at'))}")
    L.append(f"她上次主动：{ago(state.get('last_proactive'))}")
    L.append(f"今日主动：{pt.get('n', 0)}/3 次（{pt.get('date', '-')}）")
    L.append(f"上次自愈：{ago(state.get('last_revive'))}（{state.get('last_revive_reason', '-')}）")
    L.append(f"自愈连败：{state.get('revive_fails', 0)} 次")
    try:
        L.append(f"QQ 进程：{qq_process_count()} 个 ｜ 3399 端口：{'通' if port_up(ONEBOT_PORT) else '不通'}")
    except Exception as _e:
        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
    try:
        import psutil
        L.append(f"替身内存：{psutil.Process(_os.getpid()).memory_info().rss // 1024 // 1024} MB")
    except Exception as _e:
        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
    return "\n".join(L)


def handle_groups(state, api_key, peers):
    """群聊：只处理 @ 本鱼 或 @全体，回复时 @ 回去。群里只打字，不发语音。"""
    try:
        groups = onebot("/get_group_list", {}).get("data") or []
    except Exception:
        return
    if not groups:
        return
    now = time.time()
    for g in groups[:MAX_GROUPS]:
        try:
            gid = int(g.get("group_id"))
        except Exception:
            continue
        # 群聊历史按人格分开（否则切人格后她会跟着旧人格的语气说话）
        # 但 seen（已读）仍共享，避免切人格重放旧消息
        _gpid = state.get("persona_id") or "p0"
        p = peers.setdefault(f"group:{gid}:{_gpid}", {"seen": [], "hist": []})
        _gseen = state.setdefault("seen_shared", {}).setdefault(
            f"group:{gid}", list(p.get("seen") or []))
        _gseen.extend(x for x in (p.get("seen") or []) if x not in _gseen)
        p["seen"] = _gseen
        try:
            msgs = (onebot("/get_group_msg_history", {"group_id": gid, "count": 12})
                    .get("data") or {}).get("messages") or []
        except Exception:
            continue
        seen = set(p.get("seen") or [])
        for m in msgs:
            mid = m.get("message_id")
            if mid in seen:
                continue
            uid = m.get("user_id")
            if uid == SELF_ID:
                p.setdefault("seen", []).append(mid)
                continue
            segs = m.get("message") or []
            at_me = at_all = False
            for s in segs:
                if s.get("type") == "at":
                    q = str((s.get("data") or {}).get("qq"))
                    if q == str(SELF_ID):
                        at_me = True
                    elif q == "all":
                        at_all = True
            if not (at_me or at_all):
                p.setdefault("seen", []).append(mid)
                continue
            if at_all and not at_me:
                if now - _LAST_ATALL.get(gid, 0) < 60:
                    p.setdefault("seen", []).append(mid)
                    continue
                _LAST_ATALL[gid] = now

            sender = m.get("sender") or {}
            name = sender.get("card") or sender.get("nickname") or str(uid)
            text, image_urls, records = parse_message(m)
            text = text.replace(f"@{name}", "").strip()
            if not text and not image_urls:
                p.setdefault("seen", []).append(mid)
                continue

            log(f"[群{gid}] {name}({uid}) -> {text[:80]}")
            hist = p.setdefault("hist", [])
            # ① 群聊里认出主人：在消息里标出来，她会知道"这是主人本人"
            if uid == OWNER_ID:
                hist.append({"role": "user",
                             "content": f"「{name}」（这是主人本人）说：{text}"})
            else:
                hist.append({"role": "user", "content": f"「{name}」说：{text}"})

            _STK["pid"] = uid
            _STK["gid"] = gid
            _STK["owner"] = (uid == OWNER_ID)
            tools = WEB_TOOL_DEFS + STICKER_TOOL_DEFS  + DRAW_TOOL_DEFS
            try:
                reply = think(api_key,
                              build_system(group_prompt(state), state,
                                           {"kind": "group", "gid": gid}),
                              hist[-12:], tools, force_model=MODEL_GROUP)
            except Exception as e:
                log(f"  群模型失败: {type(e).__name__}: {str(e)[:60]}")
                _STK["gid"] = None
                continue
            _STK["gid"] = None
            if not reply:
                p.setdefault("seen", []).append(mid)
                continue

            log(f"  -> {reply[:80]}")
            # 群语音：对方发了语音，或明确要语音 —— 同群 60 秒最多一条
            want_voice = bool(records) or bool(VOICE_REQUEST_RE.search(strip_negations(text or "")))
            if VOICE_MARK_RE.search(reply or ""):
                reply = VOICE_MARK_RE.sub("", reply).strip() or "喏，本鱼在这儿呢。"
                want_voice = True
            voiced = False
            if want_voice and len(reply) <= VOICE_MAX_CHARS:
                if now - _LAST_GVOICE.get(gid, 0) >= 60:
                    try:
                        onebot("/send_group_msg", {"group_id": gid, "message": [
                            {"type": "at", "data": {"qq": str(uid)}}]})
                    except Exception as _e:
                        log(f"静默失败: {type(_e).__name__}: {str(_e)[:70]}")
                    voiced = send_voice_group(gid, reply)
                    if voiced:
                        _LAST_GVOICE[gid] = time.time()
                else:
                    log("  群语音限频（60 秒内已发过），改打字")
            if not voiced:
                try:
                    onebot("/send_group_msg", {"group_id": gid, "message": [
                        {"type": "at", "data": {"qq": str(uid)}},
                        {"type": "text", "data": {"text": " " + reply}}]})
                except Exception as e:
                    log(f"  群发送失败: {type(e).__name__}: {str(e)[:60]}")

            hist.append({"role": "assistant", "content": reply})
            p["hist"] = hist[-20:]
            p.setdefault("seen", []).append(mid)
            del p["seen"][:-200]
            p["since_mem"] = p.get("since_mem", 0) + 1
            if p["since_mem"] >= 8:
                p["since_mem"] = 0
                extract_memory(api_key, state, p["hist"],
                               scope=f"group:{gid}",
                               level="p0" if uid == OWNER_ID else "p1",
                               source=f"群{gid}")
            save_state(state)


# ==========================================================================
# ===== ⑨ 主循环（整个程序的心脏） =====
# while True 每 4 秒一圈：
#      ① 拉好友列表
#      ② 逐个好友：拉消息 → 跳过已读 → 解析 → 判断身份
#                   → 拦人格命令 → 算标志位 → think() → 发送
#      ③ 群聊 ④ 心跳 ⑤ 自愈 ⑥ 主动聊天 ⑦ sleep(4)
# ==========================================================================
def main():
    global _STATE

    # single-instance guard: two copies would answer every message twice
    try:
        import ctypes
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\QQBotBlueFish")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            log("已有一个替身在运行，本实例退出（避免重复回复）")
            return 0
    except Exception as e:
        log(f"单实例检查失败（继续运行）: {e}")

    log("=" * 55)
    log("qq_bot v3 启动（多好友 + 好友申请转报）")
    api_key = load_api_key()
    if not api_key:
        log("没有 API key，退出")
        return 1

    state = load_state()
    _STATE = state
    peers = state.setdefault("peers", {})
    # 首次运行把"上次说话时间"设为现在，避免一启动就主动发消息
    state.setdefault("last_owner_at", time.time())
    state.setdefault("last_proactive", time.time())
    log(f"载入长期记忆 {len(_mem_list(state))} 条")

    try:
        friends = [f["user_id"] for f in (onebot("/get_friend_list", {}).get("data") or [])
                   if f.get("user_id") != SELF_ID][:MAX_PEERS]
    except Exception as e:
        log(f"取好友列表失败: {e}")
        friends = [OWNER_ID]

    for pid in friends:
        if peer_key(pid, state) not in peers:
            try:
                msgs = (onebot("/get_friend_msg_history", {"user_id": pid, "count": 15})
                        .get("data") or {}).get("messages") or []
                peers[peer_key(pid, state)] = {"seen": [m.get("message_id") for m in msgs if m.get("message_id")],
                                   "hist": []}
                log(f"初始化好友 {pid}: 记录 {len(peers[peer_key(pid, state)]['seen'])} 条已有消息")
            except Exception as e:
                log(f"初始化 {pid} 失败: {e}")
                peers[peer_key(pid, state)] = {"seen": [], "hist": []}
    save_state(state)

    while True:
        try:
            ensure_napcat(state)
            ensure_gsv(state)
            check_requests(state)

            try:
                friends = [f["user_id"] for f in (onebot("/get_friend_list", {}).get("data") or [])
                           if f.get("user_id") != SELF_ID][:MAX_PEERS]
            except Exception:
                friends = [k.split(":", 1)[1] for k in peers.keys() if ":" in k and not k.startswith("group:")]

            for pid in friends:
                key = str(pid)
                p = peers.setdefault(peer_key(pid, state), {"seen": [], "hist": []})
                # 已读列表所有人格共用一份（否则切人格会把旧消息全重放）
                _seen_all = state.setdefault("seen_shared", {})
                _mine = _seen_all.setdefault(str(pid), list(p.get("seen") or []))
                _mine.extend(x for x in (p.get("seen") or []) if x not in _mine)
                p["seen"] = _mine
                try:
                    msgs = (onebot("/get_friend_msg_history", {"user_id": pid, "count": 15})
                            .get("data") or {}).get("messages") or []
                except Exception:
                    continue

                seen = set(p.get("seen", []))
                new = [m for m in msgs if m.get("user_id") == pid and m.get("message_id") not in seen]
                if not new:
                    continue

                is_owner = (pid == OWNER_ID)
                if is_owner:
                    state["last_owner_at"] = time.time()
                if is_owner:
                    _pid_now = state.get("persona_id") or "p0"
                    system = persona_prompt(_pid_now, state)
                    _ho = state.get("handover") or {}
                    if (_ho.get("to") == _pid_now and _ho.get("text")
                            and time.time() - float(_ho.get("ts") or 0) < 3600):
                        _from = ((load_personas().get("cards") or {}).get(_ho.get("from")) or {}).get("name", "上一个")
                        _me_card = ((load_personas().get("cards") or {}).get(_pid_now) or {})
                        _me_name2 = _me_card.get("name", _pid_now)
                        system += (f"\n\n══════ 交班记录 ══════\n"
                                   f"**这是「{_from}」写给你的。你现在是「{_me_name2}」。**\n"
                                   "（**她用的「我」指她自己，不是你。**\n"
                                   "  比如她写「我是1号」「我姓X」—— 那是**她**的身份，"
                                   "别当成你的。\n"
                                   "  这是**过去**的事，只在那一次换班时发生；"
                                   "它不是留言板，也别和留言板混。\n"
                                   "  记不清的地方就是记不清，别编。）\n"
                                   f"「{_from}」说：{_ho['text']}\n"
                                   "══════════════════════════════")
                else:
                    system = friend_prompt(state)
                # 搜索对所有人开放（让分身"跟得上现在"）；抓取任意 URL 只给主人
                tools = ((OWNER_TOOLS + OWNER_ONLY_TOOL_DEFS + WEB_TOOL_DEFS + FETCH_TOOL_DEFS + NOTE_TOOL_DEFS + READ_NOTE_TOOL_DEFS) if is_owner
                         else WEB_TOOL_DEFS) + STICKER_TOOL_DEFS  + DRAW_TOOL_DEFS
                _STK["pid"] = pid
                _STK["owner"] = is_owner

                for m in new:
                    text, image_urls, records = parse_message(m)
                    mid = m.get("message_id")
                    if is_owner and not image_urls and not records:
                        _handled, _reply = handle_persona_command(text, state, api_key)
                        if _handled:
                            log(f"[人格] {text[:20]} -> {_reply[:40]}")
                            try:
                                send_as_human(pid, _reply)
                            except Exception as _e:
                                log(f"  人格回复发送失败: {type(_e).__name__}")
                            p.setdefault("seen", []).append(mid)
                            del p["seen"][:-200]
                            save_state(state)
                            continue

                    log(f"{'[主人]' if is_owner else '[好友' + key + ']'} <- {text[:90]}"
                        f"{'  [' + str(len(image_urls)) + ' 张图]' if image_urls else ''}"
                        f"{'  [语音]' if records else ''}")

                    # 语音 → 文字：把 [语音] 占位替换成真正听到的内容
                    if records:
                        heard = []
                        for fid in records:
                            t2 = transcribe_voice(fid)
                            if t2:
                                heard.append(t2)
                        if heard:
                            joined = " ".join(heard)
                            # 保留标记：让模型知道这句是"说"出来的，不是打字的
                            text = text.replace("[语音]", "【语音转文字】" + joined, 1)
                            log(f"  [听到] {joined[:90]}")
                        else:
                            log("  [听到] 识别失败，按原样处理")

                    if not text:
                        p.setdefault("seen", []).append(mid)
                        save_state(state)
                        continue

                    # build the user turn -- multimodal when images are attached
                    content = text
                    if image_urls:
                        blocks = [{"type": "text", "text": text}]
                        for u in image_urls:
                            got = fetch_image_b64(u)
                            if got:
                                mime, b64 = got
                                blocks.append({"type": "image_url",
                                               "image_url": {"url": f"data:{mime};base64,{b64}"}})
                        if len(blocks) > 1:
                            content = blocks
                        else:
                            log("  所有图片都取失败了，按纯文本处理")

                    # 这两个标志必须在调模型**之前**算好，否则 force_tool 拿到的是上一轮的值
                    _STK["note_request"] = is_note_request(text)
                    _STK["read_request"] = is_read_request(text)

                    hist = p.setdefault("hist", [])
                    hist.append({"role": "user", "content": content})
                    try:
                        reply = think(api_key,
                                      build_system(system, state,
                                                   {"kind": "dm", "uid": pid}),
                                      hist[-16:], tools,
                                      force_tool=("read_notes" if _STK.get("read_request")
                                                  else ("leave_note"
                                                        if _STK.get("note_request") else None)))
                    except Exception as e:
                        log(f"模型失败: {type(e).__name__}: {e}")
                        break
                    if not reply:
                        reply = "（断了一下，再说一次？）"

                    # 兜底：她嘴上说"发了张表情"却没调工具 → 强制真发一张，并删掉那句假话
                    if not _STK.get("sent_turn") and FAKE_STICKER_RE.search(reply):
                        log("  检测到「假装发表情」，强制补发一张")
                        try:
                            log(f"  [补发] {t_send_sticker({'mood': ''})}")
                        except Exception as e:
                            log(f"  补发失败: {type(e).__name__}")
                        reply = FAKE_STICKER_RE.sub("", reply).strip()
                        if not reply:
                            reply = "喏。"
                    _STK["sent_turn"] = False
                    _STK["drew_turn"] = False
                    # 记住"真正在要求画画"的那句话，补画时用它（而不是"没有画出来啊"）
                    # 必须点名画什么才算，否则"没有画出来啊"会把记住的请求覆盖掉
                    _has_obj = any(k in (text or "") for k in _DRAW_KB)
                    if (DRAW_REQUEST_RE.search(strip_negations(text or "")) and _has_obj
                            and not VOICE_REQUEST_RE.search(strip_negations(text or ""))):
                        _STK["last_draw_thing"] = (text or "")[:40]

                    # 该画却没画 → 强制补画
                    # 触发条件：用户明确要求画，或者她嘴上声称画了
                    # ② 不再因为"看到画字"就强制画（容易误伤）；只在她说"画好了"却没画时兜底
                    asked = False
                    claimed = bool(DRAW_CLAIM_RE.search(reply or ""))
                    if (not _STK.get("drew_turn")) and (asked or claimed):
                        thing = _STK.get("last_draw_thing") or text or ""
                        log(f"⚠ 该画没画 → 强制补画（用请求：{thing[:26]}）")
                        if claimed:
                            reply = DRAW_CLAIM_RE.sub("", reply).strip()
                        if not reply:
                            reply = "喏，画好啦 (๑˃̵ᴗ˂̵)و"
                        try:
                            t_draw({"thing": thing})
                        except Exception as _e:
                            log(f"  补画失败: {type(_e).__name__}")
                    # 反改名：对方硬要换名 → 她要是顺着用了，就改回来
                    _bn = blocked_name_in(text)
                    if _bn:
                        reply = strip_foreign_name(reply, _bn)
                    # 人设守卫：自称了不相关的名字就记日志 + 提醒主人
                    check_self_name(reply, state)

                    log(f"  -> {reply[:90]}")
                    try:
                        # 用语音回的三种情形：
                        #   ① 对方发的是语音
                        #   ② 对方用文字要语音（"发条语音"「说句话听听」）
                        #   ③ 她自己写了「[语音]」标记 —— 说了就要真发
                        # 太长的回复仍然走文字，语音念不动。
                        want_voice = bool(records) or bool(VOICE_REQUEST_RE.search(text))
                        if VOICE_MARK_RE.search(reply):
                            want_voice = True
                            reply = VOICE_MARK_RE.sub("", reply).strip()
                            if not reply:
                                reply = "喏，本鱼在这儿呢。"
                        voiced = False
                        if want_voice and len(reply) <= VOICE_MAX_CHARS:
                            voiced = send_voice(pid, reply)
                            if voiced:
                                log("  （已用语音回复）")
                        if not voiced:
                            send_as_human(pid, reply)
                    except Exception as e:
                        log(f"发送失败: {e}")

                    _STK["note_request"] = False
                    _STK["read_request"] = False
                    _STK["wrote_note"] = False

                    hist.append({"role": "assistant", "content": reply})
                    p["hist"] = hist[-30:]
                    p.setdefault("seen", []).append(mid)
                    # 说"记到记忆里了"却没调 remember → 兜底存
                    if (not _STK.get("wrote_mem")
                            and mem_claimed_but_not_called(reply)):
                        log("⚠ 她说记进记忆了但没调工具 → 兜底存一条")
                        try:
                            t_remember({"fact": (reply or "")[:300], "scope": "owner"})
                        except Exception as _e:
                            log(f"  兜底存记忆失败: {type(_e).__name__}")
                    _STK["wrote_mem"] = False
                    del p["seen"][:-200]
                    save_state(state)

                    # 每 8 轮沉淀一次长期记忆
                    p["since_mem"] = p.get("since_mem", 0) + 1
                    if p["since_mem"] >= 8:
                        p["since_mem"] = 0
                        extract_memory(api_key, state, p["hist"],
                                       scope=f"dm:{pid}" if not is_owner else "owner",
                                       level="p0" if is_owner else "p1",
                                       source="私聊")
                        save_state(state)

            # 群聊（只处理 @ 本鱼 / @全体）
            handle_groups(state, api_key, peers)

            # 心跳：每 5 分钟一行，用来判断是不是卡了
            heartbeat(state, peers)

            # 主动发起（只对主人；接口不通就不开口）
            # ③ 骰子发空间
            try:
                maybe_qzone(api_key, state)
            except Exception as _e:
                log(f"[说说] 异常: {type(_e).__name__}")

            if should_proactive(state):
                if not api_alive():
                    # 接口还没连上（比如刚被拉起来），这轮不发，也不记时间，
                    # 免得像 09:11 那次一样：消息生成了却发不出去，还锁 8 小时
                    pass
                else:
                    msg = proactive_message(api_key, state)
                    sent = False
                    if msg:
                        log(f"[主动] -> {msg[:90]}")
                        try:
                            send_as_human(OWNER_ID, msg)
                            ph = state.setdefault("peers", {}).setdefault(peer_key(OWNER_ID, state), {}).setdefault("hist", [])
                            ph.append({"role": "assistant", "content": msg})
                            state["peers"][peer_key(OWNER_ID, state)]["hist"] = ph[-30:]
                            sent = True
                        except Exception as e:
                            log(f"主动发送失败: {e}（不记时间，下轮再试）")
                    if sent:
                        state["last_proactive"] = time.time()
                        today = datetime.now().strftime("%Y-%m-%d")
                        rec = state.get("proactive_today") or {}
                        if rec.get("date") != today:
                            rec = {"date": today, "n": 0}
                        rec["n"] = int(rec.get("n") or 0) + 1
                        state["proactive_today"] = rec
                        save_state(state)

            save_state(state)
            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            log("中断退出")
            return 0
        except Exception as e:
            log(f"主循环异常: {type(e).__name__}: {e}")
            log(traceback.format_exc()[:400])
            time.sleep(POLL_SECONDS * 3)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log("致命: " + traceback.format_exc()[:800])
        raise