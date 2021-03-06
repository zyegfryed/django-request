import re

from django.utils.translation import string_concat, ugettext, ugettext_lazy as _
from django.template.loader import render_to_string

from request import settings
from request.models import Request
from request.traffic import modules

# Calculate the verbose_name by converting from InitialCaps to "lowercase with spaces".
get_verbose_name = lambda class_name: re.sub('(((?<=[a-z])[A-Z])|([A-Z](?![A-Z]|$)))', ' \\1', class_name).strip()

def set_count(items):
    """
    This is similar to "set", but this just creates a list with values.
    The list will be ordered from most frequent down.
    
    Example:
        >>> inventory = ['apple', 'lemon', 'apple', 'orange', 'lemon', 'lemon']
        >>> set_count(inventory)
        [('lemon', 3), ('apple', 2), ('orange', 1)]
    """
    item_count = {}
    for item in items:
        if not item: continue
        if not item_count.has_key(item): item_count[item] = 0
        item_count[item] += 1
    
    items = [(v, k) for k, v in item_count.iteritems()]
    items.sort()
    items.reverse()
    
    return [(k, v) for v, k in items]

class Plugins(object):
    def load(self):
        from django.utils.importlib import import_module
        from django.core import exceptions
        
        self._plugins = []
        for module_path in settings.REQUEST_PLUGINS:
            try:
                dot = module_path.rindex('.')
            except ValueError:
                raise exceptions.ImproperlyConfigured, '%s isn\'t a plugin' % module_path
            plugin, plugin_classname = module_path[:dot], module_path[dot+1:]
            
            try:
                mod = import_module(plugin)
            except ImportError, e:
                raise exceptions.ImproperlyConfigured, 'Error importing plugin %s: "%s"' % (plugin, e)
            
            try:
                plugin_class = getattr(mod, plugin_classname)
            except AttributeError:
                raise exceptions.ImproperlyConfigured, 'Plugin "%s" does not define a "%s" class' % (plugin, plugin_classname)
            
            self._plugins.append(plugin_class())
    
    def plugins(self):
        if not hasattr(self, '_plugins'):
            self.load()
        return self._plugins
    plugins = property(plugins)

plugins = Plugins()

class Plugin(object):
    def __init__(self):
        self.module_name = self.__class__.__name__
        
        if not hasattr(self, 'verbose_name'):
            self.verbose_name = _(get_verbose_name(self.module_name))
    
    def template_context(self):
        {}
    
    def render(self):
        templates = [
            "request/plugins/%s.html" % (self.__class__.__name__.lower()),
            "request/plugins/base.html",
        ]
        
        if hasattr(self, 'template'):
            templates.insert(0, self.template)
        
        kwargs = self.template_context()
        kwargs['verbose_name'] = self.verbose_name
        kwargs['plugin'] = self
        return render_to_string(templates, kwargs)

class LatestRequests(Plugin):
    def template_context(self):
        return {'requests': Request.objects.all()[:5]}

class TrafficInformation(Plugin):
    def template_context(self):
        INFO_TABLE = ('today', 'this_week', 'this_month', 'this_year', 'all')
        INFO_TABLE_QUERIES = [getattr(Request.objects, query, None)() for query in INFO_TABLE]
        
        return {
            'traffic': modules.table(INFO_TABLE_QUERIES)
        }

class TopPaths(Plugin):
    def queryset(self):
        return self.qs.filter(response__lt=400).values_list('path', flat=True)
    
    def template_context(self):
        return {
            'paths': set_count(self.queryset())[:10]
        }

class TopErrorPaths(TopPaths):
    template = 'request/plugins/toppaths.html'
    
    def queryset(self):
        return self.qs.filter(response__gte=400).values_list('path', flat=True)

class TopReferrers(Plugin):
    def template_context(self):
        return {
            'referrers': set_count(self.qs.unique_visits().exclude(referer='').values_list('referer', flat=True))[:10]
        }

class TopSearchPhrases(Plugin):
    def template_context(self):
        return {
            'phrases': set_count(self.qs.search().only('referer').attr_list('keywords'))[:10]
        }

class TopBrowsers(Plugin):
    def template_context(self):
        return {
            'browsers': set_count(self.qs.only('user_agent').attr_list('browser'))[:5]
        }

class ActiveUsers(Plugin):
    def template_context(self):
        return {}
