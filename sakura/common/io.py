import collections, itertools, io, sys, json, numpy as np
from gevent.queue import Queue
from gevent.event import AsyncResult

DEBUG_LEVEL = 0   # do not print messages exchanged
# DEBUG_LEVEL = 1   # print requests and type of results
# DEBUG_LEVEL = 2   # print requests and results (slowest mode)

ParsedRequest = collections.namedtuple('ParsedRequest',
                    ('req_id', 'path', 'args', 'kwargs'))

def make_json_serializable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return make_serializable(obj)

def make_serializable(obj):
    # some classes should be serialized directly
    if isinstance(obj, str) or isinstance(obj, bytes) or \
            isinstance(obj, np.ndarray):
        return obj
    # with other objects, try to be smart
    if isinstance(obj, dict):
        return { k: make_serializable(v) for k, v in obj.items() }
    elif hasattr(obj, 'summarize'):
        return make_serializable(obj.summarize())
    elif hasattr(obj, '_asdict'):
        return make_serializable(obj._asdict())
    elif isinstance(obj, list) or isinstance(obj, tuple) or \
                hasattr(obj, '__iter__'):
        return tuple(make_serializable(o) for o in obj)
    # object is probably serializable
    return obj

def json_fallback_handler(obj):
    obj2 = make_json_serializable(obj)
    if obj2 is obj:
        raise TypeError(repr(obj) + ' is not JSON serializable')
    return obj2

class CompactJsonProtocol:
    def load(self, f):
        return json.load(f)
    def dump(self, obj, f):
        return json.dump(obj, f,
                separators=(',', ':'),
                default=json_fallback_handler)

compactjson = CompactJsonProtocol()

def print_short(*args):
    if DEBUG_LEVEL == 0:
        return  # do nothing
    OUT = io.StringIO()
    print(*args, file=OUT)
    if OUT.tell() > 110:
        OUT.seek(110)
        OUT.write('...\n')
        OUT.truncate()
    sys.stdout.write(OUT.getvalue())

class LocalAPIHandler(object):
    def __init__(self, f, protocol, local_api, greenlets_pool = None):
        self.f = f
        self.protocol = protocol
        self.api_runner = AttrCallRunner(local_api)
        if greenlets_pool == None:
            self.handle_request = self.handle_request_base
        else:
            self.pool = greenlets_pool
            self.handle_request = self.handle_request_pool
    def loop(self):
        while True:
            should_continue = self.handle_next_request()
            if not should_continue:
                break
    def handle_next_request(self):
        try:
            raw_req = self.protocol.load(self.f)
            req = ParsedRequest(*raw_req)
            print_short('received', str(req))
        except BaseException:
            print('malformed request. closing.')
            return False
        self.handle_request(*req)
        return True
    def handle_request_base(self, req_id, path, args, kwargs):
        res = self.api_runner.do(path, args, kwargs)
        try:
            self.protocol.dump((req_id, make_serializable(res)), self.f)
            if DEBUG_LEVEL == 2:
                print_short("sent", req_id, res)
            elif DEBUG_LEVEL == 1:
                print_short("sent", req_id, res.__class__)
            self.f.flush()
        except BaseException as e:
            print('could not send response:', e)
    def handle_request_pool(self, *args):
        self.pool.spawn(self.handle_request_base, *args)

# The following pair of classes allows to pass API calls efficiently
# over a network socket.
#
# On the emitter end, we will have the following kind of code:
#
# api = AttrCallAggregator(api_forwarding_func)
# ...
# res = api.my.super.function(1, 2, a=3)
#
# This will cause the following to be called:
# api_forwarding_func('my.super.function', [1, 2], {'a':3})
#
# then it is easy for api_backend_func to pass its arguments
# on the socket connection.
#
# on the other end, we have have a code like:
#
# api_call_runner = AttrCallRunner(api_handler)
# ...
# api_call_runner.do('my.super.function', [1, 2], {'a':3})
#
# This will call the following to be called:
# api_handler.my.super.function(1, 2, a=3)
#
# This mechanism is efficient because it sends the whole attribute path
# at once on the network.
# Drawback: It works with remote function calls only, i.e. all
# remote attributes accessed must be functions.

class AttrCallAggregator(object):
    def __init__(self, handler, path = ()):
        self.path = path
        self.handler = handler
    def __getattr__(self, attr):
        return AttrCallAggregator(self.handler, self.path + (attr,))
    def __getitem__(self, index):
        return AttrCallAggregator(self.handler, self.path + ((index,),))
    def __call__(self, *args, **kwargs):
        return self.handler(self.path, args, kwargs)
    def __len__(self):
        path = self.path + ('__len__',)
        return self.handler(path, (), {})

class AttrCallRunner(object):
    def __init__(self, handler):
        self.handler = handler
    def do(self, path, args, kwargs):
        obj = self.handler
        for attr in path:
            if isinstance(attr, str):
                obj = getattr(obj, attr)
            else:
                obj = obj[attr[0]]  # getitem
        return obj(*args, **kwargs)

class RemoteAPIForwarder(AttrCallAggregator):
    def __init__(self, f, protocol):
        super().__init__(self.handler)
        self.f = f
        self.protocol = protocol
        self.reqs = {}
        self.req_ids = itertools.count()
        self.running = False
    def handler(self, path, args, kwargs):
        req_id = self.req_ids.__next__()
        async_res = AsyncResult()
        self.reqs[req_id] = async_res
        self.protocol.dump((req_id, path, args, kwargs), self.f)
        self.f.flush()
        # if the greenlet did not start the loop() method,
        # block until we get the result. (initialization phase)
        if not self.running:
            self.next_result()
        return async_res.get()
    def next_result(self):
        try:
            req_id, res = self.protocol.load(self.f)
        except BaseException:
            print('malformed result. closing.')
            return False
        async_res = self.reqs[req_id]
        async_res.set(res)
        del self.reqs[req_id]
        return True
    def loop(self):
        self.running = True
        while self.next_result():
            pass

