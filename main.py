import os
import io

import logging

from flask import Flask
from utility import maybe_debug_app
app = maybe_debug_app(Flask(__name__))

from flask import abort, redirect, url_for, render_template, Response, request

from flask_cachecontrol import FlaskCacheControl, cache
flask_cache_control = FlaskCacheControl()
flask_cache_control.init_app(app)

import httplib
import urllib
import urlparse

import numpy

from tilesource import clip_image_alpha, overlay_image, sources, parse_tilespec
import tilesource

import requests
import requests_toolbelt.adapters.appengine
requests_toolbelt.adapters.appengine.monkeypatch()

from google.appengine.api import images
import PIL.Image

from google.appengine.ext import ndb

import cloudstorage as gcs
from google.appengine.api import app_identity
from google.appengine.api import urlfetch, urlfetch_errors
bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
logging.info("gcs bucket_name: %r", bucket_name)

@ndb.tasklet
def upload_object_async(storage_api, path, data, content_type, gcs_headers=None):
    """
    Args:
      api: A StorageApi instance.
      path: Quoted/escaped path to the object, e.g. /mybucket/myfile
      data: object bytes
      content_type: Optional content-type; Default value is
        delegate to Google Cloud Storage.
      gcs_headers: additional gs headers as a str->str dict, e.g
        {'x-goog-acl': 'private', 'x-goog-meta-foo': 'foo'}.
    """
    headers = {'x-goog-resumable': 'start'}
    headers['content-type'] = content_type
    if gcs_headers:
      headers.update(gcs_headers)

    status, resp_headers, content = yield storage_api.post_object_async(path, headers=headers)
    gcs.errors.check_status(
            status, [201], path, headers, resp_headers, body=content)
    loc = resp_headers.get('location')
    if not loc:
      raise IOError('No location header found in 201 response')
    parsed = urlparse.urlparse(loc)
    path_with_token = '%s?%s' % (path, parsed.query)

    headers = {
        'content-range': "bytes 0-%d/%d" % (len(data) - 1, len(data))
    }

    status, response_headers, content = yield storage_api.put_object_async(
        path_with_token, payload=data, headers=headers)
    gcs.errors.check_status(status, [200], path, headers,
                        response_headers, content,
                        {'upload_path': path_with_token})

@ndb.tasklet
def get_tile(tile_layer, tile, return_pil = False ):
    tile_key = ( "/%s/tile/%s/%s/%s/%s" % (
        bucket_name, tile_layer.storage_key, tile["z"], tile["x"], tile["y"]))
    object_key = urllib.quote(tile_key)

    storage_api = gcs.storage_api._get_storage_api(None)
    status, header, content = \
        yield storage_api.head_object_async(object_key)
    gcs.errors.check_status(status, [200, httplib.NOT_FOUND], object_key)

    if status == 200:
        logging.debug("found: %s", object_key)
    else:
        logging.debug("rendering: %s", object_key)
        tile_img = yield tile_layer.render_async(tile)

        tileb = io.BytesIO()
        tile_img.convert("RGBA").save(tileb, "png")
        yield upload_object_async(
            storage_api, object_key, tileb.getvalue(), "image/png")

    if return_pil:
        logging.info("loading: %s" % object_key)
        status, resp_headers, content = \
            yield storage_api.get_object_async(object_key)
        gcs.errors.check_status(status, [200], object_key)
        raise ndb.Return(PIL.Image.open(io.BytesIO(content)).convert("RGBA"))
    else:
        logging.info("refing: %s" % tile_key)
        raise ndb.Return(images.Image(filename="/gs" + tile_key))

@app.route("/")
@app.route("/composite/")
def composite_redirect():
    return redirect(url_for("composite", tilespec="gosat~qmtslope_opacity_.25~mbcnt_opacity_.5"))

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

    tile_layers = parse_tilespec(tilespec)

    app.logger.info(
        "tile_layers: %r", [
            (l.__class__.__name__, { t : getattr(l, t) for t in l.trait_names() })
            for l in tile_layers
        ])

    tile_images = [
        get_tile(tile_layer, tile, return_pil = app.debug)
        for tile_layer in tile_layers
    ]
    tile_images = [ i.get_result() for i in tile_images ]

    if not app.debug:
        composite = images.composite([
                (i, 0, 0, l.opacity, images.TOP_LEFT)
                for i, l in zip(tile_images, tile_layers)
            ],
            width=256, height=256, output_encoding=images.PNG
        )
    else:
        b = io.BytesIO()
        overlay_image(*[
            clip_image_alpha(i, int(255) * l.opacity)
            for i, l in zip(tile_images, tile_layers)
        ]).save(b, "png")
        composite = b.getvalue()
    
    return Response(composite, content_type='image/png')

@app.errorhandler(urlfetch_errors.DeadlineExceededError)
def deadline_exceeded_handler(ex):
    response = Response("External fetch timed out.", status=503)
    response.retry_after = 6
    return response
