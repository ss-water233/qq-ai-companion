import re
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小鱼的画板 —— 代码画的儿童画。

设计原则：**故意不完美**。
  · 线条抖动（手抖感）
  · 填充留白边、涂不匀
  · 颜色用蜡笔色板，不用纯黑
  · 形状比例不对（小孩画画就这样）
依赖只有 Pillow，不需要任何模型。
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 640
PAPER = (252, 249, 240)

# 蜡笔色板（都偏亮，不用纯黑）
CRAYONS = [
    (232, 84, 84), (245, 148, 62), (248, 206, 74), (108, 190, 118),
    (78, 158, 226), (150, 118, 226), (238, 130, 178), (120, 200, 210),
    (150, 110, 80), (90, 90, 110),
]
INK = (70, 70, 95)


def _j(p, a=2.2):
    return (p[0] + random.uniform(-a, a), p[1] + random.uniform(-a, a))


def _wobble(pts, a=2.2):
    return [_j(p, a) for p in pts]


def stroke(d, pts, color=INK, width=5, a=2.2, passes=2):
    """抖动的粗线。多画一遍模拟蜡笔叠色。"""
    for k in range(passes):
        p = _wobble(pts, a * (1 + 0.4 * k))
        if len(p) < 2:
            continue
        d.line(p, fill=color, width=max(1, width - k), joint="curve")


def circle_pts(cx, cy, r, n=22, squash=1.0, start=0.0):
    out = []
    for i in range(n + 1):
        t = start + 2 * math.pi * i / n
        out.append((cx + r * math.cos(t), cy + r * squash * math.sin(t)))
    return out


def blob(d, cx, cy, rx, ry, color, fill=True, width=5):
    """椭圆形的"涂色块"，边缘故意不圆。"""
    pts = [(cx + rx * math.cos(t) + random.uniform(-2, 2),
            cy + ry * math.sin(t) + random.uniform(-2, 2))
           for t in [i * 2 * math.pi / 20 for i in range(21)]]
    if fill:
        d.polygon(pts, fill=color)
    stroke(d, pts, color if not fill else INK, width, 2.0, 1)


# ---------------- 零件 ----------------

def p_whale(d, cx, cy, s=1.0):
    col = random.choice([(78, 158, 226), (120, 200, 210), (150, 118, 226)])
    # 尾巴先画（在身体后面）
    tail = [(cx + 74 * s, cy - 4 * s), (cx + 128 * s, cy - 44 * s),
            (cx + 136 * s, cy + 6 * s), (cx + 128 * s, cy + 48 * s),
            (cx + 74 * s, cy + 6 * s)]
    d.polygon(_wobble(tail, 2), fill=col)
    stroke(d, tail + [tail[0]], INK, 4, 2, 1)
    blob(d, cx, cy, 92 * s, 66 * s, col)
    # 眼睛
    d.ellipse([cx - 40 * s, cy - 20 * s, cx - 22 * s, cy + 2 * s], fill=INK)
    d.ellipse([cx + 6 * s, cy - 20 * s, cx + 24 * s, cy + 2 * s], fill=INK)
    # 脸颊
    for sx in (-1, 1):
        d.ellipse([cx + sx * 46 * s - 12 * s, cy + 2 * s,
                   cx + sx * 46 * s + 12 * s, cy + 20 * s], fill=(245, 170, 190))
    # 嘴
    stroke(d, circle_pts(cx - 6 * s, cy + 14 * s, 22 * s, 10, 0.5, 0.15), INK, 4, 1.5, 1)
    # 喷水（一道水柱 + 几滴水）
    stroke(d, [(cx - 12 * s, cy - 58 * s), (cx - 16 * s, cy - 88 * s),
               (cx - 6 * s, cy - 104 * s)], (120, 190, 230), 4, 2.5)
    for dx, dy in ((-34, -96), (-20, -116), (6, -100), (-46, -78)):
        d.ellipse([cx + dx * s - 5 * s, cy + dy * s - 8 * s,
                   cx + dx * s + 5 * s, cy + dy * s + 2 * s],
                  fill=(120, 190, 230))


