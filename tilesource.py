from io import BytesIO

import PIL.Image as Image
import PIL.ImageChops as ImageChops

sources = {
    "fs" : "http://caltopo.com/resource/imagery/tiles/sf/{z}/{x}/{y}.png",
    "mb" : "http://caltopo.com/resource/imagery/mapbuilder/cs-60-40-c21BB6100-h22-a21-r22-t22d-m21-p21/{z}/{x}/{y}.png",
    "mbo" : "http://caltopo.com/resource/imagery/mapbuilder/clear-0-0-h22t-r23-t23/{z}/{x}/{y}.png",
    "ct" : "http://caltopo.com/resource/imagery/tiles/c/{z}/{x}/{y}.png",
    "im" : "http://khm1.googleapis.com/kh?v=709&hl=en-US&&x={x}&y={y}&z={z}"
}

def parse_tilespec(tilespec):
    res = []
    layers = tilespec.split()
    for lspec in tilespec.split("_"):
        lspec = lspec.split("-")
        if len(lspec) == 1:
            layer, alpha = lspec[0], 256
        else:
            assert len(lspec) == 2
            layer, alpha = lspec[0], int(lspec[1])
        
        assert layer in sources
        assert alpha >=0 and alpha<=256
            
        res.append((layer, alpha))
    return res

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
