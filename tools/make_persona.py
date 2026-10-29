#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""make_persona.py —— 根据 about_owner.md 自动生成专属角色卡。

用法：
    python tools/make_persona.py

设计原则：
  · **不强求**。没有问卷也能用，只是角色卡会"泛"一点。
  · 先讲清楚"为什么填问卷有用"，再问要不要生成。
  · 生成后先预览，用户点头才写文件。
"""
import io
import json
import os
import sys

# Windows 控制台是 GBK，先强制 stdout 用 UTF-8（否则 ✗ ✓ 这类符号会崩）
try:
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace('-', '') != 'utf8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# ---------- 说明 ----------
INTRO = """
============================================================
  专属角色卡生成器
============================================================

它会做一件事：
  读你的 about_owner.md（问卷答案），生成一张**只属于你**的角色卡。

------------------------------------------------------------
为什么值得填问卷？（不填也能用，只是差很多）
------------------------------------------------------------

  不填问卷：
    角色卡只知道"主人"这个词 ✗
    → 她不知道你几点睡、讨厌什么语气、最近在烦什么
    → 聊起来像"客服"，不像"认识你的人" ✗

  填了问卷：
    她会有很多东西可以接 ✓
    → "你今天又熬夜了吧"（因为你作息写在那）
    → "别用那种口气跟我说话"（因为你写讨厌趾高气扬）
    → **大部分"她真的懂我"的感觉，来自这份档案** ✓

  我自己的做法：
    那份 40 题的问卷，我答了一半就开始用 ✗
    → 明显感觉她说话"有东西接了" ✓

------------------------------------------------------------
问卷在哪：docs/主人问卷.md
答案存成：about_owner.md（.gitignore 已挡住，不会被提交）
============================================================
"""


def load_owner():
    for name in ("about_owner.md", "about_owner.example.md"):
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            return name, io.open(p, encoding="utf-8").read()
    return None, ""


def load_key():
    try:
        from config import API_KEY
        if API_KEY:
            return API_KEY
    except Exception:
        pass
    p = os.path.join(ROOT, "api_key.txt")
    if os.path.exists(p):
        return io.open(p, encoding="utf-8").read().strip()
    return None


def ask(prompt, default=""):
    try:
        v = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        sys.exit(0)
    return v or default


def main():
    print(INTRO)

    name, owner = load_owner()
    if not name:
        print("✗ 没找到 about_owner.md，也没找到模板。")
        print("  先看 docs/主人问卷.md，答几题，存成 about_owner.md。\n")
        return
    is_example = name.endswith("example.md")
    print(f"找到档案：{name}（{len(owner)} 字）")
    if is_example:
        print("⚠ 这是**空白模板**。生成出来的角色卡会比较泛 ✗")
        print("  建议先填 about_owner.md 再来。\n")
    else:
        print("✓ 这是你自己的档案，生成出来的会贴你很多 ✓\n")

    print("-" * 60)
    print("要现在生成角色卡吗？（y = 生成 / n = 先不）")
    print("  说明：生成后**先预览**，你点头才会写进 personas.json。")
    print("-" * 60)
    if ask("  y/n > ", "n").lower() not in ("y", "yes", "1"):
        print("\n好，那先不生成。")
        print("以后想生成，随时再跑：python tools/make_persona.py")
        return

    # ---------- 参数 ----------
    print()
    n_persona = ask("  要几个人格？（1 或 2，默认 2）> ", "2")
    n = 2 if n_persona.startswith("2") else 1
    style = ask("  你喜欢她们什么调子？（活泼 / 安静 / 一活泼一安静，默认最后）> ",
                "一活泼一安静")
    print()

    key = load_key()
    if not key:
        print("✗ 没有 API Key。先在 config.py 里填 API_KEY。")
        return

    # ---------- 调模型 ----------
    import urllib.request
    prompt = f"""根据下面这份"主人档案"，为 QQ 聊天机器人设计 {n} 个角色卡。

要求：
· 每个角色要有：name（名字）、emoji、aliases（3-5 个别名）、desc（一句话定位）、persona（完整人设）
· persona 必须包含【身份】【说话】【性格】【不要】四段
· 必须写清：自称、句子长度、口癖、不会做什么
· 语气要求：{style}
· 角色要**真的能接住档案里的细节**（比如他几点睡、讨厌什么语气、最近在烦什么）
· 不要写成"温柔体贴的助手"这种通用模板 ✗

输出严格的 JSON（不要 markdown 代码块）：
{{"active": "p0", "cards": {{"p0": {{...}}, "p1": {{...}}}}}}

===== 主人档案 =====
{owner[:6000]}
"""

    payload = {"model": "deepseek-flash", "thinking": {"type": "disabled"},
               "temperature": 0.9, "max_tokens": 2500,
               "messages": [{"role": "user", "content": prompt}]}
    print("  正在生成…")
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        txt = d["choices"][0]["message"].get("content") or ""
    except Exception as e:
        print(f"✗ 生成失败：{type(e).__name__}: {e}")
        return

    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j <= i:
        print("✗ 模型没返回合法 JSON。")
        return
    try:
        cards = json.loads(txt[i:j + 1])
    except Exception as e:
        print(f"✗ JSON 解析失败：{e}")
        return

    # ---------- 预览 ----------
    print("\n" + "=" * 60)
    print("  预览")
    print("=" * 60)
    for pid, card in (cards.get("cards") or {}).items():
        print(f"\n[{pid}] {card.get('emoji', '')} {card.get('name', '(无名)')}"
              f"   —— {card.get('desc', '')}")
        per = card.get("persona") or ""
        print("  " + per.replace("\n", "\n  ")[:600])
    print("\n" + "=" * 60)

    if ask("  保存到 personas.json 吗？（y/n，默认 n）> ", "n").lower() not in ("y", "yes", "1"):
        print("\n好，没保存。想改可以调 docs/怎么写角色卡.md 里的参数再跑一次。")
        return

    out = os.path.join(ROOT, "personas.json")
    if os.path.exists(out):
        if ask("  personas.json 已存在，覆盖吗？（y/n，默认 n）> ", "n").lower() not in ("y", "yes", "1"):
            print("  没覆盖。")
            return
    io.open(out, "w", encoding="utf-8").write(
        json.dumps(cards, ensure_ascii=False, indent=2))
    print(f"\n✓ 已保存：{out}")
    print("  重启机器人就生效。")


if __name__ == "__main__":
    main()
