"""
This is the main dispatcher module.

Dispatch works as follows:
Start at the RootController, the root controller must
have a _dispatch function, which defines how we move
from object to object in the system.
Continue following the dispatch mechanism for a given
controller until you reach another controller with a 
_dispatch method defined.  Use the new _dispatch
method until anther controller with _dispatch defined
or until the url has been traversed to entirety.

This module also contains the standard ObjectDispatch
class which provides the ordinary TurboGears mechanism.

"""

from inspect import ismethod, isclass, getargspec
from warnings import warn
import pylons
import mimetypes
from pylons.controllers import WSGIController
from tg.exceptions import HTTPNotFound
from tg.util import odict

HTTPNotFound = HTTPNotFound().exception

class DispatchState(object):
    """
    This class keeps around all the pertainent info for the state
    of the dispatch as it traverses through the tree.  This allows
    us to attach things like routing args and to keep track of the
    path the controller takes along the system.
    """
    def __init__(self, url_path, params):
        self.url_path = url_path
        self.params = params
        self.controller_path = odict()
        self.routing_args = {}
        self.method = None
        self.remainder = None
        self.dispatcher = None

    def add_controller(self, location, controller):
        """Adds a controller object to the stack"""
        self.controller_path[location] = controller

    def add_method(self, method, remainder):
        """Adds the final method that will be called in the _call method"""
        self.method = method
        self.remainder = remainder

    def add_routing_args(self, current_path, remainder, fixed_args, var_args):
        """adds the "intermediate" routing args for a given controller mounted at the current_path"""
        i = 0
        for i, arg in enumerate(fixed_args):
            if i>=len(remainder):
                break;
            self.routing_args[arg] = remainder[i]
        remainder = remainder[i:]
        if var_args and remainder:
            self.routing_args[current_path] = remainder
        
    @property
    def controller(self):
        """returns the current controller"""
        return self.controller_path.getitem(-1)
    
class Dispatcher(WSGIController):
    """
       Extend this class to define your own mechanism for dispatch.
    """

    def _call(self, controller, params, remainder=None):
        """
            Override This function to define how your controller method should be called.
        """
        response = controller(*remainder, **dict(params))
        return response
    
    def _get_argspec(self, func):
        try:
            cached_argspecs = self.__class__._cached_argspecs
        except AttributeError:
            self.__class__._cached_argspecs = cached_argspecs = {}
        
        try:
            argspec = cached_argspecs[func.im_func]
        except KeyError:
            argspec = cached_argspecs[func.im_func] = getargspec(func)
        return argspec
 
    def _get_params_with_argspec(self, func, params, remainder):
        params = params.copy()
        argspec = self._get_argspec(func)
        argvars = argspec[0][1:]
        if argvars and enumerate(remainder):
            for i, var in enumerate(argvars):
                if i >= len(remainder):
                    break;
                params[var] = remainder[i]
        return params
    
    def _remove_argspec_params_from_params(self, func, params, remainder):
        """Remove parameters from the argument list that are
           not named parameters
           Returns: params, remainder"""
        
        # figure out which of the vars in the argspec are required
        argspec = self._get_argspec(func)
        argvars = argspec[0][1:]
            
        # if there are no required variables, or the remainder is none, we
        # have nothing to do
        if not argvars or not remainder:
            return params, remainder
        
        #this is a work around for a crappy api choice in getargspec
        argvals = argspec[3]
        if argvals is None:
            argvals = []

        required_vars = argvars
        optional_vars = []
        if argvals:
            required_vars = argvars[:len(argvals)-1]
            optional_vars = argvars[len(argvals)-1:]

        #make a copy of the params so that we don't modify the existing one
        params=params.copy()
        
        # replace the existing required variables with the values that come in from params
        # these could be the parameters that come off of validation.
        for i,var in enumerate(required_vars):
            remainder[i] = params[var]
            del params[var]
            
        #remove the optional vars from the params until we run out of remainder
        for var in optional_vars:
            if var in params:
                del params[var]

        return params, remainder
    
    def _dispatch(self, state, remainder):
        """override this to define how your controller should dispatch.
        returns: dispatcher, controller_path, remainder
        """
        raise NotImplementedError
    
    def _get_dispatchable(self, url_path):
        """
        Returns a tuple (controller, remainder, params)

        :Parameters:
          url
            url as string
        """
        
        pylons.request.response_type = None
        pylons.request.response_ext = None
        if url_path and '.' in url_path[-1]:
            last_remainder = url_path[-1]
            mime_type, encoding = mimetypes.guess_type(last_remainder)
            if mime_type:
                extension_spot = last_remainder.rfind('.')
                extension = last_remainder[extension_spot:]
                url_path[-1] = last_remainder[:extension_spot]
                pylons.request.response_type = mime_type
                pylons.request.response_ext = extension

        params = pylons.request.params.mixed()

        state = DispatchState(url_path, params)
        state.add_controller('/', self)
        state.dispatcher = self
        state =  state.controller._dispatch(state, url_path)
        
        pylons.c.controller_url = '/'.join(url_path[:-len(state.remainder)])
        

        state.routing_args.update(params)
        state.dispatcher._setup_wsgiorg_routing_args(url_path, state.remainder, state.routing_args)

        return state.method, state.controller, state.remainder, params

    def _setup_wsgiorg_routing_args(self, url_path, remainder, params):
        pass
        #this needs to get added back in after we understand why it breaks pagination.
