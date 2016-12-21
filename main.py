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

from tilesource import clip_image_alpha, overlay_image, sources, source_images

class DirectRender(webapp2.RequestHandler):

    def get(self, tiletype, z, x, y):
        tile_url = sources[tiletype].format(z=z, x=x, y=y)
        r = requests.get(tile_url)
        r.raise_for_status()

        self.response.headers['Content-Type'] = r.headers["Content-Type"]
        self.response.write(r.content)

class CompositeRender(webapp2.RequestHandler):

    def get(self, z, x, y):

        tile_images = source_images(z=z, x=x, y=y)
            
        composite = overlay_image(
            tile_images["mb"],
            clip_image_alpha(tile_images["fs"], 64)
        )

        b = io.BytesIO()
        composite.save(b, format='png')

        self.response.headers["Content-Type"] = "image/png"
        self.response.write(b.getvalue())

class CompositeIndexRender(webapp2.RequestHandler):
    def get(self):
        template_values = {}
        template = JINJA_ENVIRONMENT.get_template('composite/index.html')
        self.response.write(template.render(template_values))

app = webapp2.WSGIApplication([
    webapp2.Route(r'/direct/<tiletype:\w+>/<z:\d+>/<x:\d+>/<y:\d+>.png', handler=DirectRender),
    webapp2.Route(r'/composite/<z:\d+>/<x:\d+>/<y:\d+>.png', handler=CompositeRender),
    webapp2.Route(r'/composite/', handler=CompositeIndexRender),
], debug=True)
