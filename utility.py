import logging

import os
import sys
from werkzeug import DebuggedApplication

import decorator

class VirtualModule(object):
   def __init__(self,name):
      sys.modules[name]=self
   def __getattr__(self,name):
      return globals()[name]

def maybe_debug_app(app):
    server_software = os.getenv('SERVER_SOFTWARE', '')
    logging.info("maybe_debug_app SERVER_SOFTWARE: %s", server_software)

    if server_software.startswith('Dev'):
        logging.warning("Initializing werkzeung debugging.")

        VirtualModule("__main__")

        app.debug = True
        app.wsgi_app = DebuggedApplication(app.wsgi_app, evalex=True)
    else:
        app.debug = False

    return app

def cache_result(cache, make_cache_key=None):
    def _caching(f, *args, **kwargs):
        if make_cache_key is None:
            cache_key = "%s(args=%r, kwargs=%r)" % (f.func_name, args, kwargs)
        else:
            cache_key = make_cache_key(*args, **kwargs)

        result = cache.get(cache_key)
        if result is not None:
            return result

        result = f(*args, **kwargs)
        cache.set(cache_key, result)
        return result

    return decorator.decorator(_caching)

def cache_many(cache):
    def _caching(f, *args):
        results = {
            a : r
            for a, r in cache.get_dict(*set(args)).items()
            if r is not None
        }

        sub_args = set(args) - set(results)
        if sub_args:
            sub_results = dict(zip(sub_args, f(*sub_args)))
            cache.set_many(sub_results)
            
            results.update(sub_results)

        return [results[a] for a in args]

    return decorator.decorator(_caching)
