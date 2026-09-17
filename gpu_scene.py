"""Offscreen multisampled OpenGL geometry, embedded in the existing Tk Canvas."""
from array import array
from functools import lru_cache
import math
import moderngl
from PIL import Image
from smooth_canvas import SmoothScene

@lru_cache(maxsize=4096)
def rgb(color):
    return tuple(int(color[i:i+2],16)/255 for i in (1,3,5))

class GpuScene(SmoothScene):
    gpu_glow=True
    def __init__(self,widget):
        super().__init__(widget)
        self.ctx=moderngl.create_standalone_context(require=330)
        self.renderer=self.ctx.info.get('GL_RENDERER','OpenGL')
        self.program=self.ctx.program(vertex_shader='''#version 330
            in vec2 position; in vec3 color; out vec3 shade; uniform vec2 viewport;
            void main(){gl_Position=vec4(position.x*2/viewport.x-1,1-position.y*2/viewport.y,0,1);shade=color;}''',
            fragment_shader='''#version 330
            in vec3 shade; out vec4 pixel;
            void main(){pixel=vec4(shade,1);}''')
        self.buffer=self.ctx.buffer(reserve=4*1024*1024,dynamic=True)
        self.vao=self.ctx.vertex_array(self.program,[(self.buffer,'2f 3f','position','color')])
        self.linebuffer=self.ctx.buffer(reserve=2*1024*1024,dynamic=True)
        self.linevao=self.ctx.vertex_array(self.program,[(self.linebuffer,'2f 3f','position','color')])
        self.fbo=self.resolve=self.colorbuffer=self.texture=None
        self.size=None
        self.glow_key=None
        self.glow_vertices=None
    def delete(self,*args):
        self.width=max(300,self.winfo_width())
        self.height=int(self.widget['height'])
        self.offset=(self.widget.winfo_width()-self.width)/2
        self.texts=[]
        self.vertices=array('f')
        self.lines=array('f')
        if self.size!=(self.width,self.height):
            for obj in (self.fbo,self.resolve,self.colorbuffer,self.texture):
                if obj: obj.release()
            self.size=(self.width,self.height)
            samples=min(4,self.ctx.max_samples)
            self.colorbuffer=self.ctx.renderbuffer(self.size,components=3,samples=samples)
            self.fbo=self.ctx.framebuffer(color_attachments=[self.colorbuffer])
            self.texture=self.ctx.texture(self.size,3)
            self.resolve=self.ctx.framebuffer(color_attachments=[self.texture])
        self.fbo.use()
        self.ctx.viewport=(0,0,self.width,self.height)
        self.program['viewport'].value=self.size
        self.fbo.clear(5/255,11/255,16/255)
    def vertex(self,x,y,color):
        self.vertices.extend((x,y,*color))
    def triangle(self,a,b,c,color):
        for x,y in (a,b,c): self.vertex(x,y,color)
    def create_rectangle(self,x1,y1,x2,y2,fill=None,outline=None,**kw):
        if fill:
            color=rgb(fill)
            self.triangle((x1,y1),(x2,y1),(x2,y2),color)
            self.triangle((x1,y1),(x2,y2),(x1,y2),color)
    def create_line(self,*xy,fill=None,width=1,**kw):
        color=rgb(fill)
        for i in range(0,len(xy)-2,2):
            x,y,xx,yy=xy[i:i+4]
            self.lines.extend((x,y,*color,xx,yy,*color))
    def create_oval(self,x1,y1,x2,y2,fill=None,outline=None,width=1,**kw):
        cx,cy=(x1+x2)/2,(y1+y2)/2
        rx,ry=(x2-x1)/2,(y2-y1)/2
        steps=max(12,min(80,int(max(rx,ry)*2)))
        points=[(cx+rx*math.cos(i*math.tau/steps),cy+ry*math.sin(i*math.tau/steps)) for i in range(steps+1)]
        if fill:
            color=rgb(fill)
            for a,b in zip(points,points[1:]): self.triangle((cx,cy),a,b,color)
        if outline: self.create_line(*(v for p in points for v in p),fill=outline,width=width)
    def create_arc(self,x1,y1,x2,y2,start=0,extent=0,outline=None,width=1,**kw):
        cx,cy=(x1+x2)/2,(y1+y2)/2
        rx,ry=(x2-x1)/2,(y2-y1)/2
        steps=max(8,int(abs(extent)/3))
        points=[(cx+rx*math.cos(math.radians(start+extent*i/steps)),cy-ry*math.sin(math.radians(start+extent*i/steps))) for i in range(steps+1)]
        self.create_line(*(v for p in points for v in p),fill=outline,width=width)
    def create_glow(self,cx,cy,r,color,energy):
        key=(cx,cy,r,color,round(energy,2))
        if key==self.glow_key:
            self.vertices.extend(self.glow_vertices)
            return
        start=len(self.vertices)
        outer=rgb('#07131a')
        light=rgb(color)
        # Continuous per-vertex gradient avoids nested-disc banding and overdraw.
        for ring in range(18):
            for i in range(48):
                corners=[]
                for rad,angle in ((ring,i),(ring+1,i),(ring+1,i+1),(ring,i+1)):
                    u=rad/18
                    power=(1-u)**3*(.65+.2*energy)
                    shade=tuple(a+(b-a)*power for a,b in zip(outer,light))
                    corners.append((cx+r*u*math.cos(angle*math.tau/48),cy+r*u*math.sin(angle*math.tau/48),shade))
                for index in (0,1,2,2,3,0): self.vertex(*corners[index])
        self.glow_key=key
        self.glow_vertices=self.vertices[start:]
    def present(self):
        payload=self.vertices.tobytes()
        if len(payload)>self.buffer.size:
            raise RuntimeError('Geometry budget exceeded')
        self.buffer.write(payload)
        self.vao.render(moderngl.TRIANGLES,vertices=len(self.vertices)//5)
        self.linebuffer.write(self.lines.tobytes())
        self.linevao.render(moderngl.LINES,vertices=len(self.lines)//5)
        self.ctx.copy_framebuffer(self.resolve,self.fbo)
        image=Image.frombytes('RGB',self.size,self.resolve.read(components=3,alignment=1)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        self.last_image=image
        self.present_image(image)
    def release(self):
        for obj in (self.vao,self.linevao,self.buffer,self.linebuffer,self.program,self.fbo,self.resolve,self.colorbuffer,self.texture):
            if obj: obj.release()
        self.ctx.release()
