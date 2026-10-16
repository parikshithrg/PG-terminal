from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tmp" / "booklets"
OUT = SRC / "contact-sheets"
OUT.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)

for folder in sorted(SRC.glob("docx-*")):
    pages = sorted(folder.glob("page-*.png"))
    thumbs = []
    for index, page in enumerate(pages, 1):
        image = Image.open(page).convert("RGB")
        image.thumbnail((360, 510))
        tile = Image.new("RGB", (390, 560), "#DDE3EA")
        tile.paste(image, ((390 - image.width) // 2, 20))
        ImageDraw.Draw(tile).text((195, 535), f"PAGE {index}", font=font, fill="#142033", anchor="mm")
        thumbs.append(tile)
    sheet = Image.new("RGB", (780, 2240), "#BFC8D4")
    for i, tile in enumerate(thumbs):
        sheet.paste(tile, ((i % 2) * 390, (i // 2) * 560))
    sheet.save(OUT / f"{folder.name}.jpg", quality=90)
