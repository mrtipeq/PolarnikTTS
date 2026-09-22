"""Compose Chrome Web Store screenshots (1280x800) and the 440x280 promo tile from the raw
UI captures in docs/screenshots/.

    python scripts/make_store_screenshots.py

Output goes to docs/store/. Raw captures are placed on a dark gradient with a Polish caption
(the store listing is Polish). Tall options-page captures are split into two columns so the
text stays readable at 1280x800. Requires Pillow.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "screenshots"
OUT = ROOT / "docs" / "store"
W, H = 1280, 800
CAPTION_H = 96
PAD = 28
BG_TOP, BG_BOTTOM = (18, 22, 34), (40, 46, 66)
ACCENT = (214, 40, 40)  # PolarnikTTS red

FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
FONT_CANDIDATES_REG = [
    "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES if bold else FONT_CANDIDATES_REG:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def background(w: int = W, h: int = H) -> Image.Image:
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px_row = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = px_row
    return img


def caption(img: Image.Image, title: str, subtitle: str = "") -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([PAD, PAD + 6, PAD + 8, PAD + 6 + (58 if subtitle else 34)], fill=ACCENT)
    d.text((PAD + 22, PAD), title, font=font(30), fill=(245, 245, 250))
    if subtitle:
        d.text((PAD + 22, PAD + 40), subtitle, font=font(19, bold=False), fill=(190, 196, 214))


def shadowed(img: Image.Image, radius: int = 14) -> Image.Image:
    """Return the capture with rounded corners and a soft drop shadow (RGBA)."""
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    m = 24
    canvas = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([m, m + 6, m + w - 1, m + h + 5], radius=radius, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    canvas.alpha_composite(shadow)
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    canvas.alpha_composite(rgba, (m, m))
    return canvas


def fit(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    s = min(max_w / img.width, max_h / img.height, 1.0)
    if s < 1.0:
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    return img


def place_row(bg: Image.Image, parts: list[Image.Image], top: int) -> None:
    """Lay out captures side by side, centred, scaled to share the available width/height."""
    avail_h = H - top - PAD
    avail_w = W - 2 * PAD
    gap = 40
    scale = min(1.0, avail_h / max(p.height for p in parts),
                (avail_w - gap * (len(parts) - 1)) / sum(p.width for p in parts))
    scaled = [p.resize((round(p.width * scale), round(p.height * scale)), Image.LANCZOS) if scale < 1 else p
              for p in parts]
    total = sum(p.width for p in scaled) + gap * (len(scaled) - 1)
    x = (W - total) // 2
    row_h = max(p.height for p in scaled)
    for p in scaled:
        sh = shadowed(p)
        y = top + (0 if len(parts) > 1 and abs(parts[0].height - parts[-1].height) > 40 else (row_h - p.height) // 2)
        bg.alpha_composite(sh, (x - 24, y - 24))
        x += p.width + gap


def place_column(bg: Image.Image, parts: list[Image.Image], top: int) -> None:
    """Stack captures vertically, centred, scaled to share the available height/width."""
    avail_h = H - top - PAD
    avail_w = W - 2 * PAD
    gap = 32
    scale = min(1.0, avail_w / max(p.width for p in parts),
                (avail_h - gap * (len(parts) - 1)) / sum(p.height for p in parts))
    scaled = [p.resize((round(p.width * scale), round(p.height * scale)), Image.LANCZOS) if scale < 1 else p
              for p in parts]
    total = sum(p.height for p in scaled) + gap * (len(scaled) - 1)
    y = top + (avail_h - total) // 2
    for p in scaled:
        x = (W - p.width) // 2
        bg.alpha_composite(shadowed(p), (x - 24, y - 24))
        y += p.height + gap


def load(name: str) -> Image.Image:
    return Image.open(SRC / name).convert("RGB")


def strip_rows(img: Image.Image, y0: int, y1: int) -> Image.Image:
    """Remove horizontal band [y0, y1) - used to drop a transient error line from a capture."""
    top = img.crop((0, 0, img.width, y0))
    bottom = img.crop((0, y1, img.width, img.height))
    out = Image.new("RGB", (img.width, top.height + bottom.height))
    out.paste(top, (0, 0))
    out.paste(bottom, (0, top.height))
    return out


def split_columns(img: Image.Image, cut: int | None = None) -> list[Image.Image]:
    cut = cut or img.height // 2
    return [img.crop((0, 0, img.width, cut)), img.crop((0, cut, img.width, img.height))]


def compose(name: str, title: str, subtitle: str, parts: list[Image.Image], stack: bool = False) -> None:
    bg = background().convert("RGBA")
    caption(bg, title, subtitle)
    (place_column if stack else place_row)(bg, parts, CAPTION_H + PAD)
    OUT.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(OUT / name, optimize=True)
    print("wrote", OUT / name)


def promo_tile() -> None:
    tile = background(440, 280)
    icon = Image.open(ROOT / "extension" / "icons" / "icon128.png").convert("RGBA")
    tile = tile.convert("RGBA")
    tile.alpha_composite(icon, (28, 76))
    d = ImageDraw.Draw(tile)
    d.text((172, 84), "PolarnikTTS", font=font(34), fill=(245, 245, 250))
    d.text((174, 134), "Polski lektor do YouTube", font=font(20, bold=False), fill=(214, 220, 236))
    d.text((174, 162), "napisy → tłumaczenie → głos", font=font(17, bold=False), fill=(170, 178, 200))
    d.rectangle([172, 210, 410, 214], fill=ACCENT)
    tile.convert("RGB").save(OUT / "promo_440x280.png", optimize=True)
    print("wrote", OUT / "promo_440x280.png")


def main() -> None:
    panel, popup = load("01_player_panel.png"), load("02_popup.png")
    about = load("03_about.png")
    server_voice = load("04_options_server_voice.png")
    local = strip_rows(load("05_engines_local.png"), 768, 782)  # drop the old Chatterbox error line
    cloud = load("06_engines_cloud_translators.png")
    tail = load("07_translators_playback_transfer.png")

    compose("01_player.png", "Lektor w odtwarzaczu YouTube",
            "Przycisk P obok ustawień filmu, panel w stylu YouTube i popup ze statusem serwera",
            [panel, popup])
    compose("02_engines_local.png", "Silniki lokalne i chmurowe do wyboru",
            "Microsoft Edge (domyślny), Piper, Chatterbox i XTTS – instalacja jednym kliknięciem, tester głosu",
            split_columns(local, 554))
    compose("03_engines_cloud.png", "Głosy OpenAI, Gemini, ElevenLabs i tłumacze LLM",
            "Klucze API wpisujesz raz – wspólne dla tłumacza i głosu; Ollama/Bielik działa lokalnie bez klucza",
            split_columns(cloud, 588))
    compose("04_server_voice.png", "Serwer uruchamiasz i zatrzymujesz z rozszerzenia",
            "Lokalnie albo na innym komputerze w sieci; wybór silnika, głosu i tempa z odsłuchem",
            [server_voice])
    compose("05_playback_transfer.png", "Odtwarzanie, przenoszenie ustawień i informacje o programie",
            "Ściszanie oryginału, dopasowanie tempa, eksport/import na inny komputer",
            [about, tail.crop((0, 422, tail.width, tail.height))], stack=True)
    promo_tile()


if __name__ == "__main__":
    main()
