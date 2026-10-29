#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画画 v2 的 DSL 渲染器。

输入是一段**纯 JSON 数据**（不是代码），解释成一张蜡笔童画。
复用 doodle.py 里的画纸、抖动线条、印章库。

指令集（12 个 op）：
  stamp    {name, at, scale, flip}        贴印章（25 种）
  ellipse  {at, r[2], fill, outline}      圆/椭圆
  rect     {at, size[2], fill, outline}   矩形
  polygon  {pts[], fill, outline}         多边形
  line     {pts[], width, color}          折线
  curve    {pts[], width, color}          平滑曲线
  arc      {at, r, from, to, width}       弧线
  dot      {at, r, color}                 小圆点
  text     {at, s, size, color}           文字
  weather  {kind}                         雨/雪/晴
  ground   {y, color}                     地平线
  sign     {on}                           签名
"""
import json
import math
import random

import doodle as D
from PIL import ImageFont

SIZE = 640

COLORS = {
    "red": (232, 84, 84), "orange": (245, 148, 62), "yellow": (248, 206, 74),
    "green": (108, 190, 118), "blue": (78, 158, 226), "purple": (150, 118, 226),
    "pink": (238, 130, 178), "cyan": (120, 200, 210), "brown": (150, 110, 80),
    "grey": (150, 155, 170), "white": (252, 253, 255), "black": (60, 60, 80),
    "skin": (245, 210, 190), "paper": D.PAPER,
}


def _c(name, default=(90, 90, 110)):
    if isinstance(name, (list, tuple)) and len(name) == 3:
        return tuple(int(x) for x in name)
    return COLORS.get(str(name or "").lower(), default)


def _pt(p):
    try:
        x, y = float(p[0]), float(p[1])
    except Exception:
        return (SIZE / 2, SIZE / 2)
    return (max(-40, min(SIZE + 40, x)), max(-40, min(SIZE + 40, y)))


def _num(v, lo, hi, dflt=1.0):
    try:
        v = float(v)
    except Exception:
        return dflt
    return max(lo, min(hi, v))


def _font(size):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        try:
            return ImageFont.truetype(p, int(size))
        except Exception:
            continue
    return ImageFont.load_default()



MAX_SAME = 8      # 同一个东西最多几份
MAX_KIND = 4      # 不同主体最多几类
MAX_ITEMS = 12    # 总元素上限（含装饰）


def enforce_limits(items):
    """硬截断：单样 ≤8、不同主体 ≤4 类、总数 ≤12。返回 (新items, 被砍的数量)。"""
    out, same, kinds = [], {}, 0
    cut = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        op = it.get("op")
        if op == "stamp":
            name = str(it.get("name") or "")
            if name not in same:
                if kinds >= MAX_KIND:
                    cut += 1          # 第 5 类主体，砍
                    continue
                kinds += 1
                same[name] = 0
            if same[name] >= MAX_SAME:
                cut += 1              # 同类超 8 份，砍
                continue
            same[name] += 1
        out.append(it)
    if len(out) > MAX_ITEMS:
        cut += len(out) - MAX_ITEMS
        out = out[:MAX_ITEMS]         # 超总数，砍尾巴（装饰在后面）
    return out, cut


def render(spec, seed=None):
    """把 DSL 渲染成 PIL Image。任何一条指令出错就跳过它，不影响其余。"""
    if seed is not None:
        random.seed(seed)
    if isinstance(spec, str):
        spec = json.loads(spec)
    if not isinstance(spec, dict):
        raise ValueError("spec 必须是对象")

    img, d = D._paper()
    items, _cut = enforce_limits(spec.get("items") or [])

    # 按 y 从远到近画：y 小的（天上/远处）先画，y 大的（近处）后画 → 不再互相盖住
    def _depth(it):
        try:
            if it.get("op") == "stamp":
                return float((it.get("at") or [0, 0])[1])
            if it.get("op") in ("ellipse", "rect", "arc", "dot", "text"):
                return float((it.get("at") or [0, 0])[1])
            if it.get("op") in ("polygon", "line", "curve"):
                pts = it.get("pts") or [[0, 0]]
                return sum(p[1] for p in pts) / max(1, len(pts))
        except Exception:
            pass
        return 999
    items = sorted(items, key=_depth)
    # 顶层也支持（更顺手）：{"weather": "rain", "ground": 520, "sign": true}
    weather = str(spec.get("weather") or "")[:8] or None
    ground_y = _num(spec.get("ground"), 200, 600, 520)
    want_sign = bool(spec.get("sign", True))

    # 先定地平线高度和天气（影响后续构图，但不重排坐标）
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("op") == "weather":
            weather = str(it.get("kind") or "")[:8]
        elif it.get("op") == "ground":
            ground_y = _num(it.get("y"), 200, 600, 520)
        elif it.get("op") == "sign":
            want_sign = bool(it.get("on", True))

    # 地平线
    pts = [(30 + i * (SIZE - 60) / 10, ground_y + random.uniform(-10, 10)) for i in range(11)]
    D.stroke(d, pts, _c("green"), 6, 3)
    for _ in range(7):
        x = random.randrange(40, SIZE - 40)
        D.stroke(d, [(x, ground_y + 2), (x + random.uniform(-8, 8), ground_y - 28 - random.uniform(0, 16))],
                 _c("green"), 4, 2, 1)

    drawn, skipped = 0, []
    for it in items:
        if not isinstance(it, dict):
            continue
        op = it.get("op")
        try:
            if op == "stamp":
                name = str(it.get("name") or "")
                fn = (D.PARTS.get(name) or (None,))[0]
                if fn is None:
                    skipped.append(f"stamp:{name}")
                    continue
                at = _pt(it.get("at") or [SIZE / 2, ground_y - 60])
                fn(d, at[0], at[1], _num(it.get("scale"), 0.15, 2.2, 0.9))
                drawn += 1
            elif op == "ellipse":
                at = _pt(it.get("at") or [SIZE / 2, SIZE / 2])
                r = it.get("r") or [40, 40]
                rx, ry = _num(r[0], 2, 320, 40), _num(r[1], 2, 320, 40)
                box = [at[0] - rx, at[1] - ry, at[0] + rx, at[1] + ry]
                fill = _c(it.get("fill"), None) if it.get("fill") else None
                if fill:
                    d.ellipse(box, fill=fill)
                if it.get("outline", True):
                    D.stroke(d, D.circle_pts(at[0], at[1], max(rx, ry), 18, ry / max(rx, 1)),
                             _c(it.get("color"), D.INK), 4, 2)
                drawn += 1
            elif op == "rect":
                at = _pt(it.get("at") or [SIZE / 2, SIZE / 2])
                sz = it.get("size") or [60, 60]
                w, h = _num(sz[0], 2, 600, 60), _num(sz[1], 2, 600, 60)
                box = [at[0] - w / 2, at[1] - h / 2, at[0] + w / 2, at[1] + h / 2]
                fill = _c(it.get("fill"), None) if it.get("fill") else None
                if fill:
                    d.rectangle(box, fill=fill)
                if it.get("outline", True):
                    D.stroke(d, [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]),
                                 (box[0], box[3]), (box[0], box[1])],
                             _c(it.get("color"), D.INK), 4, 2, 1)
                drawn += 1
            elif op == "polygon":
                pts = [_pt(p) for p in (it.get("pts") or [])][:40]
                if len(pts) < 3:
                    skipped.append("polygon<3pts")
                    continue
                if it.get("fill"):
                    d.polygon(D._wobble(pts, 2), fill=_c(it.get("fill")))
                D.stroke(d, pts + [pts[0]], _c(it.get("color"), D.INK), 4, 2, 1)
                drawn += 1
            elif op == "line":
                pts = [_pt(p) for p in (it.get("pts") or [])][:40]
                if len(pts) < 2:
                    skipped.append("line<2pts")
                    continue
                D.stroke(d, pts, _c(it.get("color"), D.INK),
                         int(_num(it.get("width"), 1, 20, 4)), 2)
                drawn += 1
            elif op == "curve":
                pts = [_pt(p) for p in (it.get("pts") or [])][:12]
                if len(pts) < 3:
                    skipped.append("curve<3pts")
                    continue
                smooth = []
                for i in range(len(pts) - 1):
                    for t in (0.0, 0.5):
                        smooth.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t,
                                       pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t))
                smooth.append(pts[-1])
                D.stroke(d, smooth, _c(it.get("color"), D.INK),
                         int(_num(it.get("width"), 1, 20, 4)), 2)
                drawn += 1
            elif op == "arc":
                at = _pt(it.get("at") or [SIZE / 2, SIZE / 2])
                r = _num(it.get("r"), 4, 300, 40)
                a1 = _num(it.get("from"), -360, 360, 180)
                a2 = _num(it.get("to"), -360, 360, 360)
                D.stroke(d, D.circle_pts(at[0], at[1], r, 14, 1.0, math.radians(a1) * 0 + a1 * math.pi / 180),
                         _c(it.get("color"), D.INK), int(_num(it.get("width"), 1, 16, 4)), 2, 1)
                drawn += 1
            elif op == "dot":
                at = _pt(it.get("at") or [SIZE / 2, SIZE / 2])
                r = _num(it.get("r"), 1, 40, 6)
                d.ellipse([at[0] - r, at[1] - r, at[0] + r, at[1] + r],
                          fill=_c(it.get("color"), D.INK))
                drawn += 1
            elif op == "text":
                at = _pt(it.get("at") or [60, 60])
                s = str(it.get("s") or "")[:20]
                if not s:
                    skipped.append("text empty")
                    continue
                f = _font(_num(it.get("size"), 10, 60, 26))
                d.text(at, s, font=f, fill=_c(it.get("color"), (110, 110, 140)))
                drawn += 1
        except Exception as e:
            skipped.append(f"{op}:{type(e).__name__}")

    if weather:
        try:
            D.paint_weather(d, weather if weather in ("rain", "snow", "sunny") else None)
        except Exception:
            pass
    if want_sign:
        D._signature(img)
    img = img.filter(__import__("PIL.ImageFilter", fromlist=["ImageFilter"]).SMOOTH)
    return img, {"drawn": drawn, "skipped": skipped[:6]}
