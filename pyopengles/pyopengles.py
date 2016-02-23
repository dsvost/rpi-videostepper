#
# Copyright (c) 2012 Peter de Rivaz
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted.
#
# Raspberry Pi 3d demo using OpenGLES 2.0 via Python
#
# Version 0.1 (Draws a rectangle using vertex and fragment shaders)
# Version 0.2 (Draws a Julia set on top of a Mandelbrot controlled by the mouse.  Mandelbrot rendered to texture in advance.

import ctypes
import time
import math
# Pick up our constants extracted from the header files with prepare_constants.py
from egl import *
from gl2 import *
from gl2ext import *
import pymouse
from threading import Thread, Lock

# Define verbose=True to get debug messages
verbose = True

# Define some extra constants that the automatic extraction misses
EGL_DEFAULT_DISPLAY = 0
EGL_NO_CONTEXT = 0
EGL_NO_DISPLAY = 0
EGL_NO_SURFACE = 0
DISPMANX_PROTECTION_NONE = 0

# Open the libraries
bcm = ctypes.CDLL('libbcm_host.so')
opengles = ctypes.CDLL('libGLESv2.so')
openegl = ctypes.CDLL('libEGL.so')

eglint = ctypes.c_int

eglshort = ctypes.c_short

def eglints(L):
    """Converts a tuple to an array of eglints (would a pointer return be better?)"""
    return (eglint*len(L))(*L)

eglfloat = ctypes.c_float

def eglfloats(L):
    return (eglfloat*len(L))(*L)

def check(e):
    """Checks that error is zero"""
    if e==0: return
    if verbose:
        print 'Error code',hex(e&0xffffffff)
    raise ValueError

class EGL(object):

    def __init__(self,depthbuffer=False):
        """Opens up the OpenGL library and prepares a window for display"""
        b = bcm.bcm_host_init()
        assert b==0
        self.display = openegl.eglGetDisplay(EGL_DEFAULT_DISPLAY)
        assert self.display
        r = openegl.eglInitialize(self.display,0,0)
        assert r
        if depthbuffer:
            attribute_list = eglints(     (EGL_RED_SIZE, 8,
                                      EGL_GREEN_SIZE, 8,
                                      EGL_BLUE_SIZE, 8,
                                      EGL_ALPHA_SIZE, 8,
                                      EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
                                      EGL_DEPTH_SIZE, 16,
                                      EGL_NONE) )
        else:
            attribute_list = eglints(     (EGL_RED_SIZE, 8,
                                      EGL_GREEN_SIZE, 8,
                                      EGL_BLUE_SIZE, 8,
                                      EGL_ALPHA_SIZE, 8,
                                      EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
                                      EGL_NONE) )
        # EGL_SAMPLE_BUFFERS,  1,
        # EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,

        numconfig = eglint()
        config = ctypes.c_void_p()
        r = openegl.eglChooseConfig(self.display,
                                     ctypes.byref(attribute_list),
                                     ctypes.byref(config), 1,
                                     ctypes.byref(numconfig));
        assert r
        r = openegl.eglBindAPI(EGL_OPENGL_ES_API)
        assert r
        if verbose:
            print 'numconfig=',numconfig
        context_attribs = eglints( (EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE) )
        self.context = openegl.eglCreateContext(self.display, config,
                                        EGL_NO_CONTEXT,
                                        ctypes.byref(context_attribs))
        assert self.context != EGL_NO_CONTEXT
        width = eglint()
        height = eglint()
        s = bcm.graphics_get_display_size(0,ctypes.byref(width),ctypes.byref(height))
        self.width = width
        self.height = height
        assert s>=0
        dispman_display = bcm.vc_dispmanx_display_open(0)
        dispman_update = bcm.vc_dispmanx_update_start( 0 )
        dst_rect = eglints( (0,0,width.value,height.value) )
        src_rect = eglints( (0,0,width.value<<16, height.value<<16) )
        assert dispman_update
        assert dispman_display
        dispman_element = bcm.vc_dispmanx_element_add ( dispman_update, dispman_display,
                                  10000, ctypes.byref(dst_rect), 0,
                                  ctypes.byref(src_rect),
                                  DISPMANX_PROTECTION_NONE,
                                  0 , 0, 0)
        bcm.vc_dispmanx_update_submit_sync( dispman_update )
        nativewindow = eglints((dispman_element,width,height));
        nw_p = ctypes.pointer(nativewindow)
        self.nw_p = nw_p
        self.surface = openegl.eglCreateWindowSurface( self.display, config, nw_p, 0)
        assert self.surface != EGL_NO_SURFACE
        r = openegl.eglMakeCurrent(self.display, self.surface, self.surface, self.context)
        assert r

class demo():

    def showlog(self,shader):
        """Prints the compile log for a shader"""
        N=1024
        log=(ctypes.c_char*N)()
        loglen=ctypes.c_int()
        opengles.glGetShaderInfoLog(shader,N,ctypes.byref(loglen),ctypes.byref(log))
        print log.value

    def showprogramlog(self,shader):
        """Prints the compile log for a program"""
        N=1024
        log=(ctypes.c_char*N)()
        loglen=ctypes.c_int()
        opengles.glGetProgramInfoLog(shader,N,ctypes.byref(loglen),ctypes.byref(log))
        print log.value

    def __init__(self):
        self.vertex_data = eglfloats((-1.0,-1.0,1.0,1.0,
                         1.0,-1.0,1.0,1.0,
                         1.0,1.0,1.0,1.0,
                         -1.0,1.0,1.0,1.0))
        self.vshader_source = ctypes.c_char_p(
              "attribute vec4 vertex;"
              "varying vec2 tcoord;"
              "varying vec4 color;"
              "void main(void) {"
              "  vec4 pos = vertex;"
              "  pos.xy*=0.9;"
              "  gl_Position = pos;"
              "  tcoord = vertex.xy*0.5+0.5;"
              "  color = pos;"
              "}")

        self.vsimple_shader_source = ctypes.c_char_p(
            "attribute vec4 vertex;"
            "varying vec4 pos;"
            "uniform float uTime;"
            "void main(void) {"
            "   gl_Position = vertex;"
            "   pos = vertex;"
            "}"
        )

        self.fshader_source = ctypes.c_char_p(
              "precision highp float;"
              "vec2 c = vec2(0.35,0.45);"
              "varying vec4 pos;"
              "uniform float uTime;"
              "void main(void) {"
              "   float distanceFromLight = length(c - pos.xy);"
              "   float radius = sin(uTime);"
              "   float alphaComponent = 1.0 - distanceFromLight/max(radius*3.0, 0.001);"
              "   gl_FragColor = vec4(1.0,1.0,1.0,alphaComponent+uTime/4.0);"
              "}")

              #"   float alphaComponent = 1.0 - min(0.3, sin(distanceFromLight*5.0));"

        self.f2shader_source = ctypes.c_char_p(
            "varying vec4 color;"
            "float rand(vec2 co) {"
            "   return fract(sin(dot(co.xy, vec2(12.9898, 78.233))) * 43758.5453);"
            "}"
            "void main(void) {"
            "   float r = rand(color.rg*color.gb);"
            "   float g = rand(color.gb*color.rb);"
            "   float b = rand(color.rb*color.bb);"
            "   gl_FragColor=vec4(r,r,r,0.3);"
            "}")

        self.offset = 0
        self.offset_direction = 0.2
        self.finished = False
        self.canFinish = False

        vshader = opengles.glCreateShader(GL_VERTEX_SHADER);
        opengles.glShaderSource(vshader, 1, ctypes.byref(self.vsimple_shader_source), 0)
        opengles.glCompileShader(vshader);

        if verbose:
            self.showlog(vshader)

        fshader = opengles.glCreateShader(GL_FRAGMENT_SHADER);
        opengles.glShaderSource(fshader, 1, ctypes.byref(self.fshader_source), 0);
        opengles.glCompileShader(fshader);

        if verbose:
            self.showlog(fshader)

        program = opengles.glCreateProgram();
        opengles.glAttachShader(program, vshader);
        opengles.glAttachShader(program, fshader);
        opengles.glLinkProgram(program);

        if verbose:
            self.showprogramlog(program)

        self.program = program
        self.unif_color = opengles.glGetUniformLocation(program, "color");
        self.attr_vertex = opengles.glGetAttribLocation(program, "vertex");
        self.unif_scale = opengles.glGetUniformLocation(program, "scale");
        self.unif_offset = opengles.glGetUniformLocation(program, "offset");
        self.unif_tex = opengles.glGetUniformLocation(program, "tex0");
        self.unif_utime = opengles.glGetUniformLocation(program, "uTime");

        opengles.glClearColor ( eglfloat(0.0), eglfloat(0.0), eglfloat(0.0), eglfloat(0.0) );

        self.buf=eglint()
        opengles.glGenBuffers(1,ctypes.byref(self.buf))

        self.check()

        # Prepare a texture image
        self.tex=eglint()
        self.check()
        opengles.glGenTextures(1,ctypes.byref(self.tex))
        self.check()
        opengles.glBindTexture(GL_TEXTURE_2D,self.tex)
        self.check()

        opengles.glTexImage2D(GL_TEXTURE_2D,0,GL_RGB,1920,1080,0,GL_RGB,GL_UNSIGNED_SHORT_5_6_5,0)

        self.check()
        opengles.glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, eglfloat(GL_NEAREST))
        opengles.glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, eglfloat(GL_NEAREST))
        self.check()

        # Prepare a framebuffer for rendering
        self.tex_fb=eglint()
        opengles.glGenFramebuffers(1,ctypes.byref(self.tex_fb))
        self.check()
        opengles.glBindFramebuffer(GL_FRAMEBUFFER,self.tex_fb)
        self.check()
        opengles.glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,self.tex,0)
        self.check()
        opengles.glBindFramebuffer(GL_FRAMEBUFFER,0)
        self.check()
        # Prepare viewport
        opengles.glViewport ( 0, 0, egl.width, egl.height );
        self.check()

        # Upload vertex data to a buffer
        opengles.glBindBuffer(GL_ARRAY_BUFFER, self.buf);
        opengles.glBufferData(GL_ARRAY_BUFFER, ctypes.sizeof(self.vertex_data),
                             ctypes.byref(self.vertex_data), GL_STATIC_DRAW);
        opengles.glVertexAttribPointer(self.attr_vertex, 4, GL_FLOAT, 0, 16, 0);
        opengles.glEnableVertexAttribArray(self.attr_vertex);
        self.check()

    def draw_triangles(self,scale=0.0005,offset=(0.2,0.3)):

        # Now render to the main frame buffer
        opengles.glBindFramebuffer(GL_FRAMEBUFFER,0)
        # Clear the background (not really necessary I suppose)
        opengles.glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        self.check()

        opengles.glBindBuffer(GL_ARRAY_BUFFER, self.buf);
        self.check()
        opengles.glUseProgram ( self.program );
        self.check()
        opengles.glBindTexture(GL_TEXTURE_2D,self.tex)
        self.check()
        opengles.glUniform4f(self.unif_color, eglfloat(0.4), eglfloat(0.4), eglfloat(0.4), eglfloat(0.2))
        self.check()
        opengles.glUniform2f(self.unif_scale, eglfloat(scale), eglfloat(scale));
        self.check()
        opengles.glUniform2f(self.unif_offset, eglfloat(offset[0]), eglfloat(offset[1]));
        self.check()
        opengles.glUniform1i(self.unif_tex, 0); # I don't really understand this part, perhaps it relates to active texture?
        self.check()

        if (self.offset>=0.8):
            self.offset_direction = -0.04
            self.canFinish = True
        elif (self.offset<=0.001 and self.canFinish):
            self.finished = True

        self.offset += self.offset_direction

        opengles.glUniform1f(self.unif_utime, eglfloat(self.offset));
        self.check()

        opengles.glDrawArrays ( GL_TRIANGLE_FAN, 0, 4 );
        self.check()

        opengles.glBindBuffer(GL_ARRAY_BUFFER, 0);

        opengles.glFlush()
        opengles.glFinish()
        self.check()

        openegl.eglSwapBuffers(egl.display, egl.surface);
        self.check()

    def check(self):
        e=opengles.glGetError()
        if e:
            print hex(e)
            raise ValueError

def showerror():
    e=opengles.glGetError()
    print hex(e)

egl = EGL()
d = demo()

def doPlay():
    while 1:
        d.draw_triangles(0.005)
        if (d.finished):
            break

        time.sleep(0.01)

    # Now render to the main frame buffer
    opengles.glBindFramebuffer(GL_FRAMEBUFFER,0)
    # Clear the background (not really necessary I suppose)
    opengles.glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
    opengles.glFlush()
    opengles.glFinish()
    openegl.eglSwapBuffers(egl.display, egl.surface)

    showerror()

def play():
    d.offset = 0
    d.offset_direction = 0.2
    d.finished = False
    d.canFinish = False
    doPlay()
    # t = Thread(target=doPlay)
    # t.start()

if __name__ == "__main__":
    play()
