"""Visual preferences, measured telemetry and UI-only diagnostics."""
import ctypes
from ctypes import wintypes
import importlib.util
import json
import time
import tkinter as tk
from tkinter import ttk

BG='#050b10'
PANEL='#09131b'
BORDER='#193039'
TEXT='#dcecf1'
MUTED='#76939e'
PROFILES={'ION':'#55e5ed','SOLAR':'#ffbf62','VOID':'#b798ff'}

def preferences(config):
    value=config.get('visual',{})
    value=value if isinstance(value,dict) else {}
    energy=value.get('energy',.55)
    if not isinstance(energy,(float,int)) or not 0<=energy<=1:
        energy=.55
    return dict(profile=value.get('profile') if value.get('profile') in PROFILES else 'ION',
                energy=energy,paused=value.get('paused') is True,
                reduced=value.get('reduced') is True,focus=value.get('focus') is True)

class Telemetry:
    def __init__(self):
        self.previous=None
    def sample(self):
        cpu=memory='Unavailable'
        try:
            kernel=ctypes.windll.kernel32
            idle,kern,user=(wintypes.FILETIME() for _ in range(3))
            if kernel.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kern),ctypes.byref(user)):
                values=tuple((v.dwHighDateTime<<32)+v.dwLowDateTime for v in (idle,kern,user))
                if self.previous:
                    di,dk,du=(a-b for a,b in zip(values,self.previous))
                    if dk+du>0:
                        cpu=f'{max(0,min(100,100*(1-di/(dk+du)))):.0f}%'
                self.previous=values
            class Memory(ctypes.Structure):
                _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(name,ctypes.c_ulonglong) for name in ('total','available','page','freepage','virtual','freevirtual','extended')]
            mem=Memory()
            mem.length=ctypes.sizeof(mem)
            if kernel.GlobalMemoryStatusEx(ctypes.byref(mem)):
                memory=f'{(mem.total-mem.available)/2**30:.1f} / {mem.total/2**30:.1f} GB'
        except (AttributeError,OSError):
            pass
        return cpu,memory

