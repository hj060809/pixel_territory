"""웹 앱 아이콘 (홈 화면에 추가할 때): tools/icon_art.png (64×64 도트 그림)를 정수 배로 키워 web/public/에.

그림: 섬 위에 누워 잠든 서리 드래곤(용기사)이 화염탑을 몸으로 감싼 장면. 게임 렌더러(web/src/game/stack.ts)로
잠든 용기사 모델(models.ts dragonRider frame 3)과 화염탑 모델을 한 장면에 놓고 한 카메라로 그린 뒤, 매끈한 바다·섬 배경에 얹었다.
그림이 가운데에 모여 있어 안드로이드가 제 모양(동그라미 등)으로 깎아도 잘리지 않으므로 maskable에도 같은 그림을 쓴다.

- icon-192.png (3배), icon-512.png (8배), icon-maskable-512.png (8배): 정수 배라 도트가 또렷하다

python tools/make_icons.py
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
art = Image.open(ROOT / 'tools' / 'icon_art.png').convert('RGB')
assert art.size == (64, 64), art.size
for name, size in (('icon-192.png', 192), ('icon-512.png', 512), ('icon-maskable-512.png', 512)):
    art.resize((size, size), Image.NEAREST).save(ROOT / 'web' / 'public' / name)
    print(f'web/public/{name}')