def p_sun(d, cx, cy, s=1.0):
    col = (250, 190, 60)
    d.ellipse([cx - 46 * s, cy - 46 * s, cx + 46 * s, cy + 46 * s], fill=col)
    stroke(d, circle_pts(cx, cy, 48 * s, 18), (232, 150, 40), 5, 2.2)
    for i in range(8):
        t = i * math.pi / 4 + random.uniform(-.1, .1)
        stroke(d, [(cx + 56 * s * math.cos(t), cy + 56 * s * math.sin(t)),
                   (cx + 84 * s * math.cos(t), cy + 84 * s * math.sin(t))],
               (245, 158, 62), 5, 2.5)
    # 脸（大一点，别像符号）
    d.ellipse([cx - 22 * s, cy - 16 * s, cx - 10 * s, cy - 2 * s], fill=INK)
    d.ellipse([cx + 10 * s, cy - 16 * s, cx + 22 * s, cy - 2 * s], fill=INK)
    stroke(d, circle_pts(cx, cy + 12 * s, 20 * s, 10, 0.55, 0.1), INK, 4, 1.5, 1)
    for sx in (-1, 1):
        d.ellipse([cx + sx * 30 * s - 8 * s, cy + 2 * s,
                   cx + sx * 30 * s + 8 * s, cy + 14 * s], fill=(245, 150, 140))


def p_cloud(d, cx, cy, s=1.0):
    for dx, dy, r in ((-40, 6, 30), (0, -12, 38), (42, 4, 28)):
        stroke(d, circle_pts(cx + dx * s, cy + dy * s, r * s, 16), (150, 170, 210), 5, 2.5)


def p_star(d, cx, cy, s=1.0):
    col = random.choice([(248, 206, 74), (245, 148, 62)])
    pts = []
    for i in range(10):
        r = (48 if i % 2 == 0 else 20) * s
        t = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    pts.append(pts[0])
    d.polygon(_wobble(pts, 2.5), fill=col)
    stroke(d, pts, (210, 160, 40), 4, 2.5, 1)


def p_flower(d, cx, cy, s=1.0):
    stroke(d, [(cx, cy + 20 * s), (cx + random.uniform(-6, 6), cy + 92 * s)], (108, 190, 118), 6, 3)
    stroke(d, circle_pts(cx, cy, 56 * s, 10, 0.32, 0.4), (108, 190, 118), 5, 2.5, 1)
    col = random.choice([(238, 130, 178), (232, 84, 84), (248, 206, 74)])
    for i in range(5):
        t = i * 2 * math.pi / 5
        blob(d, cx + 26 * s * math.cos(t), cy + 26 * s * math.sin(t),
             22 * s, 22 * s, col)
    d.ellipse([cx - 11 * s, cy - 11 * s, cx + 11 * s, cy + 11 * s], fill=(250, 210, 90))


def p_cat(d, cx, cy, s=1.0):
    col = random.choice([(245, 200, 150), (200, 200, 200), (150, 118, 226)])
    blob(d, cx, cy, 62 * s, 58 * s, col)
    # 耳朵
    for sx in (-1, 1):
        pts = [(cx + sx * 20 * s, cy - 46 * s), (cx + sx * 52 * s, cy - 86 * s),
               (cx + sx * 54 * s, cy - 40 * s)]
        d.polygon(_wobble(pts, 2), fill=col)
        stroke(d, pts, INK, 4, 2, 1)
    d.ellipse([cx - 32 * s, cy - 12 * s, cx - 16 * s, cy + 4 * s], fill=INK)
    d.ellipse([cx + 16 * s, cy - 12 * s, cx + 32 * s, cy + 4 * s], fill=INK)
    stroke(d, circle_pts(cx, cy + 16 * s, 14 * s, 8, 0.5), INK, 4, 1.5, 1)
    for dy in (-2, 8):
        stroke(d, [(cx - 30 * s, cy + dy * s), (cx - 62 * s, cy + (dy - 8) * s)], INK, 3, 2, 1)
        stroke(d, [(cx + 30 * s, cy + dy * s), (cx + 62 * s, cy + (dy - 8) * s)], INK, 3, 2, 1)


