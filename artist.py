#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画师：把一句描述变成 DSL（纯 JSON）。

单独调一次模型，只干构图这一件事，不掺聊天人格，质量更稳。
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, r"dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GUIDE = """你是儿童画的美术指导。把用户的描述翻译成一段"绘画指令 JSON"。

画布 640x640。坐标原点左上，x 向右，y 向下。

【构图规则】
- 天空区：y 60-260（太阳、月亮、云、星星、彩虹、小鸟、气球）
- 地面线：y ≈ 520（房子、树、花、人、猫、狗、兔子、蘑菇、雪人、雨伞站在线上）
- 水里：y 560-610（鲸鱼、小鱼）
- 悬浮：y 280-460（爱心、蛋糕、苹果、礼物、白米饭）
- **数量规则（重要）**：
  · 同一个东西**说几个画几个**，最多 8 个（"五只猫"→5 只，"十只猫"→8 只）
  · **不同的主体最多 4 类**（"猫、狗、房子、树、花"→只画前 4 类）
  · **总元素（含云、雨、文字、泡泡这些装饰）不超过 12 个**
  · 别为了丰富而堆东西 —— 空一点更好看
- **同类多个要横向排开**：5 只猫就 x 从 90 到 550 均匀分布，别都堆在一个点上。
- **别让东西互相挡住**：相邻主体的中心 x 至少差 120，同一个 y 上前后的至少差 90。
- 左中右分布，别全挤一边。

【可以用 stamp 贴这些现成的】（画得精细，优先用）
whale 鲸鱼 / fish 小鱼 / sun 太阳 / moon 月亮 / cloud 云 / star 星星 /
rainbow 彩虹 / bird 小鸟 / balloon 气球 / flower 花 / tree 树 / house 房子 /
person 小人 / cat 猫 / dog 小狗 / rabbit 兔子 / mushroom 蘑菇 / umbrella 雨伞 /
mountain 山 / snowman 雪人 / heart 爱心 / rice 白米饭 / cake 蛋糕 /
apple 苹果 / gift 礼物

【没有 stamp 的东西，用形状拼】
ellipse(at,r,fill) / rect(at,size,fill) / polygon(pts,fill) /
line(pts,width,color) / curve(pts,width,color) / arc(at,r,from,to,width) /
dot(at,r,color) / text(at,s,size) / weather(kind: rain|snow|sunny) / ground(y) / sign(on)

颜色只能用名字：red orange yellow green blue purple pink cyan brown grey white black skin
所有数值必须在 0-640 之间。不要写注释，不要写代码，只输出 JSON。

【示例1】"下雨天的房子，有只猫"
{"weather":"rain","items":[
 {"op":"stamp","name":"house","at":[210,470],"scale":0.9},
 {"op":"stamp","name":"cat","at":[450,460],"scale":0.65},
 {"op":"stamp","name":"umbrella","at":[450,405],"scale":0.55},
 {"op":"text","at":[50,60],"s":"雨天","size":26}]}

【示例2】"鲸鱼在水里吐泡泡"
{"items":[
 {"op":"stamp","name":"whale","at":[300,580],"scale":0.75},
 {"op":"dot","at":[300,520],"r":8,"color":"cyan"},
 {"op":"dot","at":[330,495],"r":6,"color":"cyan"},
 {"op":"dot","at":[290,470],"r":4,"color":"cyan"}]}

【示例3】"小姑娘在草地上看星星"
{"items":[
 {"op":"ground","y":520},
 {"op":"stamp","name":"person","at":[320,470],"scale":0.9},
 {"op":"stamp","name":"star","at":[150,150],"scale":0.6},
 {"op":"stamp","name":"star","at":[480,120],"scale":0.5},
 {"op":"stamp","name":"moon","at":[560,180],"scale":0.6},
 {"op":"line","pts":[[60,510],[580,512]],"width":5,"color":"green"}]}

现在按要求输出，只输出 JSON，不要任何解释。"""


def spec_for(desc, api_key, model="deepseek-flash", timeout=60):
    """描述 → DSL dict。失败抛异常。"""
    payload = {
        "model": model,
        "thinking": {"type": "disabled"},
        "temperature": 0.7,
        "max_tokens": 900,
        "messages": [
            {"role": "system", "content": GUIDE},
            {"role": "user", "content": f"描述：{desc}\n请输出 JSON。"},
        ],
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    txt = (d["choices"][0]["message"].get("content") or "").strip()
    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("没返回 JSON")
    spec = json.loads(txt[i:j + 1])
    if not isinstance(spec.get("items"), list) or not spec["items"]:
        raise ValueError("items 为空")
    return spec
