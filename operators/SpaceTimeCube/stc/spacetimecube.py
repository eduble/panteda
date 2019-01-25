#! /usr/bin/env python3
# -*- coding: utf-8 -*-
#Michael ORTEGA for PIMLIG/LIG/CNRS- 10/12/2018

import sys, math, time, inspect, datetime, gevent, threading
import numpy    as      np
from pathlib    import  Path
from PIL        import  Image
from gevent     import  Greenlet

try:
    from OpenGL.GL      import *
    from OpenGL.GLU     import *
    from OpenGL.GL      import shaders
except:
    print ('''ERROR: PyOpenGL not installed properly. ** ''')

from .libs import shader        as sh
from .libs import projector     as pr
from .libs import trajectory    as tr
from .libs import floor         as fl
from .libs import mercator      as mc
from .libs import tilenames     as tn

def wire_cube(mins, maxs):
    size = np.fabs(maxs - mins)
    return np.array(
            [   mins,
                mins + np.array([size[0], 0, 0]),
                mins + np.array([size[0], 0, 0]),
                mins + np.array([size[0], size[0], 0]),
                mins + np.array([size[0], size[0], 0]),
                mins + np.array([0, size[0], 0]),
                mins + np.array([0, size[0], 0]),
                mins,

                maxs,
                maxs - np.array([size[0], 0, 0]),
                maxs - np.array([size[0], 0, 0]),
                maxs - np.array([size[0], size[0], 0]),
                maxs - np.array([size[0], size[0], 0]),
                maxs - np.array([0, size[0], 0]),
                maxs - np.array([0, size[0], 0]),
                maxs,

                mins,
                mins + np.array([0, 0, size[0]]),
                mins + np.array([0, size[0], 0]),
                mins + np.array([0, size[0], size[0]]),

                maxs,
                maxs - np.array([0, 0, size[0]]),
                maxs - np.array([0, size[0], 0]),
                maxs - np.array([0, size[0], size[0]])
                ]
            )