def p_house(d, cx, cy, s=1.0):
    stroke(d, [(cx - 60 * s, cy + 70 * s), (cx - 60 * s, cy - 10 * s),
               (cx + 60 * s, cy - 10 * s), (cx + 60 * s, cy + 70 * s)],
           (150, 110, 80), 6, 2.5)
    roof = [(cx - 76 * s, cy - 8 * s), (cx, cy - 76 * s), (cx + 76 * s, cy - 8 * s)]
    d.polygon(_wobble(roof, 2), fill=(232, 84, 84))
    stroke(d, roof, (200, 60, 60), 5, 2.5, 1)
    stroke(d, [(cx - 18 * s, cy + 70 * s), (cx - 18 * s, cy + 18 * s),
               (cx + 18 * s, cy + 18 * s), (cx + 18 * s, cy + 70 * s)], (150, 110, 80), 5, 2)
    stroke(d, [(cx + 30 * s, cy + 14 * s), (cx + 52 * s, cy + 14 * s),
               (cx + 52 * s, cy + 42 * s), (cx + 30 * s, cy + 42 * s),
               (cx + 30 * s, cy + 14 * s)], (78, 158, 226), 4, 2)


def p_person(d, cx, cy, s=1.0):
    col = random.choice(CRAYONS)
    d.ellipse([cx - 26 * s, cy - 92 * s, cx + 26 * s, cy - 40 * s], outline=INK, width=5)
    stroke(d, [(cx, cy - 40 * s), (cx, cy + 24 * s)], col, 6, 2)
    stroke(d, [(cx - 44 * s, cy - 14 * s), (cx, cy - 26 * s), (cx + 44 * s, cy - 14 * s)], col, 6, 2)
    stroke(d, [(cx - 36 * s, cy + 76 * s), (cx, cy + 24 * s), (cx + 36 * s, cy + 76 * s)], col, 6, 2)
    d.ellipse([cx - 14 * s, cy - 78 * s, cx - 6 * s, cy - 70 * s], fill=INK)
    d.ellipse([cx + 6 * s, cy - 78 * s, cx + 14 * s, cy - 70 * s], fill=INK)
    stroke(d, circle_pts(cx, cy - 60 * s, 11 * s, 8, 0.5), INK, 3, 1.2, 1)


def p_heart(d, cx, cy, s=1.0):
    col = random.choice([(238, 130, 178), (232, 84, 84)])
    pts = []
    for i in range(24):
        t = i * 2 * math.pi / 24
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * 4.2 * s, cy + y * 4.2 * s))
    d.polygon(_wobble(pts, 2.5), fill=col)
    stroke(d, pts, (200, 90, 130), 4, 2.5, 1)


def p_rice(d, cx, cy, s=1.0):
    """白米饭 —— 本鱼的命。米饭要描边，不然白底看不见。"""
    for dx, dy, r in ((-22, -10, 30), (18, -14, 28), (0, -32, 27)):
        box = [cx + (dx - r) * s, cy + (dy - r * .72) * s,
               cx + (dx + r) * s, cy + (dy + r * .72) * s]
        d.ellipse(box, fill=(255, 255, 252), outline=(178, 176, 196), width=3)
    bowl = [(cx - 66 * s, cy + 10 * s), (cx + 66 * s, cy + 10 * s),
            (cx + 46 * s, cy + 74 * s), (cx - 46 * s, cy + 74 * s)]
    d.polygon(_wobble(bowl, 2), fill=(228, 230, 242))
    stroke(d, bowl + [bowl[0]], (150, 150, 175), 5, 2.5, 1)
    stroke(d, [(cx - 66 * s, cy + 10 * s), (cx + 66 * s, cy + 10 * s)],
           (150, 150, 175), 4, 2, 1)
    stroke(d, [(cx + 50 * s, cy - 40 * s), (cx + 96 * s, cy - 96 * s)], (170, 130, 90), 5, 2)
    stroke(d, [(cx + 70 * s, cy - 26 * s), (cx + 110 * s, cy - 80 * s)], (170, 130, 90), 5, 2)


