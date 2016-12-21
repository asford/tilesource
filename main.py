import os
import io

import webapp2
import jinja2

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

import requests
import requests_toolbelt.adapters.appengine
requests_toolbelt.adapters.appengine.monkeypatch()

from tilesource import clip_image_alpha, overlay_image, source_images, parse_tilespec

class DirectRender(webapp2.RequestHandler):

    def get(self, tiletype, z, x, y):
        tile_url = sources[tiletype].format(z=z, x=x, y=y)
        r = requests.get(tile_url)
        r.raise_for_status()

        self.response.headers['Content-Type'] = r.headers["Content-Type"]
        self.response.write(r.content)

class CompositeTile(webapp2.RequestHandler):

    def get(self, tilespec):
        params = {
            p : self.request.get(p)
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

        self.response.headers["Content-Type"] = "image/png"
        self.response.write(b.getvalue())

class CompositeIndex(webapp2.RequestHandler):
    def get(self, tilespec):
        # Parse to assert that tilespec valid
        parse_tilespec(tilespec)
        template_values = dict(tilespec = tilespec)
        template = JINJA_ENVIRONMENT.get_template('composite/index.html')
        self.response.write(template.render(template_values))

app = webapp2.WSGIApplication([
    webapp2.Route(r'/direct/<tiletype:\w+>/<z:\d+>/<x:\d+>/<y:\d+>.png', handler=DirectRender),
    webapp2.Route(r'/composite/<tilespec:[^/]+>/tile', handler=CompositeTile),
    webapp2.Route(r'/composite/<tilespec:[^/]+>/', handler=CompositeIndex),
], debug=True)
