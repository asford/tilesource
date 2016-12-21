from io import BytesIO

import PIL.Image as Image
import PIL.ImageChops as ImageChops

import requests

sources = {
    "fs" : "http://caltopo.com/resource/imagery/tiles/sf/{z}/{x}/{y}.png",
    "mb" : "http://caltopo.com/resource/imagery/mapbuilder/cs-60-40-c21BB6100-h22-a21-r22-t22d-m21-p21/{z}/{x}/{y}.png",
    "ct" : "http://ctcontour.s3.amazonaws.com/feet/{z}/{x}/{y}.png",
    "im" : "http://khm1.googleapis.com/kh?v=709&hl=en-US&&x={x}&y={y}&z={z}"
}

def source_images(z, x, y):
    tile_images = {}
    for s, u in sources.items():
        r = requests.get(u.format(z=z, x=x, y=y))
        r.raise_for_status()
        assert r.headers["Content-Type"].startswith("image/")
        tile_images[s] = Image.open(BytesIO(r.content))
    return tile_images


def clip_image_alpha(image, max_alpha):
    image = image.convert("RGBA")
    red, green, blue, alpha = image.split()
    alpha = ImageChops.darker(alpha, Image.new("L", alpha.size, max_alpha))
    image.putalpha(alpha)
    
    return image

def overlay_image(base, *overlays):
    res = base.copy()

    for overlay in overlays:
        r, g, b, a = overlay.split()
        overlay = Image.merge("RGB", (r, g, b))
        mask = Image.merge("L", (a,))
        res.paste(overlay, (0, 0), mask)
    
    return res