def p_fish(d, cx, cy, s=1.0):
    col = random.choice([(245, 148, 62), (120, 200, 210), (238, 130, 178)])
    blob(d, cx, cy, 54 * s, 34 * s, col)
    d.polygon(_wobble([(cx + 44 * s, cy), (cx + 88 * s, cy - 26 * s),
                       (cx + 88 * s, cy + 26 * s)], 2), fill=col)
    d.ellipse([cx - 26 * s, cy - 10 * s, cx - 14 * s, cy + 2 * s], fill=INK)
    stroke(d, circle_pts(cx - 34 * s, cy + 8 * s, 10 * s, 8, 0.5), INK, 3, 1.2, 1)



def p_moon(d, cx, cy, s=1.0):
    """实心月亮 + 陨石坑（挖洞式月牙画出来像破洞，放弃）。"""
    col = (252, 238, 175)
    d.ellipse([cx - 44 * s, cy - 44 * s, cx + 44 * s, cy + 44 * s], fill=col)
    stroke(d, circle_pts(cx, cy, 45 * s, 16), (228, 208, 120), 4, 2.2)
    for dx, dy, r in ((-22, -14, 9), (-28, 14, 7), (-8, 26, 6), (6, -26, 5)):
        d.ellipse([cx + (dx - r) * s, cy + (dy - r) * s,
                   cx + (dx + r) * s, cy + (dy + r) * s], fill=(240, 224, 155))
    # 两只睡着的小眼睛，看起来更像月亮
    stroke(d, [(cx - 16 * s, cy - 2 * s), (cx - 8 * s, cy - 8 * s), (cx, cy - 2 * s)],
           (200, 180, 100), 3, 1.5, 1)
    stroke(d, [(cx + 8 * s, cy - 2 * s), (cx + 16 * s, cy - 8 * s), (cx + 24 * s, cy - 2 * s)],
           (200, 180, 100), 3, 1.5, 1)


def p_rainbow(d, cx, cy, s=1.0):
    cols = [(232, 84, 84), (245, 148, 62), (248, 206, 74),
            (108, 190, 118), (78, 158, 226), (150, 118, 226)]
    for i, c in enumerate(cols):
        r = (120 - i * 14) * s
        stroke(d, [(cx + r * __import__("math").cos(t),
                    cy + r * __import__("math").sin(t))
                   for t in [3.34 + i2 * 2.8 / 12 for i2 in range(13)]],
               c, 9, 2.4)


def p_tree(d, cx, cy, s=1.0):
    stroke(d, [(cx, cy + 20 * s), (cx + 2, cy + 110 * s)], (150, 110, 80), 12, 3)
    for dx, dy, r in ((0, -34, 46), (-34, -6, 34), (34, -6, 34)):
        d.ellipse([cx + (dx - r) * s, cy + (dy - r) * s,
                   cx + (dx + r) * s, cy + (dy + r) * s], fill=(108, 180, 110))
        stroke(d, circle_pts(cx + dx * s, cy + dy * s, r * s, 16),
               (80, 150, 90), 4, 2.4, 1)


def p_balloon(d, cx, cy, s=1.0):
    col = random.choice([(232, 84, 84), (238, 130, 178), (78, 158, 226), (248, 206, 74)])
    d.ellipse([cx - 32 * s, cy - 40 * s, cx + 32 * s, cy + 34 * s], fill=col)
    stroke(d, circle_pts(cx, cy - 4 * s, 34 * s, 16), (200, 120, 130), 4, 2, 1)
    d.polygon(_wobble([(cx - 7 * s, cy + 32 * s), (cx + 7 * s, cy + 32 * s),
                       (cx, cy + 44 * s)], 1), fill=col)
    stroke(d, [(cx, cy + 44 * s), (cx + 8 * s, cy + 96 * s)], INK, 3, 3, 1)


def p_cake(d, cx, cy, s=1.0):
    stroke(d, [(cx - 54 * s, cy + 44 * s), (cx - 54 * s, cy - 10 * s),
               (cx + 54 * s, cy - 10 * s), (cx + 54 * s, cy + 44 * s)],
           (200, 150, 110), 5, 2.4)
    stroke(d, circle_pts(cx, cy - 10 * s, 54 * s, 14, 0.28), (238, 130, 178), 7, 2.4)
    for dx in (-28, 0, 28):
        stroke(d, [(cx + dx * s, cy - 30 * s), (cx + dx * s, cy - 52 * s)],
               (238, 130, 178), 4, 2, 1)
        d.ellipse([cx + (dx - 5) * s, cy - 66 * s, cx + (dx + 5) * s, cy - 54 * s],
                  fill=(250, 190, 60))


