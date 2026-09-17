from __future__ import annotations
import io
import json
import os
from pathlib import Path
import queue
import threading
import time
from datetime import datetime
from assistant import AssistantStore, direct_plan, wants_action, infer_plan, describe, make_plan, run_approved_plan, validate_plan
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from core import Brain, Store, DEFAULTS, action_for, validate_config
from voice import Speaker, listen, input_devices
from speech_output import SpeechBuffer
from languages import REPLY_LANGUAGES
from gemini_setup import open_setup
from web_context import search_context, needs_web_search
from ui import build_ui, state_for
from credentials import restore_key

DATA_ROOT = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
LEGACY_DATA = DATA_ROOT / 'JarvisDesktop'
DATA = LEGACY_DATA if LEGACY_DATA.exists() else DATA_ROOT / 'SCROXZDesktop'
DB_NAME = 'jarvis.sqlite3' if DATA == LEGACY_DATA else 'scroxz.sqlite3'

class App(tk.Tk):
    def __init__(self):
        try:
            from smooth_canvas import enable_dpi_awareness
            enable_dpi_awareness()
        except ImportError:
            pass
        super().__init__()
        DATA.mkdir(parents=True, exist_ok=True)
        self.config_path = DATA/'config.json'
        key_error=None
        try:
            restore_key(self.config_path)
        except (OSError,RuntimeError) as exc:
            key_error=str(exc)
        self.config = dict(DEFAULTS)
        config_error = None
        if self.config_path.exists():
            try:
                self.config.update(json.loads(self.config_path.read_text(encoding='utf-8')))
                validate_config(self.config)
            except (ValueError, TypeError, OSError) as exc:
                self.config = dict(DEFAULTS)
                config_error = str(exc)
        self.store = Store(DATA/DB_NAME)
        self.assistant_store=AssistantStore(self.store)
        self.handsfree=False
        self.cloud_voice_scope=None
        self.capture_active=False
        self.pending_task=[]
        self.reminder_error=None
        self.dialog_active=False
        self.voice_generation=0
        self.voice_cancel=threading.Event()
        self.auto_voice=tk.BooleanVar(value=True)
        self.live_web=tk.BooleanVar(value=True)
        self.fast_mic=tk.BooleanVar(value=True)
        self.suppress_speech=False
        self.history, self.last_answer = [], ''
        self.events = queue.Queue()
        self.busy = False
        self.speaker = Speaker()
        self.online_speech_consent = None
        self.stream_speech = False
        self.speech_buffer = SpeechBuffer()
        self.reduced_motion=tk.BooleanVar(value=False)
        self.stream_active=False
        self.protocol('WM_DELETE_WINDOW', self.close)
        build_ui(self)
        self.write('system','SCROXZ AI online. Live web, Fast microphone and Automatic voice are enabled.\nLive web sends chat questions to public search engines; switch it off for private or offline questions. Ask a question or give me a task.')
        if config_error:
            self.write('system','Invalid configuration was not loaded. Open Settings to repair it: '+config_error)
        if key_error:
            self.write('system',key_error)
        self.after(80,self.poll)
        self.after(80,self.speech_tick)
        self.after(1000,self.voice_tick)
        self.after(1000,self.reminder_tick)
        self.after(150,self.visual_tick)
    def write(self,role,text):
        self.chat.configure(state='normal')
        self.chat.insert('end',role.upper()+'\n',role)
        self.chat.insert('end',text+'\n\n')
        self.chat.configure(state='disabled')
        self.chat.see('end')
    def run(self,job,done,label='Working…'):
        if self.busy:
            messagebox.showinfo('SCROXZ','Please wait for the current task.')
            return False
        self.busy = True
        self.status.set(label)
        def worker():
            try:
                self.events.put((done,job(),None))
            except Exception as exc:
                self.events.put((done,None,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        return True
    def poll(self):
        try:
            while True:
                done,result,error = self.events.get_nowait()
                if done == 'delta':
                    self.append_stream(result)
                    continue
                if done == 'status':
                    if isinstance(result,tuple) and result[0]=='level':
                        self.core_canvas.level=result[1]
                    else:
                        self.status.set(result)
                    continue
                if done == 'show':
                    self.deiconify()
                    continue
                if done == 'ai_connection':
                    if hasattr(self,'theme'):
                        self.theme.record_connection(*result)
                    continue
                self.busy = False
                self.status.set('Ready' if not error else 'Task failed • see details below')
                if error:
                    self.capture_active=False
                    self.end_stream()
                    self.stop_voice()
                    self.status.set('Task failed • see details below')
                    self.write('system',error)
                else:
                    try:
                        done(result)
                    except Exception as exc:
                        self.write('system',str(exc))
        except queue.Empty:
            pass
        self.after(80,self.poll)
    def consent(self,kind='prompt, recent chat history, saved memory and relevant document excerpts',voice_allowed=False):
        if self.config['provider']!='ollama':
            scope=tuple(self.config.get(k) for k in ('provider','base_url','model'))
            if voice_allowed and self.handsfree and self.cloud_voice_scope==scope:
                return True
            note=('Uses your Google project quota. Keep billing disabled for free use. Google may use free-tier content to improve products.'
                  if self.config['provider']=='gemini' else 'Provider usage charges may apply.')
            return self.ask('Send to cloud AI?',f'This sends {kind} to:\n{self.config["base_url"]}\n\n{note} Continue?')
        return True
    def send(self):
        self.submit(self.entry.get(), from_entry=True)
    def submit(self, text, from_entry=False):
        """Voice submissions never use or replace the user's editable draft."""
        if self.busy:
            return
        text = text.strip()
        if not text:
            return
        if len(text)>12000:
            messagebox.showerror('Message too long','Keep each message under 12,000 characters.')
            return
        self.reveal_pending()
        self.speaker.stop()
        self.suppress_speech=False
        if from_entry:
            self.entry.delete(0,'end')
        self.write('you',text)
        try:
            if text.lower().rstrip('.!') in ('/cancel', 'cancel task', 'never mind', 'nevermind'):
                self.cancel_task()
                return
            if text.startswith('/remember '):
                self.pending_task=[]
                if self.ask('Save memory?',text[10:]):
                    number = self.store.remember(text[10:])
                    self.write('system',f'Saved memory #{number}. Review or remove it in Saved memory.')
                return
            if text == '/help':
                self.write('system','/open notepad | calculator | paint\n/search <query> opens your browser\n/remember <text> saves explicit memory\n/cancel clears an unfinished task\n'
                    'Import document: text retrieval, not OCR.\nAnalyze screen: one screenshot, requires vision model.\n'
                    'Microphone: optional local Whisper, ends after a short pause, after model loads.\n'
                    'Natural requests: calculator kholo; YouTube kholo; note likho: finish assignment; 10 minute baad break yaad dilao.\n'
                    'Hands-free supports Ollama or Gemini with session consent. Esc stops voice.\n'
                    'No arbitrary shell commands or automatic file editing are enabled.')
                return
            plan=direct_plan(text)
            if plan:
                self.pending_task=[]
                self.receive_plan(plan,text)
                return
            action = action_for(text)
            if action:
                self.pending_task=[]
                kind,arg=action
                plan=make_plan([{'type':'open_app','app':arg}] if kind=='open' else [{'type':'search_web','query':arg}])
                self.receive_plan(plan,text)
                return
            if text.startswith('/'):
                self.write('system','Unknown command. Type /help.')
                return
            planning=bool(self.pending_task) or wants_action(text)
            disclosure=('your request and this unfinished task’s clarification exchange' if planning else
                        'prompt, recent chat history, saved memory and relevant document excerpts')
            if not self.consent(disclosure,voice_allowed=True):
                self.write('system','Cloud request cancelled.')
                return
            if planning:
                brain=Brain(self.config)
                pending=[dict(turn) for turn in self.pending_task]
                self.run(lambda:infer_plan(brain,text,pending),lambda plan:self.receive_plan(plan,text,planned=True), 'Understanding your request…')
                return
            self.chat_request(text)
        except Exception as exc:
            self.end_stream()
            self.write('system',str(exc))
    def chat_request(self,text):
        history = self.history+[{'role':'user','content':text}]
        brain = Brain(self.config)
        self.prepare_speech_stream()
        web_enabled=self.live_web.get() and needs_web_search(text)
        sources=[]
        def finished(answer):
            self.history=(history+[{'role':'assistant','content':answer}])[-12:]
            self.end_stream()
            self.last_answer=answer
            self.flush_speech(final=True)
            self.stream_speech=False
            if sources:
                self.write('sources',sources[0])
        def generate():
            started=time.monotonic()
            context=self.store.context(text)
            if web_enabled:
                self.events.put(('status','Searching live web…',None))
                web,links=search_context(text)
                context+='\n\n'+web
                sources.append(links)
                self.events.put(('status',f'Web ready in {time.monotonic()-started:.1f}s • waiting for AI…',None))
            scope=tuple(brain.config.get(k) for k in ('provider','base_url','model'))
            model_started=time.monotonic()
            first=True
            def delta(chunk):
                nonlocal first
                if first:
                    first=False
                    elapsed=time.monotonic()-model_started
                    self.events.put(('status',f'AI responding • first text {elapsed:.1f}s • preparing reply',None))
                self.events.put(('delta',chunk,None))
            try:
                answer=brain.chat_stream(history,context,
                    delta,
                    on_status=lambda status:self.events.put(('status',status,None)))
            except Exception:
                self.events.put(('ai_connection',(scope,False),None))
                raise
            self.events.put(('ai_connection',(scope,True),None))
            return answer
        self.begin_stream()
        self.run(generate,finished,'Thinking… • waiting for first words')
    def live_web_changed(self):
        if self.live_web.get() and not self.ask('Enable live web for this session?',
                'While enabled, each chat question is sent to public search engines. Search snippets and source links are sent to your selected AI. Memories and documents are not included in the search query. No search API key or paid grounding is used. Results may be incomplete or rate-limited. Enable?'):
            self.live_web.set(False)
    def cancel_task(self):
        if self.busy:
            return
        self.pending_task=[]
        self.write('system','Unfinished task cleared. You can start a new request.')
    def new_chat(self):
        if self.busy:
            return
        self.stop_voice()
        self.history=[]
        self.pending_task=[]
        self.last_answer=''
        self.chat.configure(state='normal')
        self.chat.delete('1.0','end')
        self.chat.configure(state='disabled')
        self.write('system','New conversation. Saved memories and document index remain available.')
    def settings(self):
        if self.busy:
            return
        win=tk.Toplevel(self)
        win.title('AI settings')
        win.geometry('700x810')
        win.transient(self)
        win.grab_set()
        fields={}
        labels={'provider':'Provider: ollama = local; gemini = Google; compatible = other cloud',
            'base_url':'Base URL (compatible should include /v1 if required)',
            'model':'Chat model name', 'vision_model':'Vision model name (optional)',
            'voice_language':'Microphone: auto, hi, hinglish or en',
            'reply_language':'Reply language: hi = Hindi, hinglish = हिंदी + English, en = English',
            'speech_engine':'Voice: edge = online Hindi/English; windows = installed offline voices',
            'speech_rate':'Speech speed: percentage change (0 = normal)',
            'recognition_model':'Recognition: small = higher accuracy; base = lighter CPU use',
            'microphone_device':'Microphone input device'}
        device_choices={'default':'default — Windows default input'}
        try:
            device_choices.update({index:index+' — '+name for index,name in input_devices()})
        except Exception:
            pass
        selected_device=self.config.get('microphone_device','default')
        device_choices.setdefault(selected_device,selected_device+' — unavailable device')
        for key,label in labels.items():
            tk.Label(win,text=label).pack(anchor='w',padx=20,pady=(10,2))
            fields[key]=tk.StringVar(value=self.config.get(key,DEFAULTS.get(key,'')))
            if key=='microphone_device':
                fields[key].set(device_choices[selected_device])
            choices={'provider':['ollama','gemini','compatible'], 'voice_language':['auto','hi','hinglish','en'],
                     'reply_language':list(REPLY_LANGUAGES), 'speech_engine':['edge','windows'],
                     'speech_rate':['-20','-10','0','10','20'],
                     'recognition_model':['small','base'],'microphone_device':list(device_choices.values())}
            if key in choices:
                values=choices[key]
                ttk.Combobox(win,textvariable=fields[key],values=values,state='readonly').pack(fill='x',padx=20)
            else:
                ttk.Entry(win,textvariable=fields[key]).pack(fill='x',padx=20)
        def get():
            values={key:value.get().strip() for key,value in fields.items()}
            values['microphone_device']=next(index for index,label in device_choices.items() if label==values['microphone_device'])
            return validate_config(dict(self.config,**values))
        def save():
            try:
                config=get()
                temp=self.config_path.with_suffix('.tmp')
                temp.write_text(json.dumps(config,indent=2),encoding='utf-8')
                temp.replace(self.config_path)
                self.stop_voice()
                self.config=config
                self.reply_choice.set(REPLY_LANGUAGES[config['reply_language']])
                self.online_speech_consent=None
                self.speaker.stop()
                self.pending_task=[]
                self.status.set('Ready • AI settings saved')
                win.destroy()
            except Exception as exc:
                messagebox.showerror('Settings',str(exc),parent=win)
        def check():
            try:
                brain=Brain(get())
                self.run(brain.models,lambda models:messagebox.showinfo('Available models','\n'.join(models) or 'No models found. Install a model in Ollama first.'), 'Checking models…')
            except Exception as exc:
                messagebox.showerror('Settings',str(exc),parent=win)
        ttk.Button(win,text='Check models',command=check).pack(side='left',padx=20,pady=14)
        ttk.Button(win,text='Save',command=save).pack(side='right',padx=20,pady=14)
    def gemini_setup(self):
        open_setup(self)
    def change_reply_language(self,event=None):
        if self.busy:
            self.reply_choice.set(REPLY_LANGUAGES[self.config.get('reply_language','hinglish')])
            return
        language=next(key for key,label in REPLY_LANGUAGES.items() if label==self.reply_choice.get())
        config=dict(self.config,reply_language=language)
        try:
            temp=self.config_path.with_suffix('.tmp')
            temp.write_text(json.dumps(config,indent=2),encoding='utf-8')
            temp.replace(self.config_path)
            self.config=config
            self.reveal_pending()
            self.speaker.stop()
            self.status.set('Reply language • '+REPLY_LANGUAGES[language])
        except OSError as exc:
            self.reply_choice.set(REPLY_LANGUAGES[self.config.get('reply_language','hinglish')])
            self.write('system','Could not save language: '+str(exc))
    def import_document(self):
        if self.busy:
            return
        path=filedialog.askopenfilename(filetypes=[('Documents','*.pdf *.txt *.md *.csv *.py *.json')])
        if path:
            self.run(lambda:self.store.ingest(path),lambda n:self.write('system',f'Imported {Path(path).name}: {n} text chunks. Ask a question using words from the document.'),'Importing document…')
    def clear_documents(self):
        if not self.busy and self.ask('Clear document index?','Remove all imported document text from SCROXZ? Original files remain on disk.'):
            self.store.clear_documents()
            self.write('system','Document index cleared.')
    def memories(self):
        win=tk.Toplevel(self)
        win.title('Saved memory')
        win.geometry('650x340')
        box=tk.Listbox(win,font=('Segoe UI',11))
        box.pack(fill='both',expand=True,padx=14,pady=14)
        rows=self.store.memories()
        for number,body in rows:
            box.insert('end',f'#{number} · {body}')
        def remove():
            indices=box.curselection()
            if indices and self.ask('Remove memory?','Remove this saved memory?',parent=win):
                self.store.forget(rows[indices[0]][0])
                win.destroy()
                self.memories()
        ttk.Button(win,text='Delete selected memory',command=remove).pack(pady=(0,14))
    def microphone(self):
        if self.busy:
            return
        if not self.ask('Microphone','Load local Whisper and listen until you pause?\nFirst use may download the selected model (small uses more storage and CPU than base). Wait for Listening before speaking. Text is placed in the input box for review. Choose your input device in AI settings.'):
            return
        self.stop_voice()
        self.voice_cancel=threading.Event()
        generation=self.voice_generation
        def done(text):
            self.capture_active=False
            if generation!=self.voice_generation:
                return
            if not text:
                self.status.set('Ready • no speech detected')
                return
            if self.entry.get().strip():
                self.entry.insert('end',' '+text)
            else:
                self.entry.insert('end',text)
            self.entry.focus_set()
        self.start_capture(done,'Loading microphone/model…')
    def start_capture(self, done, label):
        cancel=self.voice_cancel
        language=self.config.get('voice_language','auto')
        fast=self.fast_mic.get()
        model_name=self.config.get('recognition_model','small')
        device=self.config.get('microphone_device','default')
        self.capture_active=True
        if not self.run(lambda:listen(language,lambda text:self.events.put(('status',text,None)),cancel,
                                    fast=fast,model_name=model_name,device=device),done,label):
            self.capture_active=False
    def speak(self):
        if self.capture_active:
            self.status.set('Microphone active • stop voice before playback')
            return
        if self.last_answer:
            try:
                if self.allow_speech():
                    self.reveal_pending()
                    self.speaker.speak(self.last_answer, **self.speech_options())
            except Exception as exc:
                self.write('system',str(exc))
    def speech_options(self):
        return {'language':self.config.get('reply_language','hinglish'),
                'engine':self.config.get('speech_engine','edge'),
                'rate':self.config.get('speech_rate','0')}
    def test_voice(self):
        if self.busy or self.capture_active:
            return
        samples={'hi':'नमस्ते। अब मैं हिंदी में बोल सकता हूँ।',
                 'hinglish':'हाँ, अब मैं हिंदी और English mix करके बोल सकता हूँ।',
                 'en':'Hello. I can speak English while my reply is arriving.',
                 'auto':'नमस्ते। Hello. आपकी भाषा के हिसाब से जवाब दूँगा।'}
        try:
            if self.allow_speech():
                self.reveal_pending()
                self.speaker.speak(samples[self.config.get('reply_language','hinglish')],**self.speech_options())
        except Exception as exc:
            self.write('system',str(exc))
    def automatic_voice_changed(self):
        if not self.auto_voice.get() and not self.handsfree:
            self.reveal_pending()
            self.stream_speech=False
            self.speaker.stop()
    def allow_speech(self):
        if self.config.get('speech_engine','edge')=='windows':
            return True
        if self.online_speech_consent is None:
            self.online_speech_consent=self.ask('Enable online Hindi / English voice?',
                'Online voice sends spoken reply text to Microsoft Edge’s speech service, including any personal or document content in that reply. Internet is required.\n\nAllow for this app session? Choose Windows voice in AI settings for offline speech. Text chat still works if you decline.')
        return self.online_speech_consent
    def prepare_speech_stream(self):
        self.reveal_pending()
        self.speaker.stop()
        self.speech_buffer=SpeechBuffer()
        self.stream_speech=bool(not self.suppress_speech and (self.auto_voice.get() or self.handsfree) and self.allow_speech())
        self.stream_speech_options=self.speech_options()
        self.sync_voice=self.stream_speech and self.stream_speech_options['engine']=='edge'
        self.reply_generated=''
        self.reply_revealed=0
        self.sync_cursor=0
        self.speaker.on_progress=self.reveal_speech
    def reveal_speech(self, part, count):
        if not getattr(self,'sync_voice',False):
            return
        start=self.reply_generated.find(part,self.sync_cursor)
        if start < 0:
            return
        self.reveal_reply(start+count)
        if count == len(part):
            self.sync_cursor=start+len(part)
    def reveal_reply(self, count):
        count=min(count,len(self.reply_generated))
        if count <= self.reply_revealed:
            return
        self.chat.configure(state='normal')
        self.chat.insert('reply_end',self.reply_generated[self.reply_revealed:count])
        self.chat.configure(state='disabled')
        self.chat.see('end')
        self.reply_revealed=count
    def reveal_pending(self):
        if getattr(self,'sync_voice',False):
            self.reveal_reply(len(self.reply_generated))
            self.sync_voice=False
    def flush_speech(self,text='',final=False):
        if not self.stream_speech or self.suppress_speech:
            return
        if not (self.auto_voice.get() or self.handsfree):
            self.stream_speech=False
            self.speaker.stop()
            return
        try:
            for part in self.speech_buffer.feed(text,final=final):
                self.speaker.enqueue(part,**self.stream_speech_options)
        except Exception as exc:
            self.stream_speech=False
            self.speaker.stop()
            if getattr(self,'sync_voice',False):
                self.reveal_pending()
            self.write('system',str(exc))
    def speech_tick(self):
        try:
            self.speaker.poll()
            self.flush_speech()
            if getattr(self,'sync_voice',False) and not self.speaker.busy and not self.stream_active:
                self.reveal_pending()
        except Exception as exc:
            self.stop_voice()
            self.write('system',str(exc))
        finally:
            self.after(80,self.speech_tick)
    def screen(self):
        if self.busy:
            return
        question=self.entry.get().strip() or 'Explain what is visible on this screen and any errors.'
        if not self.config.get('vision_model'):
            messagebox.showinfo('Vision model needed','Set a vision-capable model in AI settings first.')
            return
        if not self.ask('Capture screen?','Capture one screenshot of the primary display after SCROXZ minimizes? Close private windows first. The image is kept in memory only.'):
            return
        if not self.consent('one screenshot and your screen question'):
            return
        self.iconify()
        self.busy=True
        self.status.set('Preparing screen capture…')
        def capture():
            self.busy=False
            def job():
                try:
                    from PIL import ImageGrab
                except ImportError as exc:
                    self.events.put(('show',None,None))
                    raise RuntimeError('Run Setup-Extras.bat to install screen capture support.') from exc
                try:
                    pic=ImageGrab.grab()
                finally:
                    self.events.put(('show',None,None))
                pic.thumbnail((1600,1000))
                data=io.BytesIO()
                pic.save(data,format='PNG')
                return Brain(self.config).chat([{'role':'user','content':question}],image=data.getvalue())
            def done(answer):
                self.respond(answer)
            self.run(job,done,'Analyzing screenshot…')
        self.after(700,capture)
    def ask(self,*args,**kwargs):
        previous=self.dialog_active
        self.dialog_active=True
        try:
            return messagebox.askyesno(*args,**kwargs)
        finally:
            self.dialog_active=previous
    def respond(self,answer):
        self.last_answer=answer
        self.prepare_speech_stream()
        self.begin_stream()
        self.append_stream(answer)
        self.end_stream()
        self.flush_speech(final=True)
        self.stream_speech=False
    def receive_plan(self,plan,user_text,planned=False):
        validate_plan(plan)
        if not plan['actions']:
            if planned and not plan.get('clarify',False):
                self.pending_task=[]
                # Contextual chat sends more data than planning; obtain its own cloud consent.
                if self.consent(voice_allowed=True):
                    self.chat_request(user_text)
                else:
                    self.write('system','Cloud chat cancelled.')
                return
            answer=plan['reply'] or 'Please clarify the task.'
            if plan.get('clarify',False):
                self.pending_task += [{'role':'user','content':user_text},{'role':'assistant','content':answer}]
                if len(self.pending_task)>8:
                    self.pending_task=[]
                    answer += '\nPlease start again with the complete task; the clarification limit was reached.'
            self.history=(self.history+[{'role':'user','content':user_text},{'role':'assistant','content':answer}])[-12:]
            self.respond(answer)
            return
        self.pending_task=[]
        preview='\n\n'.join(f'{i}. {describe(action)}' for i,action in enumerate(plan['actions'],1))
        approved=self.ask('Approve SCROXZ plan?',preview+'\n\nRun these steps in order?')
        def done(results):
            answer='\n'.join(results)
            self.history=(self.history+[{'role':'user','content':user_text},{'role':'assistant','content':answer}])[-12:]
            self.respond(answer)
            self.status.set('Action plan cancelled' if not approved else
                            'Task failed • see execution feedback' if any('Failed:' in r or 'Remaining steps' in r for r in results) else 'Action plan completed')
        self.run(lambda:run_approved_plan(plan,approved,self.assistant_store,
                 on_progress=lambda status:self.events.put(('status',status,None))),done,'Executing approved plan…')
    def toggle_voice(self):
        if self.handsfree:
            self.stop_voice()
            return
        if self.busy:
            messagebox.showinfo('Voice','Wait for the current task first.')
            return
        if self.config['provider'] not in ('ollama','gemini'):
            messagebox.showinfo('Voice','Hands-free supports Ollama and Gemini. Other cloud providers can use the one-shot microphone.')
            return
        cloud=self.config['provider']=='gemini'
        if cloud:
            try:
                Brain(self.config).headers()
            except ValueError as exc:
                self.write('system',str(exc))
                return
        destination=('Google Gemini. This session sends recognized text, recent chat, saved memories and relevant document excerpts to Google automatically. Free quota applies; keep billing disabled. Google may use free-tier content to improve products.' if cloud else 'local Ollama.')
        if not self.ask('Enable hands-free voice?', 'SCROXZ will listen in turns, transcribe locally and send recognized text to '+destination+'\n\nActions still need approval. Speech service consent is separate. The mic pauses during replies. Esc stops voice. First use may download Whisper. Continue?'):
            return
        self.handsfree=True
        self.cloud_voice_scope=tuple(self.config.get(k) for k in ('provider','base_url','model')) if cloud else None
        self.suppress_speech=False
        self.auto_voice.set(True)
        self.voice_cancel=threading.Event()
        self.voice_button.configure(text='Hands-free ON • Stop')
        self.status.set('Hands-free enabled • preparing microphone')
    def stop_voice(self):
        if getattr(self,'sync_voice',False):
            self.reveal_pending()
        self.suppress_speech=True
        self.stream_speech=False
        self.handsfree=False
        self.cloud_voice_scope=None
        self.voice_generation+=1
        self.voice_cancel.set()
        self.speaker.stop()
        if hasattr(self,'voice_button'):
            self.voice_button.configure(text='Start hands-free')
        if hasattr(self,'status') and not self.busy:
            self.status.set('Voice stopped • Ready')
    def voice_tick(self):
        speaking=getattr(self.speaker,'busy',False)
        if self.handsfree and not self.busy and not speaking and not self.dialog_active and self.grab_current() is None:
            cloud_mismatch=self.config['provider']=='gemini' and self.cloud_voice_scope!=tuple(self.config.get(k) for k in ('provider','base_url','model'))
            if self.config['provider'] not in ('ollama','gemini') or cloud_mismatch:
                self.stop_voice()
            else:
                generation=self.voice_generation
                def done(text):
                    self.capture_active=False
                    if not self.handsfree or generation!=self.voice_generation:
                        return
                    if not text:
                        self.status.set('Ready • waiting for your voice')
                        return
                    if text.lower().strip(' .!') in ('stop','stop listening','stop voice','bas karo','बंद करो'):
                        self.stop_voice()
                        return
                    self.submit(text)
                self.start_capture(done,'Preparing microphone…')
        self.after(800,self.voice_tick)
    def reminder_tick(self):
        delay=1000
        try:
            if not self.dialog_active and self.grab_current() is None and not self.busy:
                for number,body,due in self.assistant_store.due()[:5]:
                    self.write('system',f'REMINDER #{number}: {body}')
                    self.bell()
                    self.assistant_store.dismiss_reminder(number)
                    self.deiconify()
                self.reminder_error=None
        except Exception as exc:
            delay=10000
            error=str(exc)
            if error != self.reminder_error:
                self.reminder_error=error
                self.write('system','Reminders temporarily unavailable; retrying in 10 seconds. '+error)
        finally:
            self.after(delay,self.reminder_tick)
    def organizer(self):
        win=tk.Toplevel(self)
        win.title('Notes & reminders')
        win.geometry('720x450')
        win.transient(self)
        win.grab_set()
        tabs=ttk.Notebook(win)
        tabs.pack(fill='both',expand=True,padx=12,pady=12)
        for label,rows,is_note in [('Notes',self.assistant_store.notes(),True),('Pending reminders',self.assistant_store.reminders(),False)]:
            frame=ttk.Frame(tabs)
            tabs.add(frame,text=label)
            box=tk.Listbox(frame,font=('Segoe UI',11))
            box.pack(fill='both',expand=True)
            for number,body,stamp in rows:
                when=stamp if is_note else datetime.fromtimestamp(stamp).strftime('%d %b %H:%M')
                box.insert('end',f'#{number} | {when} | {body}')
            def remove(box=box,rows=rows,is_note=is_note):
                chosen=box.curselection()
                if not chosen:
                    return
                if self.ask('Confirm', 'Delete this note?' if is_note else 'Cancel this reminder?',parent=win):
                    number=rows[chosen[0]][0]
                    if is_note: self.assistant_store.delete_note(number)
                    else: self.assistant_store.dismiss_reminder(number)
                    win.destroy()
                    self.organizer()
            ttk.Button(frame,text='Delete selected' if is_note else 'Cancel selected',command=remove).pack(pady=8)
    def begin_stream(self):
        self.stream_active=True
        self.chat.configure(state='normal')
        self.chat.insert('end','SCROXZ\n','scroxz')
        self.chat.mark_set('reply_end','end-1c')
        self.chat.mark_gravity('reply_end','right')
        self.chat.configure(state='disabled')
    def append_stream(self,text):
        if not self.stream_active:
            return
        self.status.set('Streaming reply…')
        if getattr(self,'sync_voice',False):
            self.reply_generated+=text
            self.flush_speech(text)
            return
        self.chat.configure(state='normal')
        self.chat.insert('end',text)
        self.chat.configure(state='disabled')
        self.chat.see('end')
        self.flush_speech(text)
    def end_stream(self):
        if self.stream_active:
            self.chat.configure(state='normal')
            self.chat.mark_gravity('reply_end','left')
            self.chat.insert('end','\n\n')
            self.chat.mark_gravity('reply_end','right')
            self.chat.configure(state='disabled')
            self.stream_active=False
    def visual_tick(self):
        speaking=self.speaker.playing
        self.core_canvas.phase=state_for(self.status.get(),self.busy,speaking)
        if self.core_canvas.phase=='LISTENING' and not self.capture_active:
            self.core_canvas.phase='READY'
        if self.speaker.busy and not speaking and self.core_canvas.phase=='READY':
            self.core_canvas.phase='THINKING'
        self.speak_button.configure(state='disabled' if self.capture_active or self.busy else 'normal')
        self.reply_selector.configure(state='disabled' if self.busy else 'readonly')
        if self.core_canvas.phase!='LISTENING':
            self.core_canvas.level=0
        provider='LOCAL' if self.config['provider']=='ollama' else 'CLOUD'
        self.provider_label.configure(text=('TASK • Awaiting details' if self.pending_task else 'SCROXZ  /  '+provider))
        if hasattr(self,'theme'):
            self.theme.tick()
        self.after(150,self.visual_tick)
    def close(self):
        self.stop_voice()
        self.destroy()

if __name__=='__main__':
    App().mainloop()
