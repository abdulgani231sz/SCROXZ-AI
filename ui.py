"""Native Tk command center. All commands delegate to the existing App pipeline."""
import time
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from languages import REPLY_LANGUAGES
from hologram import draw_hologram
from theme import BG, PANEL, BORDER, TEXT, MUTED, PROFILES, ThemeController
ACCENT=PROFILES['ION']
COLORS={'READY':ACCENT,'LISTENING':'#68edd1','THINKING':'#9cbdf5','SPEAKING':ACCENT,'WORKING':'#ffbf62','ATTENTION':'#f68b87'}

def state_for(status,busy,speaking):
    text=status.lower()
    if 'failed' in text or 'error' in text: return 'ATTENTION'
    if speaking: return 'SPEAKING'
    if 'recording now' in text or 'listening now' in text: return 'LISTENING'
    if any(word in text for word in ('thinking','understanding','streaming','transcribing','searching')): return 'THINKING'
    return 'WORKING' if busy else 'READY'

class CoreCanvas(tk.Canvas):
    def __init__(self,parent,reduced):
        super().__init__(parent,bg=BG,height=350,highlightthickness=1,highlightbackground=BORDER,takefocus=True)
        self.reduced=reduced
        self.phase='READY'
        self.level=0.
        self.accent=ACCENT
        self.energy=.55
        self.paused=False
        self.yaw=.4
        self.pitch=.35
        self.clock=0.
        self.last=time.monotonic()
        self.draw_ms=0.
        self.frame_ms=0.
        self.fps=0.
        self.low_quality=False
        self.failed=False
        self.timer=None
        self.drag_origin=None
        self.display_color=ACCENT
        self.smooth_scene=None
        self.gpu_unavailable=False
        self.precise_timer=False
        self.bind('<Destroy>',self.dispose,add='+')
        self.bind('<ButtonPress-1>',self.start_drag)
        self.bind('<B1-Motion>',self.drag)
        self.bind('<Left>',lambda e:self.rotate(-.12,0))
        self.bind('<Right>',lambda e:self.rotate(.12,0))
        self.bind('<Up>',lambda e:self.rotate(0,-.12))
        self.bind('<Down>',lambda e:self.rotate(0,.12))
        self.frame()
    def rotate(self,x,y):
        self.yaw+=x
        self.pitch=max(-1.4,min(1.4,self.pitch+y))
    def start_drag(self,event):
        self.focus_set()
        self.drag_origin=(event.x,event.y)
    def drag(self,event):
        if self.drag_origin:
            x,y=self.drag_origin
            self.rotate((event.x-x)*.008,(event.y-y)*.008)
            self.drag_origin=(event.x,event.y)
    def dispose(self,event):
        if event.widget is self:
            self.set_timer_precision(False)
        if event.widget is self and self.timer:
            self.after_cancel(self.timer)
            self.timer=None
        if event.widget is self and self.smooth_scene is not None:
            self.smooth_scene.release()
            self.smooth_scene=None
    def set_timer_precision(self,enabled):
        if enabled==self.precise_timer:
            return
        try:
            import ctypes
            clock=ctypes.windll.winmm
            if enabled:
                self.precise_timer=clock.timeBeginPeriod(1)==0
            else:
                clock.timeEndPeriod(1)
                self.precise_timer=False
        except (AttributeError,OSError):
            self.precise_timer=False
    def frame(self):
        now=time.monotonic()
        dt=min(.1,now-self.last)
        self.last=now
        visible=self.winfo_ismapped() and self.winfo_toplevel().state()!='iconic'
        moving=visible and not self.paused and not self.reduced.get()
        self.set_timer_precision(moving and not self.failed)
        if moving:
            self.frame_ms=dt*1000 if not self.frame_ms else self.frame_ms*.9+dt*100
            self.fps=1000/self.frame_ms if self.frame_ms else 0
            self.clock+=dt*(.25+self.energy*.75)
        else:
            self.fps=0.
            self.frame_ms=0.
        if visible:
            start=time.perf_counter()
            try:
                if not self.failed:
                    self.draw(self.clock)
            except Exception:
                self.failed=True
                self.delete('all')
                self.create_text(20,40,anchor='w',text='SCROXZ • Core rendering unavailable\nChat and voice remain available.',fill=TEXT,font=('Segoe UI',12))
            self.draw_ms=.9*self.draw_ms+.1*(time.perf_counter()-start)*1000
            if self.draw_ms>28: self.low_quality=True
            elif self.draw_ms<22: self.low_quality=False
        budget=33 if self.low_quality else 16
        self.timer=self.after(max(2,budget-int(self.draw_ms)) if moving and not self.failed else 200,self.frame)
    def draw(self,t):
        # Hardware antialiasing; preserve a lightweight native fallback.
        if hasattr(self,'tk') and not self.gpu_unavailable:
            try:
                from gpu_scene import GpuScene
                if self.smooth_scene is None:
                    self.smooth_scene=GpuScene(self)
                draw_hologram(self.smooth_scene,t,self.phase,self.level)
                self.smooth_scene.present()
                return
            except Exception:
                self.gpu_unavailable=True
                if self.smooth_scene is not None:
                    self.smooth_scene.release()
                    self.smooth_scene=None
        draw_hologram(self,t,self.phase,self.level)