def p_bird(d, cx, cy, s=1.0):
    stroke(d, [(cx - 30 * s, cy), (cx - 12 * s, cy - 12 * s), (cx, cy)],
           INK, 4, 2)
    stroke(d, [(cx, cy), (cx + 12 * s, cy - 12 * s), (cx + 30 * s, cy)], INK, 4, 2)


def p_umbrella(d, cx, cy, s=1.0):
    col = random.choice([(232, 84, 84), (78, 158, 226), (150, 118, 226)])
    pts = [(cx - 60 * s, cy), (cx, cy - 54 * s), (cx + 60 * s, cy)]
    d.pieslice([cx - 60 * s, cy - 54 * s, cx + 60 * s, cy + 54 * s], 180, 360, fill=col)
    stroke(d, circle_pts(cx, cy, 60 * s, 12, 1.0, 3.14), INK, 4, 2)
    stroke(d, [(cx, cy), (cx, cy + 54 * s)], (150, 110, 80), 5, 2)
    stroke(d, [(cx, cy + 54 * s), (cx + 16 * s, cy + 62 * s)], (150, 110, 80), 5, 2)


def p_mountain(d, cx, cy, s=1.0):
    pts = [(cx - 90 * s, cy + 60 * s), (cx, cy - 70 * s), (cx + 90 * s, cy + 60 * s)]
    d.polygon(_wobble(pts, 3), fill=(150, 170, 150))
    stroke(d, pts, (110, 130, 110), 4, 2.5, 1)
    cap = [(cx - 26 * s, cy - 16 * s), (cx, cy - 70 * s), (cx + 26 * s, cy - 16 * s)]
    d.polygon(_wobble(cap, 2), fill=(248, 250, 252))


def p_dog(d, cx, cy, s=1.0):
    col = random.choice([(210, 170, 120), (180, 140, 100), (240, 220, 190)])
    blob(d, cx, cy, 52 * s, 42 * s, col)
    for sx in (-1, 1):
        d.ellipse([cx + sx * 52 * s - 16 * s, cy - 34 * s,
                   cx + sx * 52 * s + 4 * s, cy + 26 * s], fill=col)
    d.ellipse([cx - 26 * s, cy - 12 * s, cx - 14 * s, cy], fill=INK)
    d.ellipse([cx + 14 * s, cy - 12 * s, cx + 26 * s, cy], fill=INK)
    d.ellipse([cx - 9 * s, cy + 6 * s, cx + 9 * s, cy + 18 * s], fill=INK)
    stroke(d, circle_pts(cx, cy + 22 * s, 14 * s, 8, 0.6), INK, 3, 1.5, 1)


def p_rabbit(d, cx, cy, s=1.0):
    col = (245, 242, 238)
    blob(d, cx, cy, 40 * s, 36 * s, col)
    for sx in (-1, 1):
        d.ellipse([cx + sx * 16 * s - 11 * s, cy - 96 * s,
                   cx + sx * 16 * s + 11 * s, cy - 20 * s], fill=col)
        d.ellipse([cx + sx * 16 * s - 5 * s, cy - 88 * s,
                   cx + sx * 16 * s + 5 * s, cy - 30 * s], fill=(245, 180, 195))
    d.ellipse([cx - 22 * s, cy - 8 * s, cx - 12 * s, cy + 2 * s], fill=INK)
    d.ellipse([cx + 12 * s, cy - 8 * s, cx + 22 * s, cy + 2 * s], fill=INK)
    d.ellipse([cx - 5 * s, cy + 8 * s, cx + 5 * s, cy + 15 * s], fill=(240, 150, 170))


def p_apple(d, cx, cy, s=1.0):
    col = (225, 80, 80)
    d.ellipse([cx - 32 * s, cy - 34 * s, cx + 32 * s, cy + 34 * s], fill=col)
    stroke(d, circle_pts(cx, cy, 33 * s, 14), (190, 60, 60), 4, 2, 1)
    stroke(d, [(cx, cy - 32 * s), (cx + 4 * s, cy - 50 * s)], (130, 100, 70), 4, 2, 1)
    stroke(d, [(cx + 4 * s, cy - 46 * s), (cx + 26 * s, cy - 56 * s),
               (cx + 14 * s, cy - 38 * s)], (110, 180, 110), 4, 2, 1)


