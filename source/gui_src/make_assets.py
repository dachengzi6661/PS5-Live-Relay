# -*- coding: utf-8 -*-
"""生成资源：应用图标 app.ico / app.png、打包期静态启动图 splash.png。

风格：极简风格 —— 纯白、单一品牌蓝（#0071E3）、连续曲率圆角、克制光影。
（v2 起界面不再使用产品配图，「首选 DNS」改为纯文字居中卡片。）
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
os.makedirs(OUT, exist_ok=True)

BLUE = (0, 113, 227)
BLUE_HI = (0, 119, 237)
WHITE = (255, 255, 255)
INK = (29, 29, 31)
MUTED = (110, 110, 115)
FAINT = (134, 134, 139)
HAIR = (210, 210, 215)


def font(size, bold=False):
    names = (["msyhbd.ttc", "seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"]
             if bold else ["msyh.ttc", "segoeui.ttf", "arial.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            continue
    return ImageFont.load_default()


def vertical_gradient(w, h, c1, c2):
    g = Image.new("RGBA", (w, h), c1 + (255,))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(h - 1, 1)
        c = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c + (255,))
    return g


def draw_mark(img, cx, cy, tile_w=62, tile_h=44, radius=12, scale=1.0):
    """品牌标记：蓝色渐变圆角方块 + 白色播放三角（自绘矢量感）。"""
    d = ImageDraw.Draw(img, "RGBA")
    tw, th = int(tile_w * scale), int(tile_h * scale)
    box = [int(cx - tw / 2), int(cy - th / 2), int(cx + tw / 2), int(cy + th / 2)]
    grad = vertical_gradient(tw, th, BLUE_HI, BLUE)
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, tw - 1, th - 1],
                                           int(radius * scale), fill=255)
    img.paste(grad, (box[0], box[1]), mask)
    tri = [(cx - 9 * scale, cy - 12 * scale),
           (cx - 9 * scale, cy + 12 * scale),
           (cx + 13 * scale, cy)]
    d.polygon(tri, fill=WHITE + (255,))


# ---------------- 应用图标 ----------------
S = 256
ico = Image.new("RGBA", (S, S), (0, 0, 0, 0))
# 白色连续曲率圆角底
bg = vertical_gradient(S, S, (255, 255, 255), (244, 244, 246))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], int(S * 0.235), fill=255)
ico.paste(bg, (0, 0), mask)
d = ImageDraw.Draw(ico, "RGBA")
d.rounded_rectangle([0, 0, S - 1, S - 1], int(S * 0.235),
                    outline=HAIR + (255,), width=2)
draw_mark(ico, S / 2, S / 2, 108, 76, 20)
ico_path = os.path.join(OUT, "app.ico")
ico.save(ico_path, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
ico.save(os.path.join(OUT, "app.png"))
print("saved", ico_path)

# ---------------- 构建期静态启动图 640x420 ----------------
W, H = 640, 420
splash = Image.new("RGBA", (W, H), WHITE + (255,))
sd = ImageDraw.Draw(splash, "RGBA")
# 顶部极淡蓝色氛围光，克制
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse([W // 2 - 190, -170, W // 2 + 190, 210],
                             fill=BLUE + (22,))
glow = glow.filter(ImageFilter.GaussianBlur(46))
splash.alpha_composite(glow)
sd.rounded_rectangle([1, 1, W - 2, H - 2], 20, outline=HAIR + (255,), width=2)
draw_mark(splash, W / 2, 146, 96, 68, 18)


def center_text(y, text, f, fill):
    d2 = ImageDraw.Draw(splash)
    bbox = d2.textbbox((0, 0), text, font=f)
    d2.text(((W - (bbox[2] - bbox[0])) / 2, y), text, font=f, fill=fill)


center_text(232, "PS5 直播推流助手", font(36, True), INK + (255,))
center_text(288, "无采集卡 · 无 Remote Play · 一键收流转推", font(17), MUTED + (255,))
# 细进度槽
sd.rounded_rectangle([100, 356, W - 100, 360], 2, fill=(232, 232, 236, 255))
sd.rounded_rectangle([100, 356, 300, 360], 2, fill=BLUE + (255,))
center_text(378, "正在加载程序，请稍候…", font(15), FAINT + (255,))
splash_path = os.path.join(OUT, "splash.png")
splash.convert("RGB").save(splash_path)
print("saved", splash_path)
