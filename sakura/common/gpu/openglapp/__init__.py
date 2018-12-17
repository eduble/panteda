
import os
if os.environ.get('SAKURA_ENV', 'undef') == 'daemon':
    # OpenGLApp will be used in regular sakura environment
    # (an operator run by a daemon)
    from sakura.common.gpu.openglapp.eglapp import EGLApp as OpenglApp
else:
    # OpenGLApp will be run standalone (for debugging)
    from sakura.common.gpu.openglapp.glutapp import GlutApp as OpenglApp