#        pylons.request.environ['wsgiorg.routing_args'] = (tuple(remainder), params)
    
    def _setup_wsgi_script_name(self, url_path, remainder, params):
        pass

    def _perform_call(self, func, args):
        """
        This function is called from within Pylons and should not be overidden.
        """
        func_name = func.__name__
        pylons.request.path.split('/')[1:]

        url_path = pylons.request.path.split('/')[1:]

        if url_path[-1] == '':
            url_path.pop()

        func, controller, remainder, params = self._get_dispatchable(url_path)

        if hasattr(controller, '__before__'):
            warn("this functionality is going to removed in the next minor version,"\
                 " please use _before instead."
                 )
            controller.__before__(*args)
        if hasattr(controller, '_before'):
            controller._before(*args)
            
        self._setup_wsgi_script_name(url_path, remainder, params)

        r = self._call(func, params, remainder=remainder)

        if hasattr(controller, '__after__'):
            warn("this functionality is going to removed in the next minor version,"\
                 " please use _after instead."
                 )
            controller.__after__(*args)
        if hasattr(controller, '_after'):
            controller._after(*args)
        return r
    
    def routes_placeholder(self, url='/', start_response=None, **kwargs):
        """
        This function does not do anything.  It is a placeholder that allows
        Routes to accept this controller as a target for its routing.
        """
        pass

