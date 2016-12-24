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

@app.route("/")
@app.route("/composite/")
def composite_redirect():
    return redirect(url_for("composite", tilespec="topo~slope_a_64"))

@app.route("/composite/<tilespec>/")
def composite(tilespec):
    # Parse to assert that tilespec valid
    parse_tilespec(tilespec)

    return render_template('composite/index.html', tilespec=tilespec, view=request.args.get("view"))

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
    tile = {
        p : int(request.args.get(p))
        for p in ("z", "x", "y")
    }

    tilelayers = parse_tilespec(tilespec)
    app.logger.info(
        "tilelayers: %r", [
            (l.__class__.__name__, { t : getattr(l, t) for t in l.trait_names() })
            for l in tilelayers
        ])

    tile_data = retrieve_urls(
        reduce(set.union, [set(l.resources_for(tile)) for l in tilelayers]))
    
    composite = overlay_image(*[l.render(tile, tile_data) for l in tilelayers])

    b = io.BytesIO()
    composite.save(b, format="png")

    return Response(b.getvalue(), content_type='image/png')

@app.errorhandler(urlfetch_errors.DeadlineExceededError)
def deadline_exceeded_handler(ex):
    response = Response("External fetch timed out.", status=503)
    response.retry_after = 6
    return response
