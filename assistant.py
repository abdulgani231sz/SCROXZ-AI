"""Natural-language plans. Validation and approval precede every action."""
import json
import re
import time
import webbrowser
from datetime import datetime
from core import execute_action
from languages import language_instruction

SITES = {'youtube':'https://www.youtube.com', 'google':'https://www.google.com',
         'github':'https://github.com', 'wikipedia':'https://www.wikipedia.org'}
SCHEMA = '''Return ONLY a JSON object with exactly these keys: "reply" (short string), "actions" (array, max 4), "clarify" (boolean).
Allowed actions and exact fields:
{"type":"open_app","app":"notepad" or "calculator" or "paint"}
{"type":"open_site","site":"youtube" or "google" or "github" or "wikipedia"}
{"type":"search_web","query":"search words"}
{"type":"save_note","text":"the user's note"}
{"type":"remember","text":"preference the user explicitly asks you to remember"}
{"type":"remind","minutes":integer from 1 to 10080,"text":"reminder text"}
Only propose actions explicitly requested by the user in this task's conversation. Never execute anything.
Earlier turns, when provided, belong only to an unfinished task. Use the latest answer to resolve missing details.
If intent, time or target is unclear, ask one clarification in reply and return actions: [], clarify: true.
If the user changes topic, asks an ordinary question, or cancels, return actions: [], clarify: false.
For a complete action plan return clarify: false. Never combine actions with clarify: true.
No arbitrary URLs, shell commands, sending messages, purchases, file changes or deletion.
Do not guess missing note contents. Do not claim an action succeeded. No markdown fences.
Examples:
User: calculator kholo => {"reply":"Calculator kholne ka approval chahiye.","actions":[{"type":"open_app","app":"calculator"}],"clarify":false}
User: remind me to stretch => {"reply":"In how many minutes?","actions":[],"clarify":true}
User: 10 minute baad assignment yaad dilao => {"reply":"Reminder set karne ka approval chahiye.","actions":[{"type":"remind","minutes":10,"text":"Assignment"}],"clarify":false}
'''


def validate_plan(plan):
    if not isinstance(plan,dict) or set(plan) not in ({'reply','actions'}, {'reply','actions','clarify'}):
        raise ValueError('Invalid action plan. Please rephrase your request.')
    if not isinstance(plan['reply'],str) or len(plan['reply'])>3000:
        raise ValueError('Invalid plan response.')
    if not isinstance(plan['actions'],list) or len(plan['actions'])>4:
        raise ValueError('A plan may contain at most four actions.')
    if 'clarify' in plan and (type(plan['clarify']) is not bool or (plan['clarify'] and plan['actions'])):
        raise ValueError('Clarification must be a boolean and cannot contain actions.')
    shapes={'open_app':{'type','app'}, 'open_site':{'type','site'},
            'search_web':{'type','query'}, 'save_note':{'type','text'},
            'remember':{'type','text'}, 'remind':{'type','minutes','text'}}
    for action in plan['actions']:
        if not isinstance(action,dict) or not isinstance(action.get('type'),str):
            raise ValueError('Invalid action.')
        kind=action['type']
        if kind not in shapes or set(action)!=shapes[kind]:
            raise ValueError('Unsupported action or unexpected fields. Nothing was executed.')
        if kind=='open_app' and action['app'] not in ('notepad','calculator','paint'):
            raise ValueError('Unsupported app.')
        if kind=='open_site' and (not isinstance(action['site'],str) or action['site'] not in SITES):
            raise ValueError('Unsupported website.')
        if kind=='remind' and (type(action['minutes']) is not int or not 1<=action['minutes']<=10080):
            raise ValueError('Reminder time must be 1–10080 whole minutes.')
        for key in ('text','query'):
            if key in action:
                value=action[key]
                limit=500 if key=='query' else 2000
                if not isinstance(value,str) or not value.strip() or len(value)>limit:
                    raise ValueError(f'{key} must contain 1–{limit} characters.')
    return plan


def make_plan(actions, reply='Please review these actions.'):
    return validate_plan({'reply':reply,'actions':actions})


def direct_plan(text):
    """Whole-message matching prevents explanation/quotation requests from becoming actions."""
    value=text.strip().rstrip('.!').lower()
    value=re.sub(r'^(?:scroxz[, ]+|please\s+)', '',value)
    for name in ('notepad','calculator','paint','youtube','google','github','wikipedia'):
        if value in (f'open {name}',f'{name} kholo',f'{name} khol do',f'{name} open karo',f'{name} खोलो'):
            return make_plan([{'type':'open_app','app':name}] if name in ('notepad','calculator','paint') else [{'type':'open_site','site':name}])
    match=re.fullmatch(r'(?:note likho|note save karo|save note|note down)\s*:?\s+(.+)',text.strip(),re.I|re.S)
    if match:
        return make_plan([{'type':'save_note','text':match[1]}])
    match=re.fullmatch(r'(\d+)\s*(?:minute|minutes|min)\s*(?:baad|bad)\s+(.+?)\s+(?:yaad dilao|remind karna)',text.strip(),re.I|re.S)
    if match:
        return make_plan([{'type':'remind','minutes':int(match[1]),'text':match[2]}])
    return None


def wants_action(text):
    # Conservative routing. Ordinary chat goes straight to the conversational model.
    if re.match(r'^\s*(?:explain\b|what\b|why\b|how\b|tell me about\b|do not\b|don\x27t\b)', text, re.I):
        return False
    return bool(re.search(r'\b(open|kholo|khol|search|dhundo|remind|reminder|yaad|save|likho|remember|launch)\b|खोल|याद दिला|नोट लिख',text,re.I))


