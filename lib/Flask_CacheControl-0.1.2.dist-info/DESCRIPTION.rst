Flask-CacheControl
------------------

A light-weight library to conveniently set Cache-Control
headers on the response. Decorate view functions with
cache_for, cache, or dont_cache decorators. Makes use of
Flask response.cache_control.

This extension does not provide any caching of its own. Its sole
purpose is to set Cache-Control and related HTTP headers on the
response, so that clients, intermediary proxies or reverse proxies
in your jurisdiction which evaluate Cache-Control headers, such as
Varnish Cache, do the caching for you.


