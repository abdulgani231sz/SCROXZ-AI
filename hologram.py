"""Bounded native Canvas geometry; no external assets or GPU context required."""
import math

def blend(a,b,f):
    return '#'+''.join(f'{round(int(a[i:i+2],16)*(1-f)+int(b[i:i+2],16)*f):02x}' for i in (1,3,5))

def draw_hologram(c,t,phase,level):
    c.delete('all')
    w=max(300,c.winfo_width())
    h=int(c['height'])
    cx,cy=w/2,(h-84)/2+12
    r=min(w*.34,(h-84)*.44,230)
    energy=getattr(c,'energy',.55)
    color=getattr(c,'accent','#55e5ed')
    if phase=='ATTENTION': color='#f68b87'
    old=getattr(c,'display_color',color)
    color=blend(old,color,.13)
    c.display_color=color
    low=getattr(c,'low_quality',False)
    yaw=getattr(c,'yaw',0)
    pitch=getattr(c,'pitch',0)
    dim=blend('#050b10',color,.22)
    medium=blend('#050b10',color,.45)
    for y in range(0,h,24):
        c.create_rectangle(0,y,w,min(h,y+24),fill=blend('#050b10','#0a1920',.45*math.sin(math.pi*y/h)),outline='')
    for x in range(0,w,48): c.create_line(x,0,x,h,fill='#09161e')
    for y in range(0,h,48): c.create_line(0,y,w,y,fill='#09161e')
    for x,y,dx,dy in ((12,12,1,1),(w-12,12,-1,1),(12,h-12,1,-1),(w-12,h-12,-1,-1)):
        c.create_line(x+18*dx,y,x,y,x,y+12*dy,fill=medium)
    c.create_text(22,22,text='NEURAL VISUALIZATION',anchor='w',fill='#76939e',font=('Consolas',8))
    c.create_text(w-22,22,text='DRAG TO ROTATE',anchor='e',fill='#76939e',font=('Consolas',8))
    for i in range(8 if low else 20):
        a=i*2.399+t*.07
        rad=r*(1.2+(i%6)*.07)
        x,y=cx+math.cos(a)*rad,cy+math.sin(a)*rad*.65
        c.create_oval(x-1,y-1,x+1,y+1,fill=medium,outline='')
    # Simulated translucent glow made from concentric vector discs.
    if getattr(c,'gpu_glow',False):
        c.create_glow(cx,cy,r*.58,color,energy)
    else:
        for i in range(30,0,-1):
            rad=r*(.035+i*.018)*(1+.025*math.sin(t*2))
            light=(1-i/31)**2*(.5+.2*energy)
            c.create_oval(cx-rad,cy-rad,cx+rad,cy+rad,outline='',fill=blend('#07131a',color,light))
    cosy,siny,cosp,sinp=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
    def project(x,y,z):
        xx=x*cosy-z*siny
        zz=x*siny+z*cosy
        yy=y*cosp-zz*sinp
        zz=y*sinp+zz*cosp
        scale=600/(600+zz)
        return cx+xx*scale,cy+yy*scale,zz
    def path(points,bright=False):
        # Batch adjacent segments of equal depth shade into one Canvas polyline.
        # This avoids hundreds of Tcl crossings and Canvas objects each frame.
        run=[]
        pen=None
        for a,b in zip(points,points[1:]):
            shade=(medium if a[2]>0 else color) if bright else (dim if a[2]>0 else medium)
            if shade!=pen:
                if run: c.create_line(*run,fill=pen,width=1)
                run=[a[0],a[1]]
                pen=shade
            run.extend((b[0],b[1]))
        if run: c.create_line(*run,fill=pen,width=1)
    steps=72 if low else 112
    # Latitude and longitude geometry rotates separately from its orbital rings.
    for lat in (-.9,-.45,0,.45,.9):
        path([project(r*.64*math.cos(lat)*math.cos(i*math.tau/steps+t*.09),r*.64*math.sin(lat),r*.64*math.cos(lat)*math.sin(i*math.tau/steps+t*.09)) for i in range(steps+1)])
    for j in range(4 if low else 7):
        angle=j*math.pi/7+t*.09
        path([project(r*.64*math.cos(i*math.tau/steps)*math.cos(angle),r*.64*math.sin(i*math.tau/steps),r*.64*math.cos(i*math.tau/steps)*math.sin(angle)) for i in range(steps+1)])
    # A restrained neural lattice adds depth and detail inside the wire sphere.
    nodes=[]
    count=24 if low else 40
    for i in range(count):
        yy=1-2*(i+.5)/count
        radius=math.sqrt(1-yy*yy)
        a=i*2.399963+t*.09
        nodes.append((r*.63*radius*math.cos(a),r*.63*yy,r*.63*radius*math.sin(a)))
    for i,node in enumerate(nodes):
        p=project(*node)
        for other in nodes[i+1:]:
            if sum((a-b)**2 for a,b in zip(node,other))<(r*.39)**2:
                q=project(*other)
                c.create_line(p[0],p[1],q[0],q[1],fill=dim,width=.65)
        size=1.3 if p[2]<0 else .7
        c.create_oval(p[0]-size,p[1]-size,p[0]+size,p[1]+size,fill=medium if p[2]>0 else color,outline='')
    for ring in range(4):
        tilt=.4+ring*.53+math.sin(t*.14+ring)*.12
        spin=t*(.17 if ring%2 else -.12)+ring*.9
        points=[]
        for i in range(steps+1):
            a=i*math.tau/steps
            x=math.cos(a)*r
            y=math.sin(a)*r*math.cos(tilt)
            z=math.sin(a)*r*math.sin(tilt)
            points.append(project(x*math.cos(spin)+z*math.sin(spin),y,-x*math.sin(spin)+z*math.cos(spin)))
        path(points,bright=ring==1)
        # Continuous orbital position, not the old discrete vertex stepping.
        a=t*.6+ring*1.7
        x=math.cos(a)*r
        y=math.sin(a)*r*math.cos(tilt)
        z=math.sin(a)*r*math.sin(tilt)
        dot=project(x*math.cos(spin)+z*math.sin(spin),y,-x*math.sin(spin)+z*math.cos(spin))
        c.create_oval(dot[0]-5,dot[1]-5,dot[0]+5,dot[1]+5,fill=dim,outline='')
        c.create_oval(dot[0]-2,dot[1]-2,dot[0]+2,dot[1]+2,fill=color,outline='')
    for i in range(72):
        a=i*math.tau/72
        inner=r*1.12
        outer=inner+(5 if i%6==0 else 2)
        c.create_line(cx+inner*math.cos(a),cy+inner*math.sin(a),cx+outer*math.cos(a),cy+outer*math.sin(a),fill=medium if i%6==0 else dim)
    for i in range(3):
        rad=r*(.20+i*.035)
        c.create_arc(cx-rad,cy-rad,cx+rad,cy+rad,start=t*(12+i*4)+i*100,extent=100,style='arc',outline=color,width=1)
    c.create_oval(cx-4,cy-4,cx+4,cy+4,fill='#e1fcff',outline=color)
    names={'READY':'Standing by.','LISTENING':'Listening.','THINKING':'Thinking.','SPEAKING':'Speaking.','WORKING':'Executing / working.','ATTENTION':'Attention required.'}
    c.create_text(cx,h-64,text=names[phase],fill='#dcecf1',font=('Segoe UI',16,'bold'))
    note='Ready for your next command'
    if phase=='LISTENING': note='Measured microphone input'
    elif phase=='SPEAKING': note='Voice playback • decorative pulse'
    elif phase=='THINKING': note='Response in progress'
    elif phase=='WORKING': note='See execution feedback below'
    elif phase=='ATTENTION': note='See conversation for details'
    c.create_text(cx,h-39,text=note,fill='#76939e',font=('Segoe UI',9))
    # Mic energy is measured. Speaking movement is explicitly decorative.
    amp=min(1,level*14) if phase=='LISTENING' else (.3 if phase=='SPEAKING' else .04)
    for i in range(21):
        bar=1+9*amp*abs(math.sin(t*4+i*.6))
        x=cx-40+i*4
        c.create_line(x,h-18-bar,x,h-18+bar,fill=medium)