class SpaceTimeCube:
    def __init__(self):
        # import local libs
        spacetimecube_py_path = Path(inspect.getabsfile(self.__class__))
        self.spacetimecube_dir = spacetimecube_py_path.parent
        # display attributes
        self.width = 100
        self.height = 100

        self.projo = pr.projector(position = [0, 0, 2])
        self.projo.wiggle = True
        self.projo.v_rotation(-45.)

        self.fps_limitation = 60    #Hz
        self.last_time      = time.time()
        self.label          = "3D cube"

        #Shaders
        self.sh_cube            = sh.shader()
        self.sh_shadows         = sh.shader()
        self.sh_back_shadows    = sh.shader()
        self.sh_trajects        = sh.shader()
        self.sh_back_trajects   = sh.shader()
        self.sh_floor           = sh.shader()

        #Trajectory data
        self.data = tr.data()
        #self.data.add([ [0,0,-1,0,0],
        #                [0,1,0,-1,0],
        #                [0,2,1,0,0]])
        self.data.add([])
        self.trajects_vertices, self.trajects_colors = self.data.compute_geometry()

        #floor
        self.floor = fl.floor()
        self.floor_text_coords = np.array([ [0.,0.], [0.,1.], [1.,1.],
                                            [0.,0.], [1.,1.], [1.,0.]])

        #Global display data
        self.cube_vertices      = wire_cube(np.array([-.5,0,-.5]),
                                            np.array([.5,1,.5]))

        self.floor_vertices     = np.array([[0, 0, 0], [0, 0, 1], [1, 0, 1],
                                            [0, 0, 0], [1, 0, 1], [1, 0, 0]])
        self.thickness_of_backs = 8 #pixels
        self.floor_darkness     = .5
        self.green_floor        = None

        self.debug = False

    def init(self):
        self.mouse = [ 0, 0 ]
        self.imode = 'none'
        glEnable(GL_MULTISAMPLE)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc (GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

        if self.debug:
            print('\n-------------------------')
            print('Inits')
        self.init_shaders()
        if self.debug:
            print('-------------------------')
            print('Running')

    def init_shaders(self):

        glsl_version = glGetString(GL_SHADING_LANGUAGE_VERSION).decode("utf-8")
        glsl_version = glsl_version.replace('.', '')

        ##########################
        # general vertex array object
        if self.debug:
            print('\t\33[1;32mGenerating vao...\33[m', end='')
        sys.stdout.flush()
        try:
            vao = glGenVertexArrays(1)
            glBindVertexArray(vao)
            if self.debug:
                print('\tOk')
            sys.stdout.flush()
        except ValueError:
            print()
            print()
            print(ValueError)
            print()
            sys.exit()



        ##########################
        # VBOS & attributes
        self.vbo_cube               = glGenBuffers(1)
        self.attr_cube_vertices     = sh.new_attribute_index()

        self.vbo_trajects_vertices  = glGenBuffers(1)
        self.vbo_trajects_colors    = glGenBuffers(1)
        self.attr_trajects_vertices = sh.new_attribute_index()
        self.attr_trajects_colors   = sh.new_attribute_index()

        self.vbo_floor_vertices     = glGenBuffers(1)
        self.vbo_floor_text_coords  = glGenBuffers(1)
        self.attr_floor_vertices    = sh.new_attribute_index()
        self.attr_floor_text_coords = sh.new_attribute_index()

        ##########################
        # Shaders
        #-----------------------------------------------
        # Cube
        ## CALLBACKS -------
        def _update_cube_arrays():
            sh.bind(self.vbo_cube, self.cube_vertices, self.attr_cube_vertices, 3, GL_FLOAT)
        self.update_cube_arrays = _update_cube_arrays

        def cube_display():
            self.sh_cube.update_uniforms()
            glDrawArrays(GL_LINES, 0, len(self.cube_vertices))
        self.sh_cube.display = cube_display

        def update_uni_cube():
            self.sh_cube.set_uniform("maxs", self.data.maxs, '4fv')
            self.sh_cube.set_uniform("mins", self.data.mins, '4fv')
            self.sh_cube.set_uniform("projection_mat", self.projo.projection().T, 'm4fv')
            self.sh_cube.set_uniform("modelview_mat", self.projo.modelview().T, 'm4fv')
        self.sh_cube.update_uniforms = update_uni_cube

        ## CALLBACKS -------
        self.update_cube_arrays()

        # Loading shader files
        if self.debug:
            print('\t\33[1;32mCube shader...\33[m', end='')
        sys.stdout.flush()
        self.sh_cube.sh = sh.create(str(self.spacetimecube_dir / 'shaders/cube.vert'),
                                    None,
                                    str(self.spacetimecube_dir / 'shaders/cube.frag'),
                                    [self.attr_cube_vertices], ['in_vertex'],
                                    glsl_version)
        if not self.sh_cube.sh: exit(1)
        if self.debug:
            print('\t\tOk')
        sys.stdout.flush()
        #-----------------------------------------------

        #-----------------------------------------------
        # Shadows
        ## CALLBACKS -------
        def _update_trajects_arrays():
            sh.bind(self.vbo_trajects_vertices, self.trajects_vertices, self.attr_trajects_vertices, 4, GL_FLOAT)
            sh.bind(self.vbo_trajects_colors, self.trajects_colors, self.attr_trajects_colors, 4, GL_FLOAT)
        self.update_trajects_arrays = _update_trajects_arrays

        def shadows_display():
            self.sh_shadows.update_uniforms()
            glDrawArrays(GL_LINE_STRIP, 0, len(self.trajects_vertices))
        self.sh_shadows.display = shadows_display

        def update_uni_shadows():
            self.sh_shadows.set_uniform("maxs", self.data.maxs, '4fv')
            self.sh_shadows.set_uniform("mins", self.data.mins, '4fv')
            self.sh_shadows.set_uniform("projection_mat", self.projo.projection().T, 'm4fv')
            self.sh_shadows.set_uniform("modelview_mat", self.projo.modelview().T, 'm4fv')
        self.sh_shadows.update_uniforms = update_uni_shadows
        ## CALLBACKS -------

        self.update_trajects_arrays()

        # Loading shader files
        if self.debug:
            print('\t\33[1;32mShadows shader...\33[m', end='')
        sys.stdout.flush()
        self.sh_shadows.sh = sh.create( str(self.spacetimecube_dir / 'shaders/shadows.vert'),
                                        None,
                                        str(self.spacetimecube_dir / 'shaders/shadows.frag'),
                                        [self.attr_trajects_vertices, self.attr_trajects_colors],
                                        ['in_vertex', 'in_color'],
                                        glsl_version)

        if not self.sh_shadows.sh: exit(1)
        if self.debug:
            print('\tOk')
        sys.stdout.flush()
        #-----------------------------------------------

        #-----------------------------------------------
        # Back Shadows
        ## CALLBACKS -------
        def back_shadows_display():
            self.sh_back_shadows.update_uniforms()
            glDrawArrays(GL_LINE_STRIP_ADJACENCY, 0, len(self.trajects_vertices))
        self.sh_back_shadows.display = back_shadows_display

        def update_uni_back_shadows():
            h       = self.projo.near*math.tan(self.projo.v_angle/2.0)
            p_size  = h*2/(self.height)
            self.sh_back_shadows.set_uniform("pixel_size", p_size, 'f')
            self.sh_back_shadows.set_uniform("nb_pixels", self.thickness_of_backs, 'i')
            self.sh_back_shadows.set_uniform("cam_near", self.projo.near, 'f')
            self.sh_back_shadows.set_uniform("cam_pos", self.projo.position, '3fv')
            self.sh_back_shadows.set_uniform("maxs", self.data.maxs, '4fv')
            self.sh_back_shadows.set_uniform("mins", self.data.mins, '4fv')
            self.sh_back_shadows.set_uniform("projection_mat", self.projo.projection().T, 'm4fv')
            self.sh_back_shadows.set_uniform("modelview_mat", self.projo.modelview().T, 'm4fv')
        self.sh_back_shadows.update_uniforms = update_uni_back_shadows
        ## CALLBACKS -------

        # Loading shader files
        if self.debug:
            print('\t\33[1;32mBack shadows shader...\33[m', end='')
        sys.stdout.flush()
        self.sh_back_shadows.sh = sh.create(str(self.spacetimecube_dir / 'shaders/back_shadows.vert'),
                                            str(self.spacetimecube_dir / 'shaders/back_shadows.geom'),
                                            str(self.spacetimecube_dir / 'shaders/back_shadows.frag'),
                                            [self.attr_trajects_vertices, self.attr_trajects_colors],
                                            ['in_vertex', 'in_color'],
                                            glsl_version)

        if not self.sh_back_shadows.sh: exit(1)
        if self.debug:
            print('\tOk')
        sys.stdout.flush()
        #-----------------------------------------------

        #-----------------------------------------------
        # Main trajectories
        ## CALLBACKS -------
        def trajects_display():
            self.sh_trajects.update_uniforms()
            glDrawArrays(GL_LINE_STRIP, 0, len(self.trajects_vertices))
        self.sh_trajects.display = trajects_display

        def update_uni_trajects():
            self.sh_trajects.set_uniform("maxs", self.data.maxs, '4fv')
            self.sh_trajects.set_uniform("mins", self.data.mins, '4fv')
            self.sh_trajects.set_uniform("projection_mat", self.projo.projection().T, 'm4fv')
            self.sh_trajects.set_uniform("modelview_mat", self.projo.modelview().T, 'm4fv')
        self.sh_trajects.update_uniforms = update_uni_trajects
        ## CALLBACKS -------

        # Loading shader files
        if self.debug:
            print('\t\33[1;32mTrajects shader...\33[m', end='')
        sys.stdout.flush()
        self.sh_trajects.sh = sh.create(str(self.spacetimecube_dir / 'shaders/trajects.vert'),
                                        None,
                                        str(self.spacetimecube_dir / 'shaders/trajects.frag'),
                                        [self.attr_trajects_vertices, self.attr_trajects_colors],
                                        ['in_vertex', 'in_color'],
                                        glsl_version)

        if not self.sh_trajects.sh: exit(1)
        if self.debug:
            print('\tOk')
        sys.stdout.flush()
        #-----------------------------------------------

        #-----------------------------------------------
        # Back Shadows
        ## CALLBACKS -------
        def back_trajects_display():
            self.sh_back_shadows.update_uniforms()
            glDrawArrays(GL_LINE_STRIP_ADJACENCY, 0, len(self.trajects_vertices))
        self.sh_back_trajects.display = back_trajects_display

        def update_uni_back_trajects():
            h       = self.projo.near*math.tan(self.projo.v_angle/2.0)
            p_size  = h*2/(self.height)
            self.sh_back_trajects.set_uniform("pixel_size", p_size, 'f')
            self.sh_back_trajects.set_uniform("nb_pixels", self.thickness_of_backs, 'i')
            self.sh_back_trajects.set_uniform("cam_near", self.projo.near, 'f')
            self.sh_back_trajects.set_uniform("cam_pos", self.projo.position, '3fv')
            self.sh_back_trajects.set_uniform("maxs", self.data.maxs, '4fv')
            self.sh_back_trajects.set_uniform("mins", self.data.mins, '4fv')
            self.sh_back_trajects.set_uniform("projection_mat", self.projo.projection().T, 'm4fv')
            self.sh_back_trajects.set_uniform("modelview_mat", self.projo.modelview().T, 'm4fv')
        self.sh_back_trajects.update_uniforms = update_uni_back_trajects
        ## CALLBACKS -------

        # Loading shader files
        if self.debug:
            print('\t\33[1;32mBack trajects shader...\33[m', end='')
        sys.stdout.flush()
        self.sh_back_trajects.sh = sh.create(str(self.spacetimecube_dir / 'shaders/back_trajects.vert'),
                                            str(self.spacetimecube_dir / 'shaders/back_trajects.geom'),
                                            str(self.spacetimecube_dir / 'shaders/back_trajects.frag'),
                                            [self.attr_trajects_vertices, self.attr_trajects_colors],
                                            ['in_vertex', 'in_color'],
                                            glsl_version)

        if not self.sh_back_trajects.sh: exit(1)
        if self.debug:
            print('\tOk')
        sys.stdout.flush()
        #-----------------------------------------------

        #-----------------------------------------------
        # Floor
        ## CALLBACKS -------
        def _update_floor_arrays():
            sh.bind(self.vbo_floor_vertices, self.floor_vertices, self.attr_floor_vertices, 3, GL_FLOAT)
            sh.bind(self.vbo_floor_text_coords, self.floor_text_coords, self.attr_floor_text_coords, 2, GL_FLOAT)
        self.update_floor_arrays = _update_floor_arrays

        def floor_display():
            self.sh_floor.update_uniforms()
            glDrawArrays(GL_TRIANGLES, 0, len(self.floor_vertices))
        self.sh_floor.display = floor_display

        def update_uni_floor():
            self.sh_floor.set_uniform("maxs", self.data.maxs, '4fv')
            self.sh_floor.set_uniform("mins", self.data.mins, '4fv')
            self.sh_floor.set_uniform("projection_mat", self.projo.projection().T, 'm4fv')
            self.sh_floor.set_uniform("modelview_mat", self.projo.modelview().T, 'm4fv')
            self.sh_floor.set_uniform("floor_texture", 0, 'i')
        self.sh_floor.update_uniforms = update_uni_floor

        self.sh_floor.texture_id = glGenTextures(1)
        def u_texture(init = False):
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.sh_floor.texture_id);

            w = self.floor.img.width
            h = self.floor.img.height

            black = Image.new('RGB', (w, h), (0, 0, 0))
            f = self.floor.img.resize((w, h), Image.ANTIALIAS)
            final = Image.blend(f, black, self.floor_darkness)

            arr = np.fromstring(final.tobytes(), np.uint8)
            glTexImage2D(   GL_TEXTURE_2D, 0, GL_RGB,
                            final.width,
                            final.height,
                            0, GL_RGB, GL_UNSIGNED_BYTE, arr);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);

        self.sh_floor.update_texture = u_texture
        ## CALLBACKS -------

        self.sh_floor.update_texture()
        self.update_floor_arrays()

        # Loading shader files
        if self.debug:
            print('\t\33[1;32mFloor shader...\33[m', end='')
        sys.stdout.flush()
        self.sh_floor.sh = sh.create(str(self.spacetimecube_dir / 'shaders/floor.vert'),
                                        None,
                                        str(self.spacetimecube_dir / 'shaders/floor.frag'),
                                        [self.attr_floor_vertices, self.attr_floor_text_coords],
                                        ['in_vertex', 'in_text_coords'],
                                        glsl_version)

        if not self.sh_floor.sh: exit(1)
        if self.debug:
            print('\t\tOk')
        sys.stdout.flush()

        #-----------------------------------------------

    def load_data(self, chunk=[], file=''):
        if len(chunk) >0:
            self.data.add(chunk)
        elif file != '':
            if self.debug:
                print('\t\33[1;32mReading data...\33[m', end='')
            sys.stdout.flush()
            big_chunk = np.recfromcsv(file, delimiter=',', encoding='utf-8')
            if type(big_chunk[0][1]) != int:
                for b in big_chunk:
                    b[1] = int(datetime.datetime.strptime(b[1], '%Y-%m-%d %H:%M:%S').strftime("%s"))
                big_chunk = big_chunk.astype([  ('trajectory', big_chunk.dtype[0]),
                                                ('date', big_chunk.dtype[2]),
                                                ('longitude', big_chunk.dtype[2]),
                                                ('latitude', big_chunk.dtype[3]),
                                                ('elevation', big_chunk.dtype[4])])
            self.data.add(big_chunk[ : int(len(big_chunk)/2)])
            self.data.add(big_chunk[int(len(big_chunk)/2) : ])
            if self.debug:
                print('\t\tOk')
        sys.stdout.flush()

        #self.data.print_meta()
        self.trajects_vertices, self.trajects_colors = np.array(self.data.compute_geometry())
        self.update_trajects_arrays()
        #self.update_floor()
        self.update_cube()

    def clean_data(self):
        if self.debug:
            print('\33[1;32m\tCleaning data...\33[m', end='')
        self.data.clean()
        if self.debug:
            print('\tOk')

    def update_cube(self):
        self.update_cube_arrays()

    def display(self):
        glClearColor(.31,.63,1.0,1.0)
        glClear(GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT)

        glDisable(GL_DEPTH_TEST)
        sh.display_list([   self.sh_floor,
                            self.sh_cube,
                            self.sh_back_shadows,
                            self.sh_back_trajects
                            ])
        glEnable(GL_DEPTH_TEST)
        sh.display_list([   self.sh_cube,
                            self.sh_shadows,
                            self.sh_trajects
                            ])

    def on_mouse_click(self, button, state, x, y):
        self.mouse = [x, y]
        LEFT_BUTTON = 0
        MIDDLE_BUTTON = 1
        RIGHT_BUTTON = 2
        DOWN = 0
        UP = 1
        if button == LEFT_BUTTON and state == DOWN:
            self.imode = 'rotation'
        elif button == RIGHT_BUTTON and state == DOWN:
            self.imode = 'translation'
        elif state == UP:
            self.imode = 'none'

    def on_mouse_motion(self, x, y):
        dx, dy = x - self.mouse[0], y - self.mouse[1]
        if self.imode == 'rotation':
            self.projo.h_rotation(-dx/self.width*math.pi*2)
            self.projo.v_rotation(-dy/self.height*math.pi*2)
        elif self.imode == 'translation':
            d = np.linalg.norm(np.array(self.projo.viewpoint) - np.array(self.projo.position))
            self.projo.translate([-dx*d/1000, dy*d/1000])
        self.mouse = [x, y]

    def on_wheel(self, delta):
        self.projo.zoom(-delta/10.)

    def on_key_press(self, key, x, y):
        if key == b'\x1b':
            sys.exit()
        elif key == b't':
            self.update_floor()
        elif key == b'w':
            self.toggle_wiggle()
        elif key == b'+':
            self.projo.zoom(1)
        elif key == b'-':
            self.projo.zoom(-1)
        elif key == b'D':
            self.set_floor_darkness(self.floor_darkness+.1)
        elif key == b'd':
            self.set_floor_darkness(self.floor_darkness-.1)
        elif key == b'p':
            self.data.print_meta()
        elif key == b'f':
            self.update_floor()
        else:
            print('\33[1;32m\tUnknown key\33[m', key)

    def on_resize(self, w, h):
        glViewport(0,  0,  w,  h);
        self.projo.change_ratio(w/float(h))
        self.width, self.height = w, h

    def animation(self):
        if self.projo.wiggle:
            self.projo.wiggle_next()

    def toggle_wiggle(self):
        self.projo.wiggle = not self.projo.wiggle

    def set_floor_darkness(self, value):
        if value > 1.0:
            self.floor_darkness = 1.0
        elif value < 0.0:
            self.floor_darkness = 0.0
        else:
            self.floor_darkness = value
        self.sh_floor.update_texture()

    def update_floor(self):
        if self.debug:
            print('\t\33[1;32mUpdating floor...\33[m', flush = True)
        sys.stdout.flush()

        # longitude and latitude of the cube corners
        lon_min, lat_min = mc.lonlat_from_mercator( self.data.mins[1],self.data.mins[2])
        lon_max, lat_max = mc.lonlat_from_mercator( self.data.maxs[1],self.data.maxs[2])

        # computing the higher depth that gives a tile smaller than the cube size
        z = tn.depth_from_size(lon_max - lon_min)+1

        # coordinates of the tiles
        lon_t_min, lat_t_min = tn.tileXY(lat_min, lon_min, z)
        lon_t_max, lat_t_max = tn.tileXY(lat_max, lon_max, z)

        edges = []
        coords = []
        size = [lon_t_max - lon_t_min + 1, lat_t_min - lat_t_max + 1]
        for lo in range(size[0]):
            for la in range(size[1]):
                lon = lon_t_min + lo
                lat = lat_t_min - la
                edges.append(tn.tileEdges(lon, lat , z))
                coords.append({'lon': lon, 'lat': lat, 'img_x': lo, 'img_y': la })

        self.floor.img = self.floor.img.resize(((size[0])*256, (size[1])*256) )
        lon_min, lat_min = mc.mercator(edges[0]['w'], edges[0]['s'])
        lon_max, lat_max = mc.mercator(edges[-1]['e'], edges[-1]['n'])
        self.floor_vertices = np.array([[lon_min, 0, lat_min],
                                        [lon_min, 0, lat_max],
                                        [lon_max, 0, lat_max],
                                        [lon_min, 0, lat_min],
                                        [lon_max, 0, lat_max],
                                        [lon_max, 0, lat_min]])
        if self.debug:
            print('\t\t\33[1;32mDownloading tiles 0%\33[m', end='', flush = True)

        for i in range(len(coords)):
            self.download_tile(coords[i], z, str(int((i+1)*100/len(coords))))
            self.update_floor_arrays()
            self.sh_floor.update_texture()
        if self.debug:
            print('\tOk', flush = True)

    def download_tile(self, coords, z, perc):
        self.floor.download_tile(   coords['lon'],
                                    coords['lat'],
                                    z,
                                    coords['img_x'],
                                    coords['img_y'])
        if self.debug:
            print(  '\r\t\t\33[1;32mDownloading tiles '+perc+'%\33[m',
                    end='',
                    flush = True)
