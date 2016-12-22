import os
import io

from flask import Flask
app = Flask(__name__)

from flask import abort, redirect, url_for, render_template, Response, request

import requests
import requests_toolbelt.adapters.appengine
requests_toolbelt.adapters.appengine.monkeypatch()

from tilesource import clip_image_alpha, overlay_image, source_images, parse_tilespec

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
    params = {
        p : request.args.get(p)
        for p in ("z", "x", "y")
    }

    tilespec = parse_tilespec(tilespec)

    tile_images = source_images(keys = [l for l, a in tilespec], **params)
        
    composite = overlay_image(*[
        clip_image_alpha(tile_images[layer], alpha)
        for layer, alpha in tilespec
    ])

    b = io.BytesIO()
    composite.save(b, format='png')

    return Response(b.getvalue(), content_type='img/png')