def button(parent,text,command,primary=False):
    return ttk.Button(parent,text=text,command=command,style='Primary.TButton' if primary else 'TButton',takefocus=True)

def build_ui(app):
    app.title('SCROXZ AI — Neural command center')
    app.geometry(f'{min(1360,app.winfo_screenwidth()-60)}x{min(880,app.winfo_screenheight()-70)}')
    app.minsize(900,660)
    app.configure(bg=BG)
    style=ttk.Style(app)
    style.theme_use('clam')
    style.configure('TButton',background='#0d1d27',foreground=TEXT,bordercolor=BORDER,lightcolor=BORDER,darkcolor=BORDER,borderwidth=1,padding=(9,6),font=('Segoe UI',10))
    style.map('TButton',background=[('active','#193b46')],bordercolor=[('focus',ACCENT)],foreground=[('disabled',MUTED)])
    style.configure('Primary.TButton',background=ACCENT,foreground=BG,font=('Segoe UI',10,'bold'))
    style.configure('TCombobox',fieldbackground=PANEL,background=BORDER,foreground=TEXT,arrowcolor=TEXT,padding=4)
    style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',TEXT)])
    style.configure('TScale',background=PANEL,troughcolor=BORDER)
    style.configure('Vertical.TScrollbar',background=BORDER,troughcolor=PANEL,borderwidth=0,arrowsize=10)
    app.theme=ThemeController(app)
    outer=tk.Frame(app,bg=BG)
    outer.pack(fill='both',expand=True,padx=18,pady=12)
    header=tk.Frame(outer,bg=BG)
    header.pack(fill='x',pady=(0,10))
    tk.Label(header,text='[S]  S C R O X Z',bg=BG,fg=TEXT,font=('Segoe UI',17,'bold')).pack(side='left')
    tk.Label(header,textvariable=app.theme.connection,bg=BG,fg=MUTED,font=('Consolas',9)).pack(side='left',padx=20)
    def fullscreen(): app.attributes('-fullscreen',not bool(app.attributes('-fullscreen')))
    button(header,'Fullscreen · F11',fullscreen).pack(side='right',padx=(6,0))
    button(header,'Visuals',app.theme.show_controls).pack(side='right',padx=(6,0))
    button(header,'Pause / Resume',lambda:app.theme.paused.set(not app.theme.paused.get())).pack(side='right')
    app.bind('<F11>',lambda e:fullscreen())
    def escape(event):
        if app.attributes('-fullscreen'): app.attributes('-fullscreen',False)
        app.stop_voice()
    app.bind('<Escape>',escape)
    toolbar=tk.Frame(outer,bg=BG)
    toolbar.pack(fill='x',pady=(0,10))
    tk.Label(toolbar,text='Command center',bg=BG,fg=TEXT,font=('Segoe UI',16,'bold')).pack(side='left')
    menu_button=tk.Menubutton(toolbar,text='Workspace ▾',bg=PANEL,fg=TEXT,activebackground=BORDER,activeforeground=TEXT,padx=12,pady=6,takefocus=True)
    menu=tk.Menu(menu_button,tearoff=False,bg=PANEL,fg=TEXT)
    for label,fn in [('New conversation',app.new_chat),('AI settings',app.settings),('AI connection',app.gemini_setup),('Cancel unfinished task',app.cancel_task),('Documents',app.import_document),('Saved memory',app.memories),('Notes & reminders',app.organizer),('Analyze screen',app.screen),('Clear document index',app.clear_documents)]:
        menu.add_command(label=label,command=fn)
    menu_button.configure(menu=menu)
    menu_button.pack(side='left',padx=16)
    app.provider_label=tk.Label(toolbar,text='',bg=BG,fg=MUTED,font=('Consolas',9))
    app.provider_label.pack(side='right')
    hero=tk.Frame(outer,bg=BG,height=350)
    hero.pack(fill='x',pady=(0,10))
    hero.grid_columnconfigure(1,weight=1)
    hero.grid_rowconfigure(0,weight=1)
    def panel(parent): return tk.Frame(parent,bg=PANEL,highlightbackground=BORDER,highlightthickness=1,padx=12,pady=8)
    def title(parent,text): tk.Label(parent,text=text,bg=PANEL,fg=MUTED,font=('Consolas',9),anchor='w').pack(fill='x',pady=(3,9))
    left=panel(hero)
    left.configure(width=190)
    left.pack_propagate(False)
    left.grid(row=0,column=0,sticky='nsew',padx=(0,10))
    title(left,'SYSTEM TELEMETRY')
    tk.Label(left,textvariable=app.theme.metrics,bg=PANEL,fg=TEXT,font=('Consolas',10),justify='left',anchor='w').pack(fill='x')
    title(left,'CONFIGURED MODULES')
    tk.Label(left,textvariable=app.theme.modules,bg=PANEL,fg=MUTED,font=('Segoe UI',9),justify='left',anchor='w').pack(fill='x')
    app.core_canvas=CoreCanvas(hero,app.reduced_motion)
    app.core_canvas.grid(row=0,column=1,sticky='nsew')
    right=panel(hero)
    right.configure(width=218)
    right.pack_propagate(False)
    right.grid(row=0,column=2,sticky='nsew',padx=(10,0))
    app.theme.controls(right)
    title(right,'ACTIVITY STREAM')
    activity=ScrolledText(right,bg=PANEL,fg=MUTED,font=('Consolas',9),height=4,width=20,wrap='word',relief='flat',state='disabled')
    activity.pack(fill='both',expand=True)
    def update_activity(*args):
        activity.configure(state='normal')
        activity.delete('1.0','end')
        activity.insert('end',app.theme.activity.get())
        activity.configure(state='disabled')
        activity.see('end')
    app.theme.activity.trace_add('write',update_activity)
    app.status=tk.StringVar(value='Ready • select your model in AI settings')
    app.theme.traces.append((app.status,app.status.trace_add('write',app.theme.observe_status)))
    line=tk.Frame(outer,bg=BG)
    line.pack(fill='x',pady=(0,6))
    tk.Label(line,text='COMMAND CHANNEL / CONVERSATION',bg=BG,fg=MUTED,font=('Consolas',9)).pack(side='left')
    tk.Label(line,textvariable=app.status,bg=BG,fg=ACCENT,font=('Segoe UI',9)).pack(side='right')
    # Reserve controls at the bottom before allowing the conversation to expand.
    footer=tk.Frame(outer,bg=BG)
    footer.pack(side='bottom',fill='x')
    opts=tk.Frame(footer,bg=BG)
    opts.pack(fill='x',pady=(7,5))
    for label,var,fn in [('Live web (free search)',app.live_web,app.live_web_changed),('Fast microphone',app.fast_mic,None),('Automatic voice',app.auto_voice,app.automatic_voice_changed)]:
        tk.Checkbutton(opts,text=label,variable=var,command=fn,bg=BG,fg=MUTED,selectcolor=PANEL,activebackground=BG,activeforeground=TEXT,takefocus=True).pack(side='left',padx=(0,8))
    app.reply_choice=tk.StringVar(value=REPLY_LANGUAGES[app.config.get('reply_language','hinglish')])
    app.reply_selector=ttk.Combobox(opts,textvariable=app.reply_choice,values=list(REPLY_LANGUAGES.values()),state='readonly',width=24)
    app.reply_selector.pack(side='right')
    app.reply_selector.bind('<<ComboboxSelected>>',app.change_reply_language)
    entryframe=tk.Frame(footer,bg=PANEL,highlightbackground=BORDER,highlightthickness=1)
    entryframe.pack(fill='x')
    app.entry=tk.Entry(entryframe,bg=PANEL,fg=TEXT,insertbackground=ACCENT,relief='flat',font=('Segoe UI',12))
    app.entry.pack(side='left',fill='x',expand=True,padx=12,ipady=9)
    app.entry.bind('<Return>',lambda e:app.send())
    button(entryframe,'Execute ↗',app.send,True).pack(side='right',padx=5,pady=5)
    voice=tk.Frame(footer,bg=BG)
    voice.pack(fill='x',pady=(7,0))
    app.voice_button=button(voice,'Start hands-free',app.toggle_voice,True)
    app.voice_button.pack(side='left')
    button(voice,'Mic',app.microphone).pack(side='left',padx=5)
    app.speak_button=button(voice,'Speak',app.speak)
    app.speak_button.pack(side='left')
    button(voice,'Test voice',app.test_voice).pack(side='left',padx=5)
    button(voice,'Cancel task',app.cancel_task).pack(side='left')
    button(voice,'Stop voice · Esc',app.stop_voice).pack(side='right')
    app.chat=ScrolledText(outer,wrap='word',bg=PANEL,fg=TEXT,font=('Segoe UI',11),relief='flat',padx=16,pady=10,height=3,state='disabled',insertbackground=ACCENT,spacing1=2,spacing3=4,selectbackground='#24505c')
    app.chat.pack(fill='both',expand=True)
    for role,color in [('you',ACCENT),('scroxz',TEXT),('system',MUTED),('sources',MUTED)]:
        app.chat.tag_configure(role,foreground=color,font=('Segoe UI',9,'bold'))
    def layout():
        wide=app.winfo_width()>=1180 and app.winfo_height()>=750 and not app.theme.focus.get()
        for widget in (left,right):
            if wide and not widget.winfo_manager(): widget.grid()
            elif not wide and widget.winfo_manager(): widget.grid_remove()
        hero_height=max(200,min(560,app.winfo_height()-(350 if app.winfo_height()>=820 else 405)))
        if int(app.core_canvas['height'])!=hero_height:
            app.core_canvas.configure(height=hero_height)
    app.layout_theme=layout
    app.bind('<Configure>',lambda e:layout() if e.widget is app else None,add='+')
    app.theme.apply()
    app.entry.focus_set()
