import os
import io


from flask import Flask
from utility import maybe_debug_app
app = maybe_debug_app(Flask(__name__))

from flask import abort, redirect, url_for, render_template, Response, request

from flask_cachecontrol import FlaskCacheControl, cache
flask_cache_control = FlaskCacheControl()
flask_cache_control.init_app(app)

import numpy

import PIL.Image as Image

from tilesource import clip_image_alpha, overlay_image, sources, parse_tilespec
import tilesource

from google.appengine.api import urlfetch, urlfetch_errors

from utility import cache_many, cache_result
from werkzeug.contrib.cache import MemcachedCache

@cache_many(cache=MemcachedCache(default_timeout=0))
def retrieve(*urls):
    app.logger.info("retrieve: %s", urls)
    rpcs = {}
    for u in set(urls):
        rpc = urlfetch.create_rpc(15)
        urlfetch.make_fetch_call(rpc, u)
        rpcs[u] = rpc

    results = {}
    for u, rpc in rpcs.items():
        try:
            result = rpc.get_result()
            if result.status_code == 200:
                results[u] = result.content
            else:
                raise ValueError("Status code: %i" % result.status_code)
        except Exception:
            app.logger.exception("Error retrieving url: %r" % u)
            raise

    return [results[u] for u in urls]

def retrieve_urls(urls):
    return dict(zip(urls, retrieve(*urls)))

@cache_result(cache=MemcachedCache(default_timeout=0))
def render_tile(tilespec, z, x, y):
    app.logger.info("render_tile: %s", locals())
    layer_sources = {
        l : tilesource.layer_source(l).format(z=z, x=x, y=y)
        for l, a in tilespec 
    }

    tile_data = retrieve_urls(set(layer_sources.values()))
    tile_images = { l : Image.open(io.BytesIO(d)) for l, d in tile_data.items() }

    layer_images = {}

    for l in layer_sources:
        if not l.startswith("customslope"):
            layer_images[l] = tile_images[layer_sources[l]]
            continue

        app.logger.info("rendering customslope")
        elevation = tilesource.ergb_to_elevation( tile_images[layer_sources[l]] )

        ds_factor = l.lstrip("customslope")
        if not ds_factor:
            xr, yr = tilesource.tile_pixel_resolution(x=x, y=y, z=z)

            slope = tilesource.slope_angle(elevation, xr=xr, yr=yr)
            
        else:
            f = int(ds_factor)
            assert f >= 2
            dse = elevation[f/2::f, f/2::f]
            dxr, dyr = tilesource.tile_pixel_resolution(x=x, y=y, z=z) * f
            dslope = tilesource.slope_angle(dse, xr=dxr, yr=dyr)
            slope = (
                numpy.repeat(axis=0, repeats=f, a=
                numpy.repeat(axis=1, repeats=f, a=
                    dslope)))


        layer_images[l] = Image.fromarray(tilesource.angle_to_rbga(slope))


    composite = overlay_image(*[
        clip_image_alpha(layer_images[layer], alpha)
        for layer, alpha in tilespec
    ])

    b = io.BytesIO()
    composite.save(b, format='png')
    return b.getvalue()

@app.route("/")
@app.route("/composite/")
def composite_redirect():
    return redirect(url_for("composite", tilespec="topo_customslope-64"))

@app.route("/composite/<tilespec>/")
def composite(tilespec):
    # Parse to assert that tilespec valid
    parse_tilespec(tilespec)
    return render_template('composite/index.html', tilespec=tilespec)

@app.route("/composite/<tilespec>/tilejson")
def composite_tilejson(tilespec):
    parse_tilespec(tilespec)

    return Response(
        render_template("composite/tilejson.json", tilespec=tilespec),
        content_type='application/json; charset=utf-8'
    )

@app.route("/composite/<tilespec>/tile")
@cache(max_age=60*60 if not app.debug else 0, public=True)
def composite_tile(tilespec):
    tile_params = {
        p : int(request.args.get(p))
        for p in ("z", "x", "y")
    }

    tilespec = parse_tilespec(tilespec)

    tile = render_tile(tilespec=tilespec, **tile_params)

    return Response(tile, content_type='image/png')

@app.errorhandler(urlfetch_errors.DeadlineExceededError)
def deadline_exceeded_handler(ex):
    response = Response("External fetch timed out.", status=503)
    response.retry_after = 6
    return response
