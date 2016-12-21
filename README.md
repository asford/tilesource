# Overview
This is a basic appengine-based app to handle server-side map tile overlay as a custom map source.

It is currently deployed under "http://tilesource-153122.appspot.com"

For example:
* <http://tilesource-153122.appspot.com/composite/im_fs-32_ct-128/>
* <http://tilesource-153122.appspot.com/composite/mb_fs-32/>

# Interface

The service provides a basic REST-ish interface:

* `/composite/<tilespec>/` - Renders a leaflet-based preview map.
* `/composite/<tilespec>/tile?z={z}&x={x}&y={y}` - Renders composite tiles at the given location.

Where `<tilespec>` is of the form [layer(-alpha?)]+ specifying, in order,
layers and optional alpha values for compositing. See layer sources in `tilesource.py`.

Z levels of 7-17 appear to work...
