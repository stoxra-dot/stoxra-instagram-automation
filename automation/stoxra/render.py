from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def wrapped(draw, text, font, width):
    lines, line = [], ''
    for word in text.split():
        candidate = (line + ' ' + word).strip()
        if draw.textlength(candidate, font=font) > width:
            if not line or draw.textlength(word, font=font) > width:
                raise ValueError('Unbreakable text exceeds layout')
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + [line]


def render(post, brand, out, live=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    logo = Path(brand['logo'])
    if live and not logo.is_file():
        raise ValueError('Official logo asset required for live publishing')
    fonts = {k: ImageFont.truetype(brand['font'], size) for k, size in [('title', 78), ('body', 43), ('small', 24)]}
    files = []
    for i, slide in enumerate(post['slides']):
        im = Image.new('RGB', (1080, 1350), brand['colors']['white'])
        d = ImageDraw.Draw(im)
        d.rectangle((72, 220, 154, 229), fill=brand['colors']['orange'])
        if logo.is_file():
            mark = Image.open(logo).convert('RGBA')
            mark.thumbnail((270, 100))
            im.paste(mark, (72, 65), mark)
        else:
            d.text((72, 75), 'STOXRA / PREVIEW', font=fonts['small'], fill=brand['colors']['purple'])
        d.text((72, 175), post['topic'].upper(), font=fonts['small'], fill=brand['colors']['purple'])
        y = 290
        for key, font, spacing, limit in [('title', fonts['title'], 95, 700), ('body', fonts['body'], 62, 1120)]:
            lines = wrapped(d, slide[key], font, 924)
            if y + len(lines) * spacing > limit:
                raise ValueError('Text exceeds template; edit content')
            for line in lines:
                d.text((72, y), line, font=font, fill=brand['colors']['black'])
                y += spacing
            y += 75
        d.line((72, 1210, 1008, 1210), fill=brand['colors']['purple'], width=2)
        d.text((72, 1240), 'LEARN. PRACTISE. BUILD DISCIPLINE.', font=fonts['small'], fill=brand['colors']['black'])
        d.text((930, 1240), f'{i+1}/{len(post["slides"])}', font=fonts['small'], fill=brand['colors']['purple'])
        path = out / f'slide-{i+1}.jpg'
        im.save(path, 'JPEG', quality=94, optimize=True)
        files.append(path)
    return files
