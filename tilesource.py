import io

import logging
import itertools

import numpy
from numpy_backports import isclose
import mercantile
mercantile.math = numpy
numpy.atan = numpy.arctan
from rolling_window import rolling_window

import PIL.Image as Image
import PIL.ImageDraw as ImageDraw
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

class Direct(object):
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

class SlopeShading(object):
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
            dse = rolling_window(elevation, (f/2, f/2), asteps=(f,f)).mean(axis=-1).mean(axis=-1)
            logging.info("dse: %s", list(dse.shape))
            dxr, dyr = tile_pixel_resolution(**tile) * f
            logging.info("res: %0.2f, %0.2f", dxr, dyr)
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

class ElevationRaster(object):
    name = "eraster"

    def create(self, **params):
        return ElevationRasterTile(**params)

class ElevationRasterTile(HasTraits):
    urltemplate = "https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw?access_token=%s" % mapbox_api_token
    a = traitlets.CInt(min=0, max=255, default_value=None, allow_none = True)

    def target_url(self, tile):
        return self.urltemplate.format(**tile)

    def resources_for(self, tile):
        return [self.urltemplate.format(**tile)]

    def render(self, tile, resources):
        elevation = ergb_to_elevation(Image.open(io.BytesIO(
            resources[self.target_url(tile)])))

        elevation -= elevation.min()

        i = Image.fromarray((elevation / elevation.max() * 255).astype("uint8")).convert("RGBA")

        if self.a:
            i = clip_image_alpha(i, self.a)
        return i

class ElevationArtifact(object):
    name = "eart"

    def create(self, **params):
        return ElevationArtifactTile(**params)

class ElevationArtifactTile(HasTraits):
    urltemplate = "https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw?access_token=%s" % mapbox_api_token
    a = traitlets.CInt(min=0, max=255, default_value=None, allow_none = True)
    window = traitlets.CInt(min=2, max=255, default_value=2)

    def target_url(self, tile):
        return self.urltemplate.format(**tile)

    def resources_for(self, tile):
        return [self.urltemplate.format(**tile)]

    def render(self, tile, resources):
        elevation = ergb_to_elevation(Image.open(io.BytesIO(
            resources[self.target_url(tile)])))

        # issame = isclose(elevation[:-1, :-1], elevation[1:, 1:])
        # res = numpy.zeros(elevation.shape, dtype="uint8")
        # rolling_window(res, (2, 2))[numpy.nonzero(issame)] = 255

        windows = rolling_window(elevation, window=(self.window, self.window))
        windows = windows.reshape(windows.shape[:-2] + (-1,))

        issame = numpy.all(isclose(windows[...,:1], windows), axis=-1)
        logging.info("eart z: %s frac: %.02f", tile["z"], numpy.count_nonzero(issame) / float(issame.size))

        res = numpy.zeros(elevation.shape + (4,), dtype="uint8")
        res[...,3][numpy.nonzero(issame)] = 255
        res[...,0] = 255
        # rolling_window(res, (self.window, self.window))[numpy.nonzero(issame)] = 255

        i = Image.fromarray(res).convert("RGBA")

        if self.a:
            i = clip_image_alpha(i, self.a)
        return i

import quantized_mesh_tile.global_geodetic

class QMTSlope(object):
    name = "qmtslope"

    def create(self, **params):
        return QMTSlopeTile(**params)

