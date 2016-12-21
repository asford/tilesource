import webapp2

from google.appengine.api import images

import requests
import requests_toolbelt.adapters.appengine
requests_toolbelt.adapters.appengine.monkeypatch()


# url = "http://www.timeapi.org/pdt/in+two+hours"
# res = requests.get(url)
# res.raise_for_status()
tile_sources = {
    "fs" : "http://caltopo.com/resource/imagery/tiles/sf/{z}/{x}/{y}.png",
    "mb" : "http://caltopo.com/resource/imagery/mapbuilder/cs-60-40-c21BB6100-h22-a21-r22-t22d-m21-p21/{z}/{x}/{y}.png"
}

from io import BytesIO

import PIL.Image as Image
import PIL.ImageChops as ImageChops

def clip_image_alpha(image, max_alpha):
    image = image.convert("RGBA")
    red, green, blue, alpha = image.split()
    alpha = ImageChops.darker(alpha, Image.new("L", alpha.size, max_alpha))
    image.putalpha(alpha)
    
    return image

def overlay_image(base, overlay):
    res = base.copy()
    
    r, g, b, a = overlay.split()
    overlay = Image.merge("RGB", (r, g, b))
    mask = Image.merge("L", (a,))
    res.paste(overlay, (0, 0), mask)
    
    return res

class DirectRender(webapp2.RequestHandler):

    def get(self, tiletype, z, x, y):
        tile_url = tile_sources[tiletype].format(z=z, x=x, y=y)
        r = requests.get(tile_url)
        r.raise_for_status()

        self.response.headers['Content-Type'] = r.headers["Content-Type"]
        self.response.write(r.content)

class CompositeRender(webapp2.RequestHandler):

    def get(self, z, x, y):

        tile_images = {}
        for s, u in tile_sources.items():
            r = requests.get(u.format(z=z, x=x, y=y))
            r.raise_for_status()
            assert r.headers["Content-Type"] == 'image/png'
            tile_images[s] = Image.open(BytesIO(r.content))
            
        composite = overlay_image(
            tile_images["mb"],
            clip_image_alpha(tile_images["fs"], 64)
        )

        b = BytesIO()
        composite.save(b, format='png')

        self.response.headers["Content-Type"] = "image/png"
        self.response.write(b.getvalue())

app = webapp2.WSGIApplication([
    webapp2.Route(r'/direct/<tiletype:\w+>/<z:\d+>/<x:\d+>/<y:\d+>.png', handler=DirectRender),
    webapp2.Route(r'/composite/<z:\d+>/<x:\d+>/<y:\d+>.png', handler=CompositeRender),
], debug=True)