def p_mushroom(d, cx, cy, s=1.0):
    stroke(d, [(cx - 10 * s, cy + 6 * s), (cx - 10 * s, cy + 46 * s),
               (cx + 10 * s, cy + 46 * s), (cx + 10 * s, cy + 6 * s)],
           (240, 235, 225), 4, 2, 1)
    d.pieslice([cx - 46 * s, cy - 42 * s, cx + 46 * s, cy + 30 * s], 180, 360,
               fill=(225, 80, 80))
    stroke(d, circle_pts(cx, cy - 6 * s, 46 * s, 12, 1.0, 3.14), (190, 60, 60), 4, 2, 1)
    for dx, dy in ((-20, -18), (8, -26), (24, -12)):
        d.ellipse([cx + dx * s - 6 * s, cy + dy * s - 6 * s,
                   cx + dx * s + 6 * s, cy + dy * s + 6 * s], fill=(255, 250, 245))


def p_gift(d, cx, cy, s=1.0):
    box = [(cx - 44 * s, cy - 20 * s), (cx + 44 * s, cy - 20 * s),
           (cx + 44 * s, cy + 44 * s), (cx - 44 * s, cy + 44 * s)]
    d.polygon(_wobble(box, 2), fill=random.choice([(238, 130, 178), (78, 158, 226)]))
    stroke(d, box + [box[0]], INK, 4, 2, 1)
    stroke(d, [(cx, cy - 20 * s), (cx, cy + 44 * s)], (248, 206, 74), 7, 2, 1)
    stroke(d, [(cx - 44 * s, cy + 10 * s), (cx + 44 * s, cy + 10 * s)], (248, 206, 74), 7, 2, 1)
    for sx in (-1, 1):
        stroke(d, [(cx, cy - 20 * s), (cx + sx * 22 * s, cy - 44 * s)], (248, 206, 74), 6, 2, 1)


def p_snowman(d, cx, cy, s=1.0):
    d.ellipse([cx - 46 * s, cy + 4 * s, cx + 46 * s, cy + 86 * s], fill=(252, 253, 255))
    d.ellipse([cx - 34 * s, cy - 46 * s, cx + 34 * s, cy + 16 * s], fill=(252, 253, 255))
    stroke(d, circle_pts(cx, cy + 45 * s, 46 * s, 16), (200, 210, 225), 4, 2, 1)
    stroke(d, circle_pts(cx, cy - 16 * s, 34 * s, 16), (200, 210, 225), 4, 2, 1)
    d.ellipse([cx - 16 * s, cy - 28 * s, cx - 6 * s, cy - 18 * s], fill=INK)
    d.ellipse([cx + 6 * s, cy - 28 * s, cx + 16 * s, cy - 18 * s], fill=INK)
    d.polygon([(cx, cy - 10 * s), (cx + 22 * s, cy - 4 * s), (cx, cy + 2 * s)],
              fill=(245, 148, 62))


# layer: sky 天上 / ground 地面 / water 水里 / any 悬浮
PARTS = {
    "whale": (p_whale, ("鲸鱼", "鲸", "whale", "小鲸鱼"), "water"),
    "fish": (p_fish, ("小鱼", "鱼", "fish"), "water"),
    "sun": (p_sun, ("太阳", "日", "sun"), "sky"),
    "moon": (p_moon, ("月亮", "月", "moon"), "sky"),
    "cloud": (p_cloud, ("云", "cloud"), "sky"),
    "star": (p_star, ("星", "star"), "sky"),
    "rainbow": (p_rainbow, ("彩虹", "rainbow"), "sky"),
    "bird": (p_bird, ("小鸟", "鸟", "bird"), "sky"),
    "balloon": (p_balloon, ("气球", "balloon"), "sky"),
    "flower": (p_flower, ("花", "flower"), "ground"),
    "tree": (p_tree, ("树", "tree"), "ground"),
    "house": (p_house, ("房子", "屋", "家", "house"), "ground"),
    "person": (p_person, ("人", "你", "我", "person", "小人"), "ground"),
    "cat": (p_cat, ("猫", "cat"), "ground"),
    "heart": (p_heart, ("心", "爱", "heart"), "any"),
    "rice": (p_rice, ("米饭", "饭", "吃", "rice"), "any"),
    "cake": (p_cake, ("蛋糕", "cake"), "any"),
    "umbrella": (p_umbrella, ("雨伞", "伞", "umbrella"), "ground"),
    "mountain": (p_mountain, ("山", "mountain"), "ground"),
    "dog": (p_dog, ("小狗", "狗", "dog"), "ground"),
    "rabbit": (p_rabbit, ("兔子", "兔", "rabbit"), "ground"),
    "apple": (p_apple, ("苹果", "apple"), "any"),
    "mushroom": (p_mushroom, ("蘑菇", "mushroom"), "ground"),
    "gift": (p_gift, ("礼物", "gift"), "any"),
    "snowman": (p_snowman, ("雪人", "snowman"), "ground"),
}


CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
MEASURE = "条只个朵颗根张幅匹块碗杯"


def _count_before(text, pos):
    """看关键词前面有没有写数量：「两条鱼」→2，「画五朵花」→5。"""
    import re as _re
    pre = text[max(0, pos - 4):pos].rstrip(MEASURE)
    for ch in ("十", "九", "八", "七", "六", "五", "四", "三", "二", "两", "一"):
        if pre.endswith(ch):
            return CN_NUM[ch]
    m = _re.search(r"(\d+)$", pre)
    if m:
        return int(m.group(1))
    return 1


def parse_parts(thing):
    """从描述里认出画什么、各画几个。返回 [(零件, 数量), ...]，最多四样。"""
    t = (thing or "").lower()
    picked = []
    for key, (_fn, kws, _layer) in PARTS.items():
        for kw in sorted(kws, key=len, reverse=True):
            i = t.find(kw.lower())
            if i < 0:
                continue
            picked.append([key, max(1, min(_count_before(t, i), 6)), i])
            break
    # 「鱼」会同时命中 whale 和 fish，让鲸鱼优先
    keys = {p[0] for p in picked}
    if "snowman" in keys and "person" in keys:
        picked = [p for p in picked if p[0] != "person"]
    if "whale" in keys and "fish" in keys:
        # 「鲸鱼」本身就含"鱼"，只有文本里另外提到小鱼/鱼儿，才保留 fish
        if not re.search(r"(小鱼|鱼儿|鱼群|一条鱼|两条鱼|条鱼)", thing):
            picked = [p for p in picked if p[0] != "fish"]
    return [(p[0], p[1]) for p in picked[:4]]


def _paper():
    img = Image.new("RGB", (SIZE, SIZE), PAPER)
    d = ImageDraw.Draw(img)
    # 纸的瑕疵
    for _ in range(900):
        x, y = random.randrange(SIZE), random.randrange(SIZE)
        c = random.randint(238, 252)
        d.point((x, y), fill=(c, c, c - 4))
    return img, d


