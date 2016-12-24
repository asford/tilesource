from io import BytesIO

import numpy
import mercantile
from rolling_window import rolling_window

import PIL.Image as Image
import PIL.ImageChops as ImageChops

mapbox_api_token = "pk.eyJ1IjoiYXNmb3JkIiwiYSI6ImNpeDJiMWZpMjAwZ3kyb2xkdW1xa2MxYjQifQ.zbKaLisJVw917FJmO3T1fw"


sources = {
    "topo" : "http://caltopo.s3.amazonaws.com/topo/{z}/{x}/{y}.png",
    "fs" : "http://caltopo.com/resource/imagery/tiles/sf/{z}/{x}/{y}.png",
    "mb" : "http://caltopo.com/resource/imagery/mapbuilder/cs-60-40-c21BB6100-h22-a21-r22-t22d-m21-p21/{z}/{x}/{y}.png",
    "mbo" : "http://caltopo.com/resource/imagery/mapbuilder/clear-0-0-h22t-r23-t23/{z}/{x}/{y}.png",
    "ct" : "http://caltopo.com/resource/imagery/tiles/c/{z}/{x}/{y}.png",
    "im" : "http://khm1.googleapis.com/kh?v=709&hl=en-US&&x={x}&y={y}&z={z}",
    "ergb" : "https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw?access_token=%s" % mapbox_api_token,
    "mbct" : "https://api.mapbox.com/styles/v1/asford/cix2rmi46003s2poh02m5cipm/tiles/256/{z}/{x}/{y}?access_token=%s" % mapbox_api_token
    }

def is_valid_layer(layer):
    return layer in sources or layer.startswith("customslope")

def layer_source(layer):
    if layer in sources:
        return sources[layer]
    elif layer.startswith("customslope"):
        return sources["ergb"]
    else:
        return None

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
        
        assert is_valid_layer(layer)
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

### Elevation model support

def ergb_to_elevation(ergb, out=None):
    ergb = numpy.array(ergb)
    if out is None:
        out = numpy.empty(ergb.shape[:2])
    out[:] = -10000
    out += ergb[...,0] * (256 ** 2) * .1
    out += ergb[...,1] * (256) * .1
    out += ergb[...,2] * .1
    
    return out

### Slope angle calculation support
def tile_pixel_resolution(x, y, z):
    tile_bounds = mercantile.bounds((x,y,z))
    return numpy.abs(
        numpy.array(mercantile.xy(tile_bounds.west, tile_bounds.north)) -
        numpy.array(mercantile.xy(tile_bounds.east, tile_bounds.south))) / 256

#numpy.pad present in numpy 1.6.1
def edgepad(a):
    assert a.ndim == 2

    result = numpy.empty(numpy.array(a.shape) + 2, a.dtype)
    result[1:-1, 1:-1] = a
    result[0,:] = result[1,:]
    result[-1,:] = result[-2,:]

    result[:,0] = result[:,1]
    result[:,-1] = result[:,-2]

    return result

def slope_angle(elevation, xr, yr):

    nbr_run = numpy.zeros((3, 3))
    nbr_run[1, [0, 2]] = xr
    nbr_run[[0, 2], 1] = yr
    nbr_run[[0,0,2,2],[0,2,0,2]] = (xr ** 2 + yr ** 2) ** .5

    nbr_rise = (
        rolling_window(edgepad(elevation), window=(3, 3)) -
        elevation.reshape(elevation.shape + (1, 1))
    )

    maximum_slope = numpy.nanmax( axis=-1,
        a=numpy.abs( nbr_rise / nbr_run ).reshape(elevation.shape + (-1,)))

    return numpy.rad2deg(numpy.arctan( maximum_slope ))

### Fixed shading support

fixed_shading_colors = {
    'none': (255, 255, 255, 0),
    'yellow': (245, 255, 10, 255),
    'light_orange': (250, 183, 0, 255),
    'orange': (254, 121, 0, 255),
    'red': (255, 0, 0, 255),
    'purple': (135, 0, 225, 255),
    'blue': (0, 0, 255, 255),
    'black': (0, 0, 0, 255),
}

fixed_shading_thresholds = [
    (27.0, "none"),
    (30.0, "yellow"),
    (32.0, "light_orange"),
    (35.0, "orange"),
    (46.0, "red"),
    (51.0, "purple"),
    (60.0, "blue"),
    (90.0, "black"),
]

fs_levels = numpy.array([l for l, c in fixed_shading_thresholds], dtype=float)
fs_colors = numpy.array([fixed_shading_colors[c] for l, c in fixed_shading_thresholds]).astype("uint8")

def angle_to_rbga(angles):
    return fs_colors[numpy.searchsorted(fs_levels, numpy.clip(angles, 0, 90))]