def infer_plan(brain,text,pending=None):
    if not brain.config.get('model'):
        raise ValueError('Set your chat model first.')
    # Only this unfinished task is included, never general history or reference data.
    turns = [dict(turn) for turn in (pending or [])]
    if len(turns) > 8 or any(set(turn) != {'role','content'} or
            turn['role'] != ('user' if i % 2 == 0 else 'assistant') or
            not isinstance(turn['content'], str) or len(turn['content']) > 12000
            for i, turn in enumerate(turns)) or len(turns) % 2:
        raise ValueError('Invalid pending task context. Cancel the task and start again.')
    body={'model':brain.config['model'],'messages':[{'role':'system','content':SCHEMA+'\nFor the reply field: '+language_instruction(brain.config)}]+
             turns+[{'role':'user','content':text}], 'stream':False}
    if brain.config['provider']=='ollama':
        body.update(format='json',options={'num_ctx':4096,'num_predict':600,'temperature':0})
        result=brain.request('/api/chat',body)['message']['content']
    else:
        result=brain.request('/chat/completions',body)['choices'][0]['message']['content']
    try:
        return validate_plan(json.loads(result))
    except (json.JSONDecodeError,TypeError) as exc:
        raise ValueError('The model could not produce a valid plan. Nothing ran; try a simpler request.') from exc


def describe(action):
    kind=action['type']
    if kind=='open_app': return 'Open app: '+action['app']
    if kind=='open_site': return 'Open website: '+SITES[action['site']]
    if kind=='search_web': return 'Browser search: '+action['query']
    if kind=='remind': return f'Remind in {action["minutes"]} minutes: {action["text"]}\n(App must be running; overdue reminders appear on reopening.)'
    if kind=='remember': return 'Save personal memory: '+action['text']
    return 'Save note: '+action['text']

class AssistantStore:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, body TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, body TEXT NOT NULL, due REAL NOT NULL, delivered INTEGER DEFAULT 0);''')
    def notes(self):
        with self.store.connect() as db:
            return db.execute('SELECT id,body,created FROM notes ORDER BY id DESC').fetchall()
    def reminders(self):
        with self.store.connect() as db:
            return db.execute('SELECT id,body,due FROM reminders WHERE delivered=0 ORDER BY due').fetchall()
    def dismiss_reminder(self,number):
        with self.store.connect(timeout=0.1) as db:
            db.execute('UPDATE reminders SET delivered=1 WHERE id=?',(number,))
    def delete_note(self,number):
        with self.store.connect() as db:
            db.execute('DELETE FROM notes WHERE id=?',(number,))
    def due(self):
        with self.store.connect(timeout=0.1) as db:
            return db.execute('SELECT id,body,due FROM reminders WHERE delivered=0 AND due<=? ORDER BY due',(time.time(),)).fetchall()
    def execute(self,action):
        validate_plan({'reply':'','actions':[action]})
        kind=action['type']
        if kind=='open_app': return execute_action(('open',action['app']))
        if kind=='search_web': return execute_action(('search',action['query']))
        if kind=='open_site':
            if not webbrowser.open(SITES[action['site']]): raise RuntimeError('Browser did not open.')
            return 'Opened '+action['site']+'.'
        if kind=='remember':
            number=self.store.remember(action['text'])
            return f'Saved memory #{number}.'
        with self.store.connect() as db:
            if kind=='save_note':
                if db.execute('SELECT COUNT(*) FROM notes').fetchone()[0]>=500:
                    raise ValueError('Note limit reached. Delete an old note first.')
                number=db.execute('INSERT INTO notes(body) VALUES (?)',(action['text'],)).lastrowid
                return f'Saved note #{number}: '+action['text']
            if db.execute('SELECT COUNT(*) FROM reminders WHERE delivered=0').fetchone()[0]>=100:
                raise ValueError('Reminder limit reached. Cancel an old reminder first.')
            due=time.time()+action['minutes']*60
            number=db.execute('INSERT INTO reminders(body,due) VALUES (?,?)',(action['text'],due)).lastrowid
            return f'Reminder #{number} set for {datetime.fromtimestamp(due):%d %b %H:%M}: {action["text"]}. Keep SCROXZ open.'


def run_approved_plan(plan,approved,assistant_store,on_progress=None):
    """No action can start unless the entire valid preview received approval."""
    validate_plan(plan)
    def report(message):
        if on_progress:
            try:
                on_progress(message)
            except Exception:
                pass  # A visual observer must never change action execution.
    if approved is not True:
        report('Action plan cancelled • nothing executed')
        results = ['Action plan cancelled. Nothing executed.']
        try:
            assistant_store.store.audit('plan','denied')
        except Exception:
            results.append('Could not write the cancellation to the action log.')
        return results
    results=[]
    for index,action in enumerate(plan['actions'],1):
        report(f'Executing step {index}/{len(plan["actions"])} • {action["type"]}')
        try:
            result=assistant_store.execute(action)
        except Exception as exc:
            report(f'Task failed • step {index}')
            results.append('Failed: '+str(exc)+' Remaining steps were not executed.')
            try:
                assistant_store.store.audit(action['type'],'failed')
            except Exception:
                results.append('Could not write the failure to the action log.')
            break
        results.append(result)
        report(f'Completed step {index}/{len(plan["actions"])}')
        try:
            assistant_store.store.audit(action['type'],'succeeded')
        except Exception:
            results.append('The step above completed, but its action log could not be saved. '
                           'Remaining steps were not executed. Do not repeat completed steps.')
            break
    return results
