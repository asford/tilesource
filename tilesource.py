import io

import numpy
import mercantile
from rolling_window import rolling_window

import PIL.Image as Image
import PIL.ImageChops as ImageChops

mapbox_api_token = "pk.eyJ1IjoiYXNmb3JkIiwiYSI6ImNpeDJiMWZpMjAwZ3kyb2xkdW1xa2MxYjQifQ.zbKaLisJVw917FJmO3T1fw"

import traitlets

class HasTraits(traitlets.HasTraits):
    #Override TypeError-swallowing in traitlets 4.2...
    def __init__(self, *args, **kwargs):
        # Allow trait values to be set using keyword arguments.
        # We need to use setattr for this to trigger validation and
        # notifications.
        super_args = args
        super_kwargs = {}
        with self.hold_trait_notifications():
            for key, value in kwargs.items():
                if self.has_trait(key):
                    setattr(self, key, value)
                else:
                    # passthrough args that don't set traits to super
                    super_kwargs[key] = value

        super(traitlets.HasTraits, self).__init__(*super_args, **super_kwargs)

class DirectTileFactory(object):
    def __init__(self, name, urltemplate):
        self.name = name
        self.urltemplate = urltemplate

    def create(self, **params):
        return DirectTile( urltemplate = self.urltemplate, **params )
    
class DirectTile(HasTraits):
    urltemplate = traitlets.Bytes()
    a = traitlets.CInt(min=0, max=255, default_value=None, allow_none=True)

    def target_url(self, tile):
        return self.urltemplate.format(**tile)

    def resources_for(self, tile):
        return [self.urltemplate.format(**tile)]

    def render(self, tile, resources):
        i = Image.open(io.BytesIO(resources[self.target_url(tile)])).convert("RGBA")

        if self.a:
            i = clip_image_alpha(i, self.a)
        return i

class SlopeShadingFactory(object):
    name = "slope"

    def create(self, **params):
        return SlopeShadingTile(**params)

class SlopeShadingTile(HasTraits):
    urltemplate = "https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw?access_token=%s" % mapbox_api_token
    a = traitlets.CInt(min=0, max=255, default_value=None, allow_none = True)
    resample = traitlets.CInt(min=2, default_value = None, allow_none=True)

    def target_url(self, tile):
        return self.urltemplate.format(**tile)

    def resources_for(self, tile):
        return [self.urltemplate.format(**tile)]

    def render(self, tile, resources):
        elevation = ergb_to_elevation(Image.open(io.BytesIO(
            resources[self.target_url(tile)])))

        if self.resample:
            f = self.resample
            dse = elevation[f/2::f, f/2::f]
            dxr, dyr = tile_pixel_resolution(**tile) * f
            dslope = slope_angle(dse, xr=dxr, yr=dyr)
            slope = (
                numpy.repeat(axis=0, repeats=f, a=
                numpy.repeat(axis=1, repeats=f, a=
                    dslope)))
        else:
            xr, yr = tile_pixel_resolution(**tile)
            slope = slope_angle(elevation, xr=xr, yr=yr)

        i = Image.fromarray(angle_to_rbga(slope))

        if self.a:
            i = clip_image_alpha(i, self.a)
        return i

sources = [
    DirectTileFactory("topo", "http://caltopo.s3.amazonaws.com/topo/{z}/{x}/{y}.png"),
    DirectTileFactory("fs", "http://caltopo.com/resource/imagery/tiles/sf/{z}/{x}/{y}.png"),
    DirectTileFactory("mb", "http://caltopo.com/resource/imagery/mapbuilder/cs-60-40-c21BB6100-h22-a21-r22-t22d-m21-p21/{z}/{x}/{y}.png"),
    DirectTileFactory("mbo", "http://caltopo.com/resource/imagery/mapbuilder/clear-0-0-h22t-r23-t23/{z}/{x}/{y}.png"),
    DirectTileFactory("ct", "http://caltopo.com/resource/imagery/tiles/c/{z}/{x}/{y}.png"),
    DirectTileFactory("im", "http://khm1.googleapis.com/kh?v=709&hl=en-US&&x={x}&y={y}&z={z}"),
    DirectTileFactory("ergb", "https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw?access_token=%s" % mapbox_api_token),
    DirectTileFactory("mbct", "https://api.mapbox.com/styles/v1/asford/cix2rmi46003s2poh02m5cipm/tiles/256/{z}/{x}/{y}?access_token=%s" % mapbox_api_token),
    SlopeShadingFactory(),
]

_sources_by_name = { s.name : s for s in sources }

def parse_tilespec(tilespec):
    res = []
    layers = tilespec.split()
    for slargs in tilespec.split("~"):
        largs = slargs.split("_")
        if not largs[0] in _sources_by_name:
            raise ValueError("Invalid layer args: %r" % slargs)
        if not len(largs) % 2 == 1:
            raise ValueError("Invalid layer args: %r" % slargs)

        params = {}
        for i in range(1, len(largs), 2):
            params[largs[i]] = largs[i+1]

        res.append(_sources_by_name[largs[0]].create( **params ))

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
        a=( nbr_rise / nbr_run ).reshape(elevation.shape + (-1,)))

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
