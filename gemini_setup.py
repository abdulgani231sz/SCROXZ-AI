"""Free-tier onboarding with current-user encrypted Windows key storage."""
import json
import hashlib
import os
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from core import Brain, gemini_config, GEMINI_MODEL
from credentials import save_key,forget_key


def chat_models(names):
    """Discovery is not proof of free quota or generation access; probe separately."""
    excluded=('embedding','image','audio','tts','live','robotics','deep-research')
    return sorted({name.removeprefix('models/') for name in names if isinstance(name,str)
                   and name.removeprefix('models/').startswith('gemini-')
                   and not any(part in name.lower() for part in excluded)})


def verification_token(key,model):
    return hashlib.sha256(json.dumps([key,model]).encode('utf-8')).hexdigest()


def test_reply(config,key):
    # Same streaming adapter and system/reference-message shape as normal chat.
    # No saved memory, conversation or documents are included in this probe.
    brain=Brain(dict(config,reply_language='en'),api_key=key)
    return brain.chat_stream([{'role':'user','content':'Reply with only OK.'}],'',lambda text:None)


def open_setup(app):
    if app.busy:
        return
    app.stop_voice()
    win=tk.Toplevel(app)
    win.title('Gemini setup — free-tier project')
    win.geometry('720x650')
    win.transient(app)
    win.grab_set()
    ttk.Label(win,text='Use Gemini instead of the local Ollama model',font=('Segoe UI',14,'bold')).pack(anchor='w',padx=20,pady=(18,10))
    ttk.Label(win,text='1. Create an API key in Google AI Studio using a Free-tier project.\n'
        '2. Keep Cloud Billing disabled to avoid paid API usage.\n'
        '3. Paste the key, Load models, select a model, then Test reply.\n\n'
        'Free usage has quotas. Google may use free-tier content to improve its products.\n'
        'SCROXZ cannot verify your billing tier. It never enables billing or switches to a paid fallback.',
        wraplength=630,justify='left').pack(anchor='w',padx=20,pady=5)
    ttk.Button(win,text='Open Google AI Studio',command=lambda:webbrowser.open('https://aistudio.google.com/apikey')).pack(anchor='w',padx=20,pady=8)
    ttk.Label(win,text='Gemini API key — masked; saved encrypted for your Windows account').pack(anchor='w',padx=20)
    key=tk.StringVar()
    ttk.Entry(win,textvariable=key,show='*').pack(fill='x',padx=20,pady=5)
    available='A key is already available. Leave this blank to reuse it.' if os.environ.get('GEMINI_API_KEY') else 'Save once after Test reply. SCROXZ will restore the encrypted key on restart.'
    ttk.Label(win,text=available,wraplength=630).pack(anchor='w',padx=20)
    free=tk.BooleanVar(value=False)
    ttk.Checkbutton(win,text='I checked that this Google project is on Free tier with billing disabled.',variable=free).pack(anchor='w',padx=20,pady=12)
    ttk.Label(win,text='Model — select from your account’s returned list; free quota is not guaranteed by listing.').pack(anchor='w',padx=20)
    model=tk.StringVar(value='')
    selector=ttk.Combobox(win,textvariable=model,values=[],state='readonly')
    selector.pack(fill='x',padx=20,pady=5)
    status=tk.StringVar(value='Load models first. Test reply sends only the fixed sample “Reply with only OK.”')
    ttk.Label(win,textvariable=status,wraplength=630).pack(anchor='w',padx=20,pady=5)
    tested=[None]
    def credentials():
        if not free.get():
            raise ValueError('Check your Google project tier first, then tick the confirmation.')
        value=key.get().strip() or os.environ.get('GEMINI_API_KEY','').strip()
        if not value:
            raise ValueError('Enter the API key here, not in the conversation.')
        return value
    def check():
        if app.busy:
            return
        try:
            value=credentials()
            brain=Brain(gemini_config(app.config),api_key=value)
            tested[0]=None
            save_button.configure(state='disabled')
            status.set('Loading available models…')
            def job():
                try:
                    return brain.models(),None
                except Exception as exc:
                    return [],str(exc)
            def done(result):
                models,error=result
                if win.winfo_exists():
                    if (key.get().strip() or os.environ.get('GEMINI_API_KEY','').strip())!=value:
                        status.set('Key changed. Load models again.')
                        return
                    choices=chat_models(models)
                    selector.configure(values=choices)
                    preferred=gemini_config(app.config)['model'].removeprefix('models/')
                    model.set(preferred if preferred in choices else '')
                    status.set(error or ('Models loaded. Select a model and click Test reply.' if choices else 'No conversational Gemini models were returned. Check access in AI Studio.'))
            app.run(job,done,'Checking Gemini connection…')
        except Exception as exc:
            messagebox.showerror('Gemini setup',str(exc),parent=win)
    def probe():
        if app.busy:
            return
        try:
            value=credentials()
            selected=model.get()
            if not selected or selected not in selector['values']:
                raise ValueError('Load models and select a returned model first.')
            token=verification_token(value,selected)
            tested[0]=None
            save_button.configure(state='disabled')
            status.set('Testing an actual streamed reply…')
            def job():
                try:
                    answer=test_reply(gemini_config(app.config,selected),value)
                    return None if answer.strip() else 'Model returned an empty reply.'
                except Exception as exc:
                    return str(exc)
            def done(error):
                if not win.winfo_exists():
                    return
                current=key.get().strip() or os.environ.get('GEMINI_API_KEY','').strip()
                if verification_token(current,model.get())!=token:
                    status.set('Key or model changed. Test reply again.')
                    return
                if error:
                    status.set(error)
                    return
                tested[0]=token
                save_button.configure(state='normal')
                status.set('Test reply successful. Save & use Gemini is now available.')
            app.run(job,done,'Testing Gemini reply…')
        except Exception as exc:
            messagebox.showerror('Gemini setup',str(exc),parent=win)
    def save():
        if app.busy:
            return
        try:
            value=credentials()
            if tested[0]!=verification_token(value,model.get()):
                raise ValueError('Run Test reply successfully for this key and model before saving.')
            config=gemini_config(app.config,model.get())
            save_key(app.config_path,value)
            temp=app.config_path.with_suffix('.tmp')
            temp.write_text(json.dumps(config,indent=2),encoding='utf-8')
            temp.replace(app.config_path)
            os.environ['GEMINI_API_KEY']=value
            key.set('')
            app.stop_voice()
            app.config=config
            app.pending_task=[]
            app.status.set('Ready • AI connection saved')
            app.write('system','AI connection saved. Requests use your project’s quota. Keep billing disabled for free-tier use.')
            win.destroy()
        except Exception as exc:
            messagebox.showerror('Gemini setup',str(exc),parent=win)
    actions=ttk.Frame(win)
    actions.pack(fill='x',padx=20,pady=10)
    ttk.Button(actions,text='Load models',command=check).pack(side='left')
    ttk.Button(actions,text='Test reply',command=probe).pack(side='left',padx=8)
    save_button=ttk.Button(actions,text='Save & use Gemini',command=save,state='disabled')
    save_button.pack(side='right')
    def forget():
        if app.busy:
            return
        if app.ask('Forget saved Gemini key?','Remove the saved key from this app and clear it from this session?',parent=win):
            try:
                forget_key(app.config_path)
                key.set('')
                tested[0]=None
                save_button.configure(state='disabled')
                status.set('Saved key removed. Enter a key and test it before using Gemini again.')
            except OSError:
                messagebox.showerror('Gemini setup','Could not remove the saved key.',parent=win)
    ttk.Button(win,text='Forget saved key',command=forget).pack(anchor='w',padx=20,pady=4)
    def invalidate(*args):
        tested[0]=None
        save_button.configure(state='disabled')
    key.trace_add('write',invalidate)
    model.trace_add('write',invalidate)
