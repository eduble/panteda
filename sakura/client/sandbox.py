#!/usr/bin/env python3
import sys, pathlib, uuid, gevent, signal, atexit
from sakura.common.tools import yield_operator_subdirs
from sakura.common.streams import enable_standard_streams_redirection
from sakura.client import api

def usage_and_exit():
    print('Usage: %s [<code-directory>]' % sys.argv[0])
    sys.exit(1)

def signal_handler(signal, frame):
    print()
    print('Ending sandbox.')
    sys.exit(0)

def run():
    if len(sys.argv) < 2:
        sandbox_dir = '.'
    else:
        sandbox_dir = sys.argv[1]
    sandbox_dir = pathlib.Path(sandbox_dir)
    if not sandbox_dir.is_dir():
        usage_and_exit()
    signal.signal(signal.SIGINT, signal_handler)
    sandbox_uuid = str(uuid.uuid4())
    sandbox_dir = sandbox_dir.resolve()
    sandbox_streams = sys
    op_dirs = list(yield_operator_subdirs(sandbox_dir))
    if len(op_dirs) == 0:
        print('Did not find sakura operator source code in this directory. Giving up.', file=sys.stderr)
        sys.exit(1)
    enable_standard_streams_redirection()
    for op_dir in op_dirs:
        op_subdir = str(op_dir.relative_to(sandbox_dir))
        op_cls = api.op_classes.register_from_sandbox(
            sandbox_uuid, sandbox_dir, sandbox_streams, op_subdir
        )
        atexit.register(op_cls.unregister)
        print('Exposing operator class at ' + str(op_dir))
    gevent.get_hub().join()

if __name__ == '__main__':
    run()