def _signature(img):
    """右下角歪歪扭扭的签名。"""
    txt = "小鱼 画"
    font = None
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
                 r"C:\Windows\Fonts\simhei.ttf"):
        try:
            font = ImageFont.truetype(path, 22)
            break
        except Exception:
            continue
    layer = Image.new("RGBA", (200, 50), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    if font:
        ld.text((4, 6), txt, font=font, fill=(120, 120, 145, 220))
    else:
        ld.text((4, 6), "~ whale ~", fill=(120, 120, 145, 220))
    layer = layer.rotate(random.uniform(-7, -2), expand=1, resample=Image.BICUBIC)
    img.paste(layer, (SIZE - 190, SIZE - 62), layer)



def parse_weather(thing):
    """从描述里认出天气：雨 / 雪 / 晴。这是整幅画的氛围，不是零件。"""
    t = thing or ""
    if any(k in t for k in ("下雨天", "下雨", "雨天", "雨点", "大雨", "小雨", "rain")):
        return "rain"
    if any(k in t for k in ("下雪", "雪天", "雪", "snow")):
        return "snow"
    if any(k in t for k in ("晴", "太阳天", "sunny")):
        return "sunny"
    return None


def paint_weather(d, kind):
    """在画面上叠加天气。雨/雪用短促的笔触，晴加个太阳。"""
    if kind == "rain":
        for _ in range(random.randint(26, 36)):
            x = random.randrange(20, SIZE - 20)
            y = random.randrange(30, SIZE - 140)
            ln = random.uniform(16, 30)
            stroke(d, [(x, y), (x - 5, y + ln)], (110, 160, 215), 3, 1.5, 1)
        # 地上的水坑
        for _ in range(random.randint(2, 4)):
            x = random.randrange(60, SIZE - 60)
            y = random.randrange(520, 600)
            stroke(d, circle_pts(x, y, random.uniform(16, 26), 10, 0.3),
                   (140, 180, 225), 3, 2, 1)
    elif kind == "snow":
        for _ in range(random.randint(30, 42)):
            x = random.randrange(20, SIZE - 20)
            y = random.randrange(30, SIZE - 120)
            r = random.uniform(3, 6)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(240, 248, 255))
            d.ellipse([x - r, y - r, x + r, y + r], outline=(200, 215, 235), width=1)
        stroke(d, [(20, 512), (SIZE - 20, 516)], (235, 245, 255), 14, 3, 1)
    elif kind == "sunny":
        p_sun(d, SIZE - 90, 92, 0.72)


def draw(thing="", seed=None):
    """画一张儿童画，返回 PIL Image。"""
    if seed is not None:
        random.seed(seed)
    img, d = _paper()

    weather = parse_weather(thing)

    # 地面：一条歪歪扭扭的草线
    ground = [(30, 520 + random.uniform(-8, 8)), (SIZE - 30, 524 + random.uniform(-8, 8))]
    ground_pts = []
    for i in range(11):
        x = 30 + (SIZE - 60) * i / 10
        ground_pts.append((x, 520 + random.uniform(-10, 10)))
    stroke(d, ground_pts, (120, 180, 110), 6, 3)
    for _ in range(7):
        x = random.randrange(40, SIZE - 40)
        stroke(d, [(x, 522), (x + random.uniform(-8, 8), 494 - random.uniform(0, 16))],
               (120, 180, 110), 4, 2, 1)

    # 装饰只放四角，避开主体（以前随机撒会压到太阳/心上）
    for _ in range(random.randint(1, 2)):
        x = random.choice([60, SIZE - 60])
        y = random.choice([60, 150])
        (p_star if random.random() < .6 else p_heart)(d, x, y, random.uniform(.35, .5))

    picked = parse_parts(thing)
    # 按层分配位置：天空在上、地面站在地平线上、水里在地平线下
    SKY = [(150, 145), (330, 110), (500, 155), (85, 255)]
    GROUND = [(175, 445), (330, 455), (485, 440), (100, 452)]
    WATER = [(180, 585), (335, 600), (490, 582), (100, 596)]
    ANY = [(215, 310), (430, 305), (325, 240), (545, 300)]
    slots = {"sky": list(SKY), "ground": list(GROUND),
             "water": list(WATER), "any": list(ANY)}
    order = {"sky": 0, "ground": 1, "water": 2, "any": 3}
    picked.sort(key=lambda p: order.get(PARTS[p[0]][2], 9))
    for i, (key, cnt) in enumerate(picked):
        fn, _kws, layer = PARTS[key]
        bx, by = slots[layer].pop(0) if slots[layer] else (320, 340)
        base_s = 0.62 if layer == "water" else 0.85
        if cnt <= 1:
            fn(d, bx + random.uniform(-10, 10), by + random.uniform(-10, 10),
               base_s * random.uniform(0.95, 1.06))
        else:
            # 多个：围成一小圈，画小一点
            s = 0.44 if cnt > 2 else 0.56
            r = 66 if cnt > 2 else 78
            for k in range(cnt):
                ang = 2 * math.pi * k / cnt + random.uniform(-.35, .35)
                fn(d, bx + r * math.cos(ang), by + r * math.sin(ang) * 0.8,
                   s * random.uniform(.9, 1.08))


    if weather:
        paint_weather(d, weather)
    _signature(img)
    img = img.filter(ImageFilter.SMOOTH)      # 一点点糊，更像蜡笔
    return img