class QMTSlopeTile(HasTraits):
    urltemplate="https://assets.agi.com/stk-terrain/world/{z}/{x}/{y}.terrain?v=1.31376.0"
    geodetic = quantized_mesh_tile.global_geodetic.GlobalGeodetic(True)

    a = traitlets.CInt(min=0, max=255, default_value=None, allow_none = True)

    @classmethod
    def spanning_tile_coords(cls, xyzp):
        mb = mercantile.bounds(xyzp)
        z = xyzp.z - 1
        if mb.north >= 49.0 and z > 14:
            z = 14
        elif z > 15:
            z = 15
            
        spanning_tiles = set(
            cls.geodetic.LonLatToTile( lat, lon, z )
            for lat, lon in itertools.product(
                (mb.west, mb.east), (mb.north, mb.south)))

        return [(x, y, z) for x, y in spanning_tiles]

    @classmethod
    def load_qmt(cls, x, y, z, content):
        cls.geodetic.TileBounds(x, y, z)
        bounds = dict(zip(
            ("west", "south", "east", "north"),
            cls.geodetic.TileBounds(x, y, z)
        ))

        tile = quantized_mesh_tile.TerrainTile(**bounds)
        tile.fromStringIO(io.BytesIO(content))
        
        return tile

    @classmethod
    def vnorm(self, vectors):
        #No axis arg in numpy 1.6 norm

        return sum([vectors[...,i] ** 2 for i in (0, 1, 2)]) ** .5

    @classmethod
    def triangle_slope_angles(cls, qt_coords, qt_triangles):
        qt_meters = qt_coords.copy()
        qt_meters[...,0], qt_meters[...,1] = mercantile.xy(qt_coords[...,0], qt_coords[...,1] )

        tri_crosses = numpy.cross(
            qt_meters[qt_triangles[...,0]] - qt_meters[qt_triangles[...,1]],
            qt_meters[qt_triangles[...,0]] - qt_meters[qt_triangles[...,2]]
        )

        off_z_angle = numpy.rad2deg(
            numpy.arccos(tri_crosses[:,2] / cls.vnorm(tri_crosses))
        )
        
        return off_z_angle
        
    def resources_for(self, tile):
        tile = mercantile.Tile(**tile)
        return [
            self.urltemplate.format(x=x,y=y,z=z)
            for x, y, z in self.spanning_tile_coords(tile)
        ]

    def render(self, tile, data):
        tile = mercantile.Tile(**tile)
        qmts = [
            self.load_qmt(x, y, z, data[self.urltemplate.format(x=x,y=y,z=z)])
            for x, y, z in self.spanning_tile_coords(tile)
        ]
        
        qm_coords = []
        qm_triangles = []
        ind = 0
        for qmt in qmts:
            qm_coords.append(numpy.array(qmt.getVerticesCoordinates()))
            qm_triangles.append(numpy.array(qmt.indices) + ind)
            ind += len(qm_coords[-1])
            
        qm_coords = numpy.concatenate(qm_coords, axis=0)
        qm_triangles = numpy.concatenate(qm_triangles, axis=0).reshape((-1, 3))

        slope_angles = self.triangle_slope_angles(qm_coords, qm_triangles)

        mb = mercantile.bounds(tile)
        qm_xs = (qm_coords[...,0] - mb.west) / ((mb.east - mb.west) / 255)
        qm_ys = (qm_coords[...,1] - mb.north) / ((mb.south - mb.north) / 255)

        qm_colors = angle_to_rbga(slope_angles)
        qm_pix = numpy.empty((len(qm_coords), 2), dtype=int)
        qm_pix[...,0] = qm_xs + 128
        qm_pix[...,1] = qm_ys + 128

        rbuff = Image.new("RGBA", (256 * 2, 256 * 2))
        rdraw = ImageDraw.ImageDraw(rbuff)

        for ti in range(len(qm_triangles)):
            rdraw.polygon(
                map(tuple, qm_pix[qm_triangles[ti]]),
                fill=tuple(qm_colors[ti])
            )

        res = rbuff.crop((128, 128, 255+128, 255+128))

        if self.a:
            res = clip_image_alpha(res, self.a)

        return res

sources = [
    Direct("topo", "http://caltopo.s3.amazonaws.com/topo/{z}/{x}/{y}.png"),
    Direct("fs", "http://caltopo.com/resource/imagery/tiles/sf/{z}/{x}/{y}.png"),
    Direct("mb", "http://caltopo.com/resource/imagery/mapbuilder/cs-60-40-c21BB6100-h22-a21-r22-t22d-m21-p21/{z}/{x}/{y}.png"),
    Direct("mbo", "http://caltopo.com/resource/imagery/mapbuilder/clear-0-0-h22t-r23-t23/{z}/{x}/{y}.png"),
    Direct("ct", "http://caltopo.com/resource/imagery/tiles/c/{z}/{x}/{y}.png"),
    Direct("im", "http://khm1.googleapis.com/kh?v=709&hl=en-US&&x={x}&y={y}&z={z}"),
    Direct("ergb", "https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw?access_token=%s" % mapbox_api_token),
    Direct("mbct", "https://api.mapbox.com/styles/v1/asford/cix2rmi46003s2poh02m5cipm/tiles/256/{z}/{x}/{y}?access_token=%s" % mapbox_api_token),
    SlopeShading(),
    ElevationRaster(),
    ElevationArtifact(),
    QMTSlope(),
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
