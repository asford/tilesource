import os
import io

from flask import Flask
from utility import maybe_debug_app
app = maybe_debug_app(Flask(__name__))

from flask import abort, redirect, url_for, render_template, Response, request

import PIL.Image as Image

from tilesource import clip_image_alpha, overlay_image, sources, parse_tilespec

from google.appengine.api import urlfetch

from utility import cache_many, cache_result
from werkzeug.contrib.cache import MemcachedCache

@cache_many(cache=MemcachedCache(default_timeout=0))
def retrieve(*urls):
    app.logger.info("retrieve: %s", urls)
    rpcs = {}
    for u in set(urls):
        rpc = urlfetch.create_rpc(10)
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

@cache_result(cache=MemcachedCache(default_timeout=0))
def render_tile(tilespec, z, x, y):
    layers = set(layer for layer, alpha in tilespec)

    tile_data = dict(zip(
        layers,
        retrieve(*
            [sources[layer].format(z=z, x=x, y=y) for layer in layers])
    ))

    tile_images = { l : Image.open(io.BytesIO(d)) for l, d in tile_data.items() }

    composite = overlay_image(*[
        clip_image_alpha(tile_images[layer], alpha)
        for layer, alpha in tilespec
    ])

    b = io.BytesIO()
    composite.save(b, format='png')
    return b.getvalue()

@app.route("/")
@app.route("/composite/")
def composite_redirect():
    return redirect(url_for("composite", tilespec="im_fs-32_ct-64"))

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
def composite_tile(tilespec):
    tile_params = {
        p : request.args.get(p)
        for p in ("z", "x", "y")
    }

    tilespec = parse_tilespec(tilespec)

    tile = render_tile(tilespec=tilespec, **tile_params)

    return Response(tile, content_type='image/png')