class ThemeController:
    def __init__(self,app):
        self.app=app
        p=preferences(app.config)
        self.profile=tk.StringVar(app,value=p['profile'])
        self.energy=tk.DoubleVar(app,value=p['energy'])
        self.paused=tk.BooleanVar(app,value=p['paused'])
        self.focus=tk.BooleanVar(app,value=p['focus'])
        app.reduced_motion.set(p['reduced'])
        self.connection=tk.StringVar(app,value='AI connection • not checked')
        self.metrics=tk.StringVar(app,value='CPU  Sampling…\nRAM  Unavailable')
        self.modules=tk.StringVar(app,value='')
        self.diagnostic=tk.StringVar(app,value='Connection not checked')
        self.activity=tk.StringVar(app,value='Interface initialized')
        self.events=[]
        self.last_status=None
        self.scope=None
        self.telemetry=Telemetry()
        self.last_sample=0
        self.save_timer=None
        self.popup=None
        self.traces=[]
        for var in (self.profile,self.energy,self.paused,self.focus,app.reduced_motion):
            self.traces.append((var,var.trace_add('write',self.changed)))
        self.dependencies={name:importlib.util.find_spec(name) is not None for name in ('edge_tts','faster_whisper','sounddevice','ddgs')}
        app.bind('<Destroy>',self.dispose,add='+')
    def changed(self,*args):
        if hasattr(self.app,'core_canvas'):
            self.apply()
        if self.save_timer:
            self.app.after_cancel(self.save_timer)
        self.save_timer=self.app.after(350,self.save)
    def apply(self):
        c=self.app.core_canvas
        c.accent=PROFILES[self.profile.get()]
        c.energy=self.energy.get()
        c.paused=self.paused.get()
        ttk.Style(self.app).configure('Primary.TButton',background=c.accent)
        if hasattr(self.app,'layout_theme'):
            self.app.layout_theme()
    def save(self):
        self.save_timer=None
        # Merge into the current configuration; never replace provider settings.
        config=dict(self.app.config,visual=dict(profile=self.profile.get(),energy=self.energy.get(),
                    paused=self.paused.get(),reduced=self.app.reduced_motion.get(),focus=self.focus.get()))
        try:
            temp=self.app.config_path.with_suffix('.tmp')
            temp.write_text(json.dumps(config,indent=2),encoding='utf-8')
            temp.replace(self.app.config_path)
            self.app.config=config
        except OSError:
            self.diagnostic.set('Visual preferences could not be saved')
    def dispose(self,event):
        if event.widget is self.app:
            if self.save_timer:
                self.app.after_cancel(self.save_timer)
                self.save()
            for var,token in self.traces:
                var.trace_remove('write',token)
    def controls(self,parent):
        def label(text):
            tk.Label(parent,text=text,bg=PANEL,fg=MUTED,font=('Consolas',9),anchor='w').pack(fill='x',pady=(5,3))
        label('CORE CONFIGURATION')
        row=tk.Frame(parent,bg=PANEL)
        row.pack(fill='x')
        for name,color in PROFILES.items():
            tk.Radiobutton(row,text=name,value=name,variable=self.profile,indicatoron=False,bg=PANEL,
                           fg=color,selectcolor='#193039',activebackground=BORDER,activeforeground=TEXT,
                           font=('Consolas',9),padx=5,pady=5,relief='flat',takefocus=True).pack(side='left',expand=True,fill='x')
        label('Energy intensity')
        ttk.Scale(parent,from_=0,to=1,variable=self.energy,takefocus=True).pack(fill='x')
        for text,var in [('Pause animation',self.paused),('Reduced motion',self.app.reduced_motion),('Focus mode',self.focus)]:
            tk.Checkbutton(parent,text=text,variable=var,bg=PANEL,fg=TEXT,selectcolor=BORDER,
                           activebackground=PANEL,activeforeground=TEXT,anchor='w',takefocus=True).pack(fill='x')
        ttk.Button(parent,text='Check AI connection',command=self.diagnose).pack(fill='x',pady=(8,4))
        tk.Label(parent,textvariable=self.diagnostic,bg=PANEL,fg=MUTED,wraplength=185,justify='left',font=('Segoe UI',9)).pack(fill='x')
    def show_controls(self):
        if self.popup and self.popup.winfo_exists():
            self.popup.lift()
            return
        self.popup=tk.Toplevel(self.app)
        self.popup.title('SCROXZ • Visual controls')
        self.popup.configure(bg=PANEL)
        self.popup.geometry('290x390')
        self.controls(self.popup)
    def diagnose(self):
        if self.app.busy:
            self.diagnostic.set('Wait for the current task to finish')
            return
        from core import Brain
        config=dict(self.app.config)
        scope=tuple(config.get(k) for k in ('provider','base_url','model'))
        self.diagnostic.set('Checking model-list connection…')
        def job():
            start=time.monotonic()
            try:
                models=Brain(config).models()
                return models,time.monotonic()-start,None
            except Exception as exc:
                return [],time.monotonic()-start,str(exc)
        def done(result):
            if scope!=tuple(self.app.config.get(k) for k in ('provider','base_url','model')):
                return
            models,elapsed,error=result
            self.scope=scope
            self.connection.set('AI check failed' if error else 'AI reachable • model list verified')
            self.diagnostic.set(('Check failed • see conversation' if error else
                                 f'Model list: {len(models)} • {elapsed*1000:.0f} ms\nGeneration and audio not tested'))
            if error:
                self.app.status.set('Task failed • AI connection check')
                self.app.write('system',error)
        self.app.run(job,done,'Checking AI connection…')
    def record_connection(self,scope,success):
        if scope==tuple(self.app.config.get(k) for k in ('provider','base_url','model')):
            self.scope=scope
            self.connection.set('AI • last reply succeeded' if success else 'AI • last reply failed')
    def observe_status(self,*args):
        status=self.app.status.get()
        if status!=self.last_status:
            self.last_status=status
            self.events.append(time.strftime('%H:%M:%S')+'  '+status[:80])
            self.events=self.events[-4:]
            self.activity.set('\n\n'.join(self.events))
    def tick(self):
        scope=tuple(self.app.config.get(k) for k in ('provider','base_url','model'))
        if scope!=self.scope:
            self.scope=scope
            self.connection.set('AI connection • not checked')
        self.observe_status()
        now=time.monotonic()
        if now-self.last_sample<1:
            return
        self.last_sample=now
        cpu,ram=self.telemetry.sample()
        c=self.app.core_canvas
        backend='GPU • MSAA' if c.smooth_scene else 'Native fallback'
        self.metrics.set(f'CPU   {cpu}\n\nRAM   {ram}\n\nFrame {c.fps:.0f} FPS\n{backend}\n\nTemp  Unavailable')
        self.modules.set('AI  '+('Local' if self.app.config['provider']=='ollama' else 'Cloud')+' configuration\n\n'+
            'Voice  '+self.app.config.get('speech_engine','edge')+'\n'+
            ('  Installed voices / unchecked' if self.app.config.get('speech_engine')=='windows' else
             '  Package ready' if self.dependencies['edge_tts'] else '  Online package missing')+'\n\n'+
            'Mic  '+('Whisper installed' if self.dependencies['faster_whisper'] and self.dependencies['sounddevice'] else 'Package missing')+'\n\n'+
            'Web  '+('Enabled' if self.app.live_web.get() else 'Disabled')+('' if self.dependencies['ddgs'] else ' / missing package')+'\n\nMemory  Local SQLite')
