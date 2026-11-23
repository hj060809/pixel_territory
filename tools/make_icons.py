"""웹 앱 아이콘 (홈 화면에 추가할 때): 로비 배경의 마을(망루·거점·해안·바다) 그림(tools/icon_art.png, 512×512)에
로비 제목과 같은 도트 글씨 'Pixel Territory'를 얹어 web/public/에.

- icon-192.png, icon-512.png: 글씨는 아래 왼쪽 (가장자리 10% 띄움, 둥근 네모·동그라미로 깎아도 잘리지 않게), 아래쪽 바다를 살짝 어둡게
- icon-maskable-512.png: 안드로이드가 제 모양으로 깎는 아이콘 (가운데 약 2/3만 보인다). 글씨를 넣을 자리가 없어 그림만
  (안드로이드 홈 화면은 아이콘 아래에 앱 이름을 따로 띄운다). 더 넓게 자른 그림(tools/icon_art_maskable.png)이라 깎인 뒤 보이는
  부분이 위 아이콘과 같은 장면이다.

icon_art.png는 로비 화면에서 UI를 숨기고 마을 둘레를 잘라 만든 그림이다 (지형 그림이 바뀌면 다시 잘라 넣는다).
글씨: web/src/menu/widgets.ts pixelTitle과 같은 방법 (맑은 고딕 굵게 20px를 0/1로, 짙은 테두리, 정수 배). 윈도우 글꼴을 쓴다.

python tools/make_icons.py
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'tools' / 'icon_art.png'
ART_MASKABLE = ROOT / 'tools' / 'icon_art_maskable.png'
FONT = ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf', 20)


def pixel_title(text: str, scale: int, col=(255, 226, 150)) -> Image.Image:
    w, h = int(FONT.getlength(text)) + 2, 28
    m = Image.new('L', (w, h), 0)
    ImageDraw.Draw(m).text((0, 3), text, font=FONT, fill=255)
    ys, xs = np.nonzero(np.array(m) >= 128)
    img = np.zeros((h + 3, w + 3, 4), np.uint8)
    for ox, oy in [(0, 1), (2, 1), (1, 0), (1, 2), (2, 3), (3, 2), (3, 3)]:   # 짙은 테두리 (로비 제목과 같다)
        img[ys + oy, xs + ox] = (30, 18, 10, 255)
    img[ys + 1, xs + 1] = (*col, 255)
    yy, xx = np.nonzero(img[..., 3])
    img = img[yy.min():yy.max() + 1, xx.min():xx.max() + 1]
    return Image.fromarray(img).resize((img.shape[1] * scale, img.shape[0] * scale), Image.NEAREST)


def compose(scale: int, x0: int, bottom: int) -> Image.Image:
    im = Image.open(ART).convert('RGBA').resize((512, 512), Image.LANCZOS)
    shade = np.zeros((512, 512, 4), np.uint8)                       # 글씨 뒤 바다를 아래로 갈수록 살짝 어둡게
    shade[..., :3] = (6, 10, 22)
    for y in range(300, 512):
        shade[y, :, 3] = int(110 * ((y - 300) / 212) ** 1.4)
    im.alpha_composite(Image.fromarray(shade))
    a, b = pixel_title('Pixel', scale), pixel_title('Territory', scale)
    gap = scale
    y0 = 512 - bottom - a.height - gap - b.height
    im.alpha_composite(a, (x0, y0))
    im.alpha_composite(b, (x0, y0 + a.height + gap))
    return im.convert('RGB')


main = compose(4, 52, 56)
for size in (192, 512):
    main.resize((size, size), Image.LANCZOS).save(ROOT / f'web/public/icon-{size}.png')
    print(f'web/public/icon-{size}.png')
Image.open(ART_MASKABLE).convert('RGB').resize((512, 512), Image.LANCZOS).save(ROOT / 'web/public/icon-maskable-512.png')
print('web/public/icon-maskable-512.png')