class ObjectDispatcher(Dispatcher):
    """
    Object dispatch (also "object publishing") means that each portion of the
    URL becomes a lookup on an object.  The next part of the URL applies to the
    next object, until you run out of URL.  Processing starts on a "Root"
    object.

    Thus, /foo/bar/baz become URL portion "foo", "bar", and "baz".  The
    dispatch looks for the "foo" attribute on the Root URL, which returns
    another object.  The "bar" attribute is looked for on the new object, which
    returns another object.  The "baz" attribute is similarly looked for on
    this object.

    Dispatch does not have to be directly on attribute lookup, objects can also
    have other methods to explain how to dispatch from them.  The search ends
    when a decorated controller method is found.

    The rules work as follows:

    1) If the current object under consideration is a decorated controller
       method, the search is ended.

    2) If the current object under consideration has a "default" method, keep a
       record of that method.  If we fail in our search, and the most recent
       method recorded is a "default" method, then the search is ended with
       that method returned.

    3) If the current object under consideration has a "lookup" method, keep a
       record of that method.  If we fail in our search, and the most recent
       method recorded is a "lookup" method, then execute the "lookup" method,
       and start the search again on the return value of that method.

    4) If the URL portion exists as an attribute on the object in question,
       start searching again on that attribute.

    5) If we fail our search, try the most recent recorded methods as per 2 and
       3.
    """
    def _find_first_exposed(self, controller, methods):
        for method in methods:
            if self._is_exposed(controller, method):
                return getattr(controller, method)
    
    def _is_exposed(self, controller, name):
        """Override this function to define how a controller method is
        determined to be exposed.
        
        :Arguments:
          controller - controller with methods that may or may not be exposed.
          name - name of the method that is tested.
        
        :Returns:
           True or None
        """
        if hasattr(controller, name) and ismethod(getattr(controller, name)):
            return True
        
    def _is_controller(self, controller, name):
        """
        Override this function to define how an object is determined to be a
        controller.
        """
        return hasattr(controller, name) and not ismethod(getattr(controller, name))

    def _dispatch_controller(self, current_path, controller, state, remainder):
        """
           Essentially, this method defines what to do when we move to the next
           layer in the url chain, if a new controller is needed.  If the new
           controller has a _dispatch method, dispatch proceeds to the new controller's
           mechanism.
           
           Also, this is the place where the controller is checked for controller-level
           security.
        """
        if hasattr(controller, '_dispatch'):
            if isclass(controller):
                warn("this functionality is going to removed in the next minor version,"\
                     " please create an instance of your sub-controller instead"
                     )
                controller = controller()
            if hasattr(controller, "im_self"):
                obj = controller.im_self
            else:
                obj = controller

            if hasattr(obj, '_check_security'):
                obj._check_security()
            state.add_controller(current_path, controller)
            state.dispatcher = controller
            return controller._dispatch(state, remainder)
        state.add_controller(current_path, controller)
        return self._dispatch(state, remainder)
        
    def _dispatch_first_found_default_or_lookup(self, state, remainder):
        """
           When the dispatch has reached the end of the tree but not found an applicable method, 
           so therefore we head back up the branches of the tree until we found a method which
           matches with a default or lookup method.
        """
        orig_url_path = state.url_path
        if len(remainder):
            state.url_path = state.url_path[:-len(remainder)]
        for i in xrange(len(state.controller_path)):
            controller = state.controller
            if self._is_exposed(controller, 'default'):
                state.add_method(controller.default, remainder)
                state.dispatcher = self
                return state
            if self._is_exposed(controller, 'lookup'):
                controller, remainder = controller.lookup(*remainder)
                state.url_path = orig_url_path
                return self._dispatch_controller('lookup', controller, state, remainder)
            state.controller_path.pop()
            if len(state.url_path):
                remainder = list(remainder)
                remainder.insert(0,state.url_path[-1])
                state.url_path.pop()
        raise HTTPNotFound

    def _dispatch(self, state, remainder):
        """
        This method defines how the object dispatch mechanism works, including
        checking for security along the way.
        """
        current_controller = state.controller

        if hasattr(current_controller, '_check_security'):
            current_controller._check_security()
        #we are plumb out of path, check for index
        if not remainder:
            if hasattr(current_controller, 'index'):
                state.add_method(current_controller.index, remainder)
                return state
            #if there is no index, head up the tree
            #to see if there is a default or lookup method we can use
            return self._dispatch_first_found_default_or_lookup(state, remainder)

        current_path = remainder[0]

        #an exposed method matching the path is found
        if self._is_exposed(current_controller, current_path):
            state.add_method(getattr(current_controller, current_path), remainder[1:])
            return state
        
        #another controller is found
        if hasattr(current_controller, current_path):
            current_controller = getattr(current_controller, current_path)
            return self._dispatch_controller(current_path, current_controller, state, remainder[1:])
        
        #dispatch not found
        return self._dispatch_first_found_default_or_lookup(state, remainder)