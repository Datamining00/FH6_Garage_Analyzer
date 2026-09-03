from __future__ import annotations
import math
import numpy as np
try:
    from OpenGL import GL
except ImportError:
    GL = None
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from .glb_parser import GlbSceneData, GlbViewerError
from .direct_livery import DirectLiveryTextures

def _perspective(fovy_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    out = np.zeros((4, 4), dtype=np.float32)
    out[0, 0] = f / max(aspect, 1e-06)
    out[1, 1] = f
    out[2, 2] = (far + near) / (near - far)
    out[2, 3] = 2.0 * far * near / (near - far)
    out[3, 2] = -1.0
    return out

def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    f = target - eye
    f /= max(float(np.linalg.norm(f)), 1e-08)
    s = np.cross(f, up)
    if np.linalg.norm(s) < 1e-08:
        up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        s = np.cross(f, up)
    s /= max(float(np.linalg.norm(s)), 1e-08)
    u = np.cross(s, f)
    out = np.eye(4, dtype=np.float32)
    out[0, :3] = s
    out[1, :3] = u
    out[2, :3] = -f
    out[0, 3] = -np.dot(s, eye)
    out[1, 3] = -np.dot(u, eye)
    out[2, 3] = np.dot(f, eye)
    return out

def _projection_bounds(scene_data: GlbSceneData, livery: DirectLiveryTextures | None):
    if livery is None:
        return (np.zeros((11, 2), dtype=np.float32), np.ones((11, 2), dtype=np.float32), np.zeros(11, dtype=np.float32))
    return (np.ascontiguousarray(scene_data.projection_minimum, dtype=np.float32), np.ascontiguousarray(scene_data.projection_maximum, dtype=np.float32), np.ascontiguousarray(scene_data.projection_valid, dtype=np.float32))

class CarOpenGLWidget(QOpenGLWidget):
    load_failed = Signal(str)

    def __init__(self, scene_data: GlbSceneData, livery_textures: DirectLiveryTextures | None=None, parent=None) -> None:
        super().__init__(parent)
        self.scene_data = scene_data
        self.livery_textures = livery_textures
        self._livery_enabled = livery_textures is not None
        self._debug_sections = False
        self._livery_texture = 0
        self._livery_mask_textures = [0, 0, 0]
        self._projection_minimum, self._projection_maximum, self._projection_valid = _projection_bounds(scene_data, livery_textures)
        self._two_sided = False
        self.setMinimumSize(800, 520)
        self.setFocusPolicy(Qt.StrongFocus)
        self._program = 0
        self._vao = 0
        self._vbo = 0
        self._ebo = 0
        self._last_pos = QPoint()
        self._yaw = 35.0
        self._pitch = 18.0
        self._distance = 1.0
        self._home_target = (scene_data.bounds_min + scene_data.bounds_max) * 0.5
        self._target = self._home_target.copy()
        size = scene_data.bounds_max - scene_data.bounds_min
        self._radius = max(float(np.linalg.norm(size)) * 0.55, 0.5)
        self.reset_camera()

    def reset_camera(self) -> None:
        self._yaw = 35.0
        self._pitch = 18.0
        self._distance = self._radius * 2.2
        self._target = self._home_target.copy()
        self.update()

    def initializeGL(self) -> None:
        try:
            if GL is None:
                raise GlbViewerError('PyOpenGL is not installed.')
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_CULL_FACE)
            GL.glCullFace(GL.GL_BACK)
            GL.glClearColor(0.5294118, 0.8078431, 0.9215686, 1.0)
            vertex = '''
#version 330 core
layout(location=0) in vec3 inPosition;
layout(location=1) in vec3 inNormal;
layout(location=2) in vec3 inColor;
layout(location=3) in vec2 inUV3;
layout(location=4) in float inAllowed;
layout(location=5) in float inProjection;
layout(location=6) in float inDirectUv;
uniform mat4 uMVP;
uniform mat4 uModel;
out vec3 vNormal;
out vec3 vColor;
out vec3 vWorld;
out vec2 vUV3;
flat out int vAllowed;
flat out int vProjection;
flat out int vDirectUv;
void main(){vec4 world=uModel*vec4(inPosition,1.0);vWorld=world.xyz;vNormal=normalize(mat3(uModel)*inNormal);vColor=inColor;vUV3=inUV3;vAllowed=int(floor(inAllowed+0.5));vProjection=int(floor(inProjection+0.5));vDirectUv=int(floor(inDirectUv+0.5));gl_Position=uMVP*vec4(inPosition,1.0);}
'''
            fragment = '''
#version 330 core
in vec3 vNormal;in vec3 vColor;in vec3 vWorld;in vec2 vUV3;flat in int vAllowed;flat in int vProjection;flat in int vDirectUv;
uniform vec3 uEye;uniform bool uLiveryEnabled;uniform int uValidMask;uniform sampler2D uLivery;uniform sampler2D uMask0;uniform sampler2D uMask1;uniform sampler2D uMask2;uniform vec4 uSourceRegions[11];uniform vec4 uPaintRegions[11];uniform vec4 uProjectionAxes[11];uniform vec4 uProjectionMaskRegions[11];uniform vec2 uProjectionMinimum[11];uniform vec2 uProjectionMaximum[11];uniform float uProjectionValid[11];out vec4 fragColor;
vec3 facing(int s){if(s==0||s==6)return vec3(0,0,1);if(s==1||s==7)return vec3(0,0,-1);if(s==2||s==5||s==8)return vec3(0,1,0);if(s==3||s==9)return vec3(1,0,0);return vec3(-1,0,0);}
float cov(int s,vec4 a,vec4 b,vec4 c){if(s==0)return a.r;if(s==1)return a.g;if(s==2)return a.b;if(s==3)return a.a;if(s==4)return b.r;if(s==5)return b.g;if(s==6)return b.b;if(s==7)return b.a;if(s==8)return c.r;if(s==9)return c.g;return c.b;}
int geo(int s){if(s==3)return 4;if(s==4)return 3;if(s==9)return 10;if(s==10)return 9;return s;}
float axis(vec3 v,float a){if(a<0.5)return v.x;if(a<1.5)return v.y;return v.z;}
void main(){vec3 N=normalize(vNormal);vec3 L=normalize(vec3(0.45,0.85,0.55));float d=max(dot(N,L),0.0);vec3 V=normalize(uEye-vWorld);float rim=pow(1.0-max(dot(N,V),0.0),3.0);vec3 base=vColor*(0.34+0.66*d)+vec3(0.08,0.11,0.14)*rim;
vec2 atlas=vec2(vUV3.x*0.5,vUV3.y),best=atlas;float bestCov=0.0;int bestSlot=-1;if(uLiveryEnabled&&vAllowed!=0){for(int s=0;s<11;++s){int bit=1<<s;if((vAllowed&bit)==0||(uValidMask&bit)==0)continue;if(dot(N,facing(s))<=0.0)continue;vec2 uv=atlas;if(vDirectUv==0){int gb=1<<geo(s);if((vProjection&gb)==0||uProjectionValid[s]<0.5)continue;vec4 ax=uProjectionAxes[s];vec2 mn=uProjectionMinimum[s],rg=uProjectionMaximum[s]-mn;if(rg.x<=0.000001||rg.y<=0.000001)continue;vec2 av=vec2(axis(vWorld,ax.x)*ax.z,axis(vWorld,ax.y)*ax.w);vec2 n=(av-mn)/rg;vec4 mr=uProjectionMaskRegions[s];uv=vec2(mix(mr.x,mr.y,n.x),mix(mr.z,mr.w,n.y));}if(uv.x<0.0||uv.x>1.0||uv.y<0.0||uv.y>1.0)continue;float c=cov(s,texture(uMask0,uv),texture(uMask1,uv),texture(uMask2,uv));if(c>bestCov){bestCov=c;bestSlot=s;best=uv;}}}
vec4 decal=vec4(0.0);if(bestSlot>=0&&bestCov>0.0){vec4 src=uSourceRegions[bestSlot];vec2 sz=src.zw-src.xy;if(sz.x>0.000001&&sz.y>0.000001){vec2 section=clamp((best-src.xy)/sz,0.0,1.0);vec4 p=uPaintRegions[bestSlot];decal=texture(uLivery,mix(p.xy,p.zw,section));decal.a*=bestCov;}}fragColor=vec4(mix(base,decal.rgb,decal.a),1.0);}
'''
            self._program = self._make_program(vertex, fragment)
            packed = np.ascontiguousarray(np.concatenate((self.scene_data.positions, self.scene_data.normals, self.scene_data.colors, self.scene_data.uv3, self.scene_data.allowed_sides, self.scene_data.projection_sides, self.scene_data.direct_uv), axis=1), dtype=np.float32)
            self._vao = GL.glGenVertexArrays(1); self._vbo = GL.glGenBuffers(1); self._ebo = GL.glGenBuffers(1)
            GL.glBindVertexArray(self._vao)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo); GL.glBufferData(GL.GL_ARRAY_BUFFER, packed.nbytes, packed, GL.GL_STATIC_DRAW)
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self._ebo); GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, self.scene_data.indices.nbytes, self.scene_data.indices, GL.GL_STATIC_DRAW)
            stride = 14 * 4
            for location, size, offset in ((0,3,0),(1,3,12),(2,3,24),(3,2,36),(4,1,44),(5,1,48),(6,1,52)):
                GL.glEnableVertexAttribArray(location); GL.glVertexAttribPointer(location,size,GL.GL_FLOAT,GL.GL_FALSE,stride,GL.GLvoidp(offset))
            GL.glBindVertexArray(0)
            if self.livery_textures is not None:
                paint=self.livery_textures.paint; expected=int(self.livery_textures.canvas_size[0])
                if paint.ndim!=3 or paint.shape[0]<=0 or paint.shape[1]!=expected or paint.shape[2]!=4 or paint.dtype!=np.uint8:
                    raise GlbViewerError('Paint atlas has an invalid shape or format.')
                max_texture_size=int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_SIZE))
                if int(paint.shape[1])>max_texture_size or int(paint.shape[0])>max_texture_size:
                    raise GlbViewerError(f'Paint atlas {paint.shape[1]}x{paint.shape[0]} exceeds GL_MAX_TEXTURE_SIZE={max_texture_size}.')
                self._livery_texture=GL.glGenTextures(1); GL.glBindTexture(GL.GL_TEXTURE_2D,self._livery_texture)
                for pname,pvalue in ((GL.GL_TEXTURE_MIN_FILTER,GL.GL_LINEAR),(GL.GL_TEXTURE_MAG_FILTER,GL.GL_LINEAR),(GL.GL_TEXTURE_WRAP_S,GL.GL_CLAMP_TO_EDGE),(GL.GL_TEXTURE_WRAP_T,GL.GL_CLAMP_TO_EDGE)): GL.glTexParameteri(GL.GL_TEXTURE_2D,pname,pvalue)
                GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT,1); GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA8,int(paint.shape[1]),int(paint.shape[0]),0,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE,paint); GL.glBindTexture(GL.GL_TEXTURE_2D,0)
                pages=self.livery_textures.mask_pages
                if pages.shape!=(3,1024,2048,4) or pages.dtype!=np.uint8: raise GlbViewerError('Native mask pages have an invalid shape or format.')
                self._livery_mask_textures=list(GL.glGenTextures(3))
                for page_index, texture_id in enumerate(self._livery_mask_textures):
                    GL.glBindTexture(GL.GL_TEXTURE_2D,texture_id)
                    for pname,pvalue in ((GL.GL_TEXTURE_MIN_FILTER,GL.GL_LINEAR),(GL.GL_TEXTURE_MAG_FILTER,GL.GL_LINEAR),(GL.GL_TEXTURE_WRAP_S,GL.GL_CLAMP_TO_EDGE),(GL.GL_TEXTURE_WRAP_T,GL.GL_CLAMP_TO_EDGE)): GL.glTexParameteri(GL.GL_TEXTURE_2D,pname,pvalue)
                    GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT,1); GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA8,2048,1024,0,GL.GL_RGBA,GL.GL_UNSIGNED_BYTE,pages[page_index])
                GL.glBindTexture(GL.GL_TEXTURE_2D,0)
        except Exception as exc:
            self.load_failed.emit(str(exc))

    @staticmethod
    def _compile_shader(source: str, shader_type: int) -> int:
        shader=GL.glCreateShader(shader_type); GL.glShaderSource(shader,source); GL.glCompileShader(shader)
        if GL.glGetShaderiv(shader,GL.GL_COMPILE_STATUS)!=GL.GL_TRUE:
            log=GL.glGetShaderInfoLog(shader).decode('utf-8','replace'); GL.glDeleteShader(shader); raise GlbViewerError('OpenGL shader compile failed: '+log)
        return shader

    @classmethod
    def _make_program(cls, vertex: str, fragment: str) -> int:
        vs=cls._compile_shader(vertex,GL.GL_VERTEX_SHADER); fs=cls._compile_shader(fragment,GL.GL_FRAGMENT_SHADER); program=GL.glCreateProgram(); GL.glAttachShader(program,vs); GL.glAttachShader(program,fs); GL.glLinkProgram(program); GL.glDeleteShader(vs); GL.glDeleteShader(fs)
        if GL.glGetProgramiv(program,GL.GL_LINK_STATUS)!=GL.GL_TRUE:
            log=GL.glGetProgramInfoLog(program).decode('utf-8','replace'); GL.glDeleteProgram(program); raise GlbViewerError('OpenGL shader link failed: '+log)
        return program

    def _eye(self) -> np.ndarray:
        yaw=math.radians(self._yaw); pitch=math.radians(self._pitch); cp=math.cos(pitch); direction=np.array([math.sin(yaw)*cp,math.sin(pitch),math.cos(yaw)*cp],dtype=np.float32); return self._target+direction*self._distance

    def paintGL(self) -> None:
        GL.glClear(GL.GL_COLOR_BUFFER_BIT|GL.GL_DEPTH_BUFFER_BIT)
        if not self._program or not self._vao: return
        width=max(self.width(),1); height=max(self.height(),1); eye=self._eye(); view=_look_at(eye,self._target.astype(np.float32),np.array([0.0,1.0,0.0],dtype=np.float32)); proj=_perspective(36.0,width/height,max(self._radius/200.0,0.01),self._radius*50.0); model=np.eye(4,dtype=np.float32); mvp=proj@view@model
        GL.glUseProgram(self._program); GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._program,'uMVP'),1,GL.GL_TRUE,mvp); GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._program,'uModel'),1,GL.GL_TRUE,model); GL.glUniform3f(GL.glGetUniformLocation(self._program,'uEye'),float(eye[0]),float(eye[1]),float(eye[2])); GL.glUniform1i(GL.glGetUniformLocation(self._program,'uLiveryEnabled'),int(self._livery_enabled and self._livery_texture!=0 and all(self._livery_mask_textures)))
        valid_mask=0
        if self.livery_textures is not None:
            for i,value in enumerate(self.livery_textures.valid_slots):
                if value: valid_mask|=1<<i
            GL.glUniform4fv(GL.glGetUniformLocation(self._program,'uSourceRegions[0]'),11,self.livery_textures.source_regions); GL.glUniform4fv(GL.glGetUniformLocation(self._program,'uPaintRegions[0]'),11,self.livery_textures.paint_regions); GL.glUniform4fv(GL.glGetUniformLocation(self._program,'uProjectionAxes[0]'),11,self.livery_textures.projection_axes); GL.glUniform4fv(GL.glGetUniformLocation(self._program,'uProjectionMaskRegions[0]'),11,self.livery_textures.projection_mask_regions); GL.glUniform2fv(GL.glGetUniformLocation(self._program,'uProjectionMinimum[0]'),11,self._projection_minimum); GL.glUniform2fv(GL.glGetUniformLocation(self._program,'uProjectionMaximum[0]'),11,self._projection_maximum); GL.glUniform1fv(GL.glGetUniformLocation(self._program,'uProjectionValid[0]'),11,self._projection_valid)
        GL.glUniform1i(GL.glGetUniformLocation(self._program,'uValidMask'),valid_mask)
        if self._livery_texture:
            GL.glActiveTexture(GL.GL_TEXTURE0); GL.glBindTexture(GL.GL_TEXTURE_2D,self._livery_texture); GL.glUniform1i(GL.glGetUniformLocation(self._program,'uLivery'),0)
        for page_index,texture_id in enumerate(self._livery_mask_textures):
            if texture_id:
                GL.glActiveTexture(GL.GL_TEXTURE1+page_index); GL.glBindTexture(GL.GL_TEXTURE_2D,texture_id); GL.glUniform1i(GL.glGetUniformLocation(self._program,f'uMask{page_index}'),1+page_index)
        GL.glBindVertexArray(self._vao); GL.glDrawElements(GL.GL_TRIANGLES,int(len(self.scene_data.indices)),GL.GL_UNSIGNED_INT,None); GL.glBindVertexArray(0)
        for unit in (3,2,1,0): GL.glActiveTexture(GL.GL_TEXTURE0+unit); GL.glBindTexture(GL.GL_TEXTURE_2D,0)
        GL.glActiveTexture(GL.GL_TEXTURE0); GL.glUseProgram(0)

    def resizeGL(self,width:int,height:int)->None: GL.glViewport(0,0,max(width,1),max(height,1))
    def mousePressEvent(self,event)->None: self._last_pos=event.position().toPoint(); super().mousePressEvent(event)
    def mouseMoveEvent(self,event)->None:
        pos=event.position().toPoint(); delta=pos-self._last_pos; self._last_pos=pos; pan_mode=bool(event.buttons()&Qt.RightButton) or (bool(event.buttons()&Qt.LeftButton) and bool(event.modifiers()&Qt.ShiftModifier))
        if pan_mode:
            eye=self._eye(); forward=self._target-eye; forward/=max(float(np.linalg.norm(forward)),1e-08); world_up=np.array([0.0,1.0,0.0],dtype=np.float32); right=np.cross(forward,world_up); right/=max(float(np.linalg.norm(right)),1e-08); up=np.cross(right,forward); up/=max(float(np.linalg.norm(up)),1e-08); scale=self._distance*0.0018; self._target+=right*(-delta.x()*scale)+up*(delta.y()*scale); self.update()
        elif event.buttons()&Qt.LeftButton:
            self._yaw-=delta.x()*0.45; self._pitch=max(-85.0,min(85.0,self._pitch+delta.y()*0.35)); self.update()
        super().mouseMoveEvent(event)
    def wheelEvent(self,event)->None:
        steps=event.angleDelta().y()/120.0; self._distance*=math.pow(0.88,steps); self._distance=max(self._radius*0.35,min(self._radius*8.0,self._distance)); self.update(); event.accept()
    def closeEvent(self,event)->None:
        try:
            self.makeCurrent()
            if GL is not None:
                if self._ebo: GL.glDeleteBuffers(1,[self._ebo])
                if self._vbo: GL.glDeleteBuffers(1,[self._vbo])
                if self._vao: GL.glDeleteVertexArrays(1,[self._vao])
                if self._livery_texture: GL.glDeleteTextures([self._livery_texture])
                for texture_id in self._livery_mask_textures:
                    if texture_id: GL.glDeleteTextures([texture_id])
                if self._program: GL.glDeleteProgram(self._program)
            self.doneCurrent()
        finally: super().closeEvent(event)

def configure_default_opengl_format() -> None:
    fmt=QSurfaceFormat(); fmt.setRenderableType(QSurfaceFormat.OpenGL); fmt.setVersion(3,3); fmt.setProfile(QSurfaceFormat.CoreProfile); fmt.setDepthBufferSize(24); fmt.setSamples(4); QSurfaceFormat.setDefaultFormat(fmt)
