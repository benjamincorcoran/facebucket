import re
import json
import yaml
import fbchat
import pickle
import random
import collections
import time
import contextlib
import collections
import pycron
import cron_descriptor as cd
import datetime

import nltk
nltk.download('stopwords')
from nltk.corpus import stopwords

from fbchat import log, Client
from fbchat import Message, User, ThreadType, ThreadLocation

from functions import *
from inventory import *
from responder import *

fbchat._util.USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36"]

SESSION_PATH = './assets/SESSION.pickle'



# Subclass fbchat.Client and override required methods
class Bucket(fbchat.Client):

    def __init__(self, *args, **kwargs):

        # Bucket variables
        self.RESPONSE_PROB = 1
        self.BAND_NAME_PROB = 0.2
        self.GIF_PROB = 0.2
        self.BUCKET_SIZE = 30
        self.HISTORY = {
            'message': collections.defaultdict(lambda :['']),
            'sent':collections.defaultdict(lambda :[''])
        }

        self.KEYWORDS = None
        self.STOPWORDS = set(stopwords.words('english'))

        # Load session data
        with open(SESSION_PATH, 'rb') as f:
            self.SESSION_COOKIES = pickle.load(f)

        # Load JSON data into bucket memory
        data = load_data('./assets/data')

        # Create items invectory
        self.ITEMS = LimitedInventory('./assets/data/ITEMS.json', self.BUCKET_SIZE)
        self.RESPONSES = Responder('./assets/data/RESPONSES.json')
        self.BANDS = Inventory('./assets/data/BANDS.json')
        self.TIMERS = TimedResponder('./assets/data/TIMERS.json')
        self.HELP = data['HELP']

        # Load wordLists
        self.wordLists = load_word_lists('./assets/wordlists')

        # Set up minute started
        self.lastCheckTime = datetime.datetime.utcnow()

        # Load timeouts
        self.timeOuts = []

        super(
            Bucket,
            self).__init__(
            '<email>',
            '<password>',
            session_cookies=self.SESSION_COOKIES)

        # Patterns
        self.NEW_RESPONSE_PATTERN = re.compile(r'if (.*) then (.*)', flags=re.IGNORECASE + re.DOTALL)
        self.NEW_CHOICE_PATTERN = re.compile(r'if (.*) choose (.*)', flags=re.IGNORECASE + re.DOTALL)
        self.NEW_TREE_PATTERN = re.compile(r'if (.*) tree (\[.*\])', flags=re.IGNORECASE + re.DOTALL)
        self.DELETE_RESPONSE_PATTERN = re.compile(r'bucket no more (.*)', flags=re.IGNORECASE + re.DOTALL)
        self.NEW_ITEM_PATTERN = re.compile(r'give bucket (.*)', flags=re.IGNORECASE + re.DOTALL)
        self.GIVE_ITEM_PATTERN = re.compile(r'bucket give (\w+) a present', flags=re.IGNORECASE)
        self.BAND_PATTERN = re.compile(r'^[^\s]+\s[^\s]+\s[^\s]+$', flags=re.IGNORECASE)
        self.TIMER_PATTERN = re.compile('bucket ((?:(?:(?:\d+,)+\d+|(?:\d+(?:\/|-)\d+)|(?:\*(?:\/|-)\d+)|\d+|\*) ?){5,7})\s(.*)', flags=re.IGNORECASE + re.DOTALL)
        self.HELP_PATTERN = re.compile(r'bucket help ?(.*)?', flags=re.IGNORECASE)
        self.QUIET_PATTERN = re.compile(r'bucket shut up (\d+)', flags=re.IGNORECASE)
        self.URL_PATTERN = re.compile(r'\$URL:([^\s]*\.[^\s]+)', flags=re.IGNORECASE)
        self.TIMEOUT_PATTERN = re.compile(r'bucket give (\w+) a time\s*?out', flags=re.IGNORECASE)


    def listen(self, markAlive=None):
        """Initialize and runs the listening loop continually.

        Args:
            markAlive (bool): Whether this should ping the Facebook server each time the loop runs
        """
        if markAlive is not None:
            self.setActiveStatus(markAlive)

        self.startListening()
        self.onListening()

        while self.listening and self.doOneListen():
            if self.lastCheckTime.minute != datetime.datetime.utcnow().minute:
                self.lastCheckTime = datetime.datetime.utcnow()

                if len(self.timeOuts) > 0:
                    remove = []
                    for i, timeOut in enumerate(self.timeOuts):
                        if timeOut['time_in'] < datetime.datetime.now():
                            print(timeOut)
                            self.time_in(timeOut['thread_id'], timeOut['thread_type'], timeOut['user_id'])
                            remove.append(i)
                    
                    self.timeOuts = [t for i,t in enumerate(self.timeOuts) if i not in remove]
                    

                timedMessages = self.TIMERS.check(self.lastCheckTime)
                if timedMessages is not None:

                    for thread_id, thread_type, response in timedMessages:

                        if thread_type == 'GROUP':
                            thread_type = ThreadType.GROUP
                        else:
                            thread_type = ThreadType.USER

                        if thread_type == ThreadType.GROUP:
                            USER = fbchat.User(1,first_name='')
                            ALLUSERS = [user for uid, user in self.fetchUserInfo(
                                *self.fetchGroupInfo(thread_id)[thread_id].participants).items() if user.first_name != 'Bot']
                        else:
                            USER = self.fetchUserInfo(thread_id)[thread_id]
                            ALLUSERS = [USER]

                        self.KEYWORDS = {
                            r"\$USER": USER.first_name,
                            r"\$RANDOM": lambda _: random.choice(ALLUSERS).first_name,
                            r"\$RAND(\d+)": lambda x: str(random.randint(1, int(x))),
                        }

                        for key in self.wordLists:
                            self.KEYWORDS[r'\$'+key.upper()] = lambda _, k=key: random.choice(self.wordLists[k])
                            self.KEYWORDS[r'\$(\w+)_'+key.upper()] = lambda s, k=key: random.choice([n for n in self.wordLists[k] if n[:len(s)]==s.lower()]+[''])


                        response = self.apply_keywords(response)
                        response = re.sub(r'\b([aA])\b(?=\s+[aeiouAEIOU])',r'\1n',response)
                        response = re.sub(r'\b([aA][nN])\b(?=\s+[^aeiouAEIOU])',r'a',response)

                        self.send(Message(text=response), thread_id=thread_id, thread_type=thread_type)

        self.stopListening()


    def add_to_responses(self, message_object, context, responseType='then'):

        user = self.KEYWORDS[r'\$USER']

        if responseType == 'then':
            newResponse = re.findall(self.NEW_RESPONSE_PATTERN, message_object.text)[0]
            msg = f"Okay {user}, if someone says '{newResponse[0]}' then I'll reply '{newResponse[1]}'."

        elif responseType == 'choice':
            newResponse = re.findall(self.NEW_CHOICE_PATTERN, message_object.text)[0]
            newResponse = (newResponse[0], [_.strip() for _ in newResponse[1].split(';')])
            msg = f"Okay {user}, if someone says '{newResponse[0]}' then I'll reply with one of '{', '.join(newResponse[1])}'."

        elif responseType == 'tree':
            newResponse = re.findall(self.NEW_TREE_PATTERN, message_object.text)[0]
            newResponse = [newResponse[0], json.loads(newResponse[1])]
            msg = f"Okay {user}, if someone says '{newResponse[0]}' then I'll reply '{newResponse[1][0]}' then enter this tree {newResponse[1][1]}."

        self.RESPONSES.add(*newResponse)
        self.send(Message(text=msg), **context)

    def delete_response(self, message_object, context):

        # with self.appearing_in_thought(thread_id='', thread_type=''):
        thread_id = context['thread_id']

        trigger = re.findall(self.DELETE_RESPONSE_PATTERN,message_object.text)[0]

        self.RESPONSES.remove(trigger)
        self.TIMERS.remove(thread_id, trigger)
 

        msg = f"Okay, I wont respond to '{trigger}' anymore :)"
        self.send(Message(text=msg), **context)

    def add_to_bucket(self, message_object, context):

        # with self.appearing_in_thought(thread_id='', thread_type=''):

        newItem = re.findall(self.NEW_ITEM_PATTERN, message_object.text)[0]
        dropped = self.ITEMS.add(newItem)

        if dropped is None:
            msg = f"Bucket is holding {newItem}."
        else:
            msg = f"Bucket dropped {dropped}. Bucket is now holding {newItem}."

        self.send(Message(text=msg), **context)

    def apply_keywords(self, response):
        for keyword, replace in self.KEYWORDS.items():
            if callable(replace):
                for find in re.findall(
                        keyword, response, flags=re.IGNORECASE):
                    response = re.sub(
                        keyword,
                        replace(find),
                        response,
                        count=1,
                        flags=re.IGNORECASE)
            else:
                response = re.sub(
                    keyword, replace, response, flags=re.IGNORECASE)
        return response

    def give_item_to(self, message_object, context):

        thread_type = context['thread_type']
        thread_id = context['thread_id']

        capture = re.findall(
            self.GIVE_ITEM_PATTERN,
            message_object.text)[0].title()

        if capture == 'Everyone' and thread_type == ThreadType.GROUP:
            users = self.fetchUserInfo(
                *self.fetchGroupInfo(thread_id)[thread_id].participants)
            targets = [
                user.first_name.title() for uid,
                user in users.items() if user.first_name.title() != 'Bot']
        elif capture == 'Everyone':
            targets = [self.fetchUserInfo(thread_id)[thread_id].first_name]
        else:
            targets = [capture]

        # with self.appearing_in_thought(thread_id='', thread_type=''):
        for target in targets:
            gift = self.ITEMS.get()

            if gift is None:
                msg = f"I'm empty :("
                break
            else:
                msg = f"Bucket gave {target} {gift}."

            self.send(Message(text=msg), **context)

    def add_new_timer(self, message_object, context):
        
        user = self.KEYWORDS[r'\$USER']
        
        capture = re.findall(self.TIMER_PATTERN, message_object.text)[0]

        if context['thread_type'] == ThreadType.GROUP:
            ttype = 'GROUP'
        else:
            ttype = 'USER'
        
        self.TIMERS.add(context['thread_id'], capture[0], [ttype, capture[1]])

        engCron = cd.get_description(capture[0])
        msg = f"Okay {user}. I'll say '{capture[1]}' {engCron.lower()}"

        self.send(Message(text=msg), **context)

    def respond_with_help_doc(self, message_object, thread_id='', thread_type=''):
        specific = re.findall(self.HELP_PATTERN, message_object.text)[0]
        if specific != '':
            msg = self.HELP[specific.lower()]
        else:
            msg = self.HELP['help']

        self.send(
            Message(
                text=msg),
            thread_id=thread_id,
            thread_type=thread_type)

    def global_quiet(self, message_object, context):
        minutes = int(re.findall(self.QUIET_PATTERN, message_object.text)[0])

        if minutes <= 60:
            msg = f"Okay, I'll be quiet for {minutes} minutes."
        else:
            minutes = 60
            msg = f"Err, I'll be quiet for an hour, but I wont be silenced."

        self.send(Message(text=msg), **context)
        self.stopListening()
        time.sleep(minutes * 60)
        self.listen()

    def add_to_message_history(self, message_object, thread_id, k='message'):
        self.HISTORY[k][thread_id].append(message_object.text)
        if len(self.HISTORY[k][thread_id]) > 3:
            self.HISTORY[k][thread_id] = self.HISTORY[k][thread_id][-3:]
    
    def add_to_sent_history(self, message_object, thread_id):
        self.add_to_message_history(message_object, thread_id, k='sent')

    def last_message_was_haiku(self, thread_id):
        haiku_test = [len(re.findall(r'([aeiouy])', msg, flags=re.IGNORECASE))
                      for msg in self.HISTORY['message'][thread_id]]
        if haiku_test == [5, 7, 5]:
            return True
        else:
            return False

    def check_band_name(self, message_object, context):
        bandName = re.findall(self.BAND_PATTERN, message_object.text)[0]
        if not self.BANDS.has(bandName):
            self.BANDS.add(bandName)
            if random.random() < self.BAND_NAME_PROB:
                genre = self.KEYWORDS[r'\$GENRE'](None)
                self.send(
                    Message(
                        text=f'{message_object.text} would be a good name for a {genre} band.'),
                        **context)
                return True
        
        return False
    
    def random_gif_response(self, message_object, context):
        uncommon = [_ for _ in filter(lambda w: not w in self.STOPWORDS, message_object.text.split())]
        if len(uncommon) > 0:
            gif = get_gif(random.choice(uncommon), random.randint(1,10))
            if gif:
                self.sendRemoteFiles(gif, Message(text=''), **context)
                return True

        return False

    def time_out(self, message_object, context, msg=None, userid=None):
        
        thread_id = context['thread_id']
        thread_type = context['thread_type']

        if userid is None:
            target = re.findall(self.TIMEOUT_PATTERN, message_object.text)[0].lower()

            if target == 'bucket':
                self.send(Message(text="I'm not a moron."), **context)

            users = {user.first_name.lower():uid for uid, user in self.fetchUserInfo(
                    *self.fetchGroupInfo(thread_id)[thread_id].participants).items() if user.first_name != 'Bucket'}
        
        else:
            target = self.fetchUserInfo(userid)[userid].first_name
            users = {target:userid}
        
        if msg is None:
            msg = f'{target.title()} is having a 5 minute time out.'

        if target in users.keys():
            self.send(Message(text=msg), **context)
            self.removeUserFromGroup(users[target], thread_id=thread_id)
            self.timeOuts.append({'thread_id':thread_id, 'thread_type':thread_type, 'user_id':users[target],'time_in':datetime.datetime.now()+datetime.timedelta(minutes = 5)})
    
    def time_in(self, context, user_id):
        self.addUsersToGroup([user_id], thread_id=context['thread_id'])
        self.send(Message(text=f'I hope you learned your lesson.'), **context)

    def respond_to_message(self, message_object, context):

        match = self.RESPONSES.check(message_object.text)

        if match is not None:

            trigger = match[0]
            response = match[1]
            captures = match[2]
            
            if isinstance(response, list):
                if any([isinstance(i, dict) for i in response]):
                    newDict = [i for i in response if isinstance(i, dict)][0]
                    self.RESPONSES = MemoryResponder(newDict)
                    if len(response) == 2:
                        response = response[0]
                    else:
                        response = response[1]
                    if response == '':
                        return False
                
                else:
                    response = random.choice(response)


            if re.search('\$TIMEOUT', response, flags=re.IGNORECASE):
                self.time_out(message_object, context, msg=re.sub('\$TIMEOUT\s*','',response, flags=re.IGNORECASE), userid=message_object.author)
                return True

            attachments = []
            if re.search(self.URL_PATTERN, response):
                attachments = re.findall(self.URL_PATTERN, response)
                response = re.sub(self.URL_PATTERN, '', response)


            response = self.apply_keywords(response)

            for capture in captures:
                response = re.sub(r"\$WORD", capture, response, count=1)

            response = re.sub(r'\b([aA])\b(?=\s+[aeiouAEIOU])',r'\1n',response)
            response = re.sub(r'\b([aA][nN])\b(?=\s+[^aeiouAEIOU])',r'a',response)

            if response + ''.join(attachments) != self.HISTORY['sent'][context['thread_id']][-1]:
                if attachments != []:
                    self.sendRemoteFiles(attachments, Message(text=response), **context)
                else:
                    self.send(Message(text=response), **context)
                
                self.add_to_sent_history(Message(text=response), context['thread_id'])
                
                return True
        
        if self.RESPONSES.path == 'MEMORY':
            self.RESPONSES = Responder('./assets/data/RESPONSES.json')
            self.respond_to_message(message_object, context)
        return False

    def onPeopleAdded(self, added_ids, author_id, thread_id, **kwargs):
        context = {'thread_id':thread_id, 'thread_type':ThreadType.GROUP}

        self.markAsRead(thread_id)
        if self.fetchUserInfo(author_id)[author_id].first_name.lower() != 'bucket':
            self.respond_with_help_doc(Message(text='bucket help'), **context)

    def onPendingMessage(self, thread_id, thread_type, metadata, msg):
        context = {'thread_id':thread_id, 'thread_type':thread_type}

        self.moveThreads(ThreadLocation.INBOX, thread_id)
        self.markAsRead(thread_id)
        self.respond_with_help_doc(Message(text='bucket help'), **context)

    def get_users(self, USER, thread_id='', thread_type=''):
        if thread_type == ThreadType.GROUP:
            ALLUSERS = {uid: user for uid, user in self.fetchUserInfo(
                *self.fetchGroupInfo(thread_id)[thread_id].participants).items() if user.first_name != 'Bucket'}
        else:
            ALLUSERS = [USER]
        
        return ALLUSERS

    def onMessage(self, author_id, message_object, thread_id, thread_type, **kwargs):
        

        context = {'thread_id':thread_id, 'thread_type':thread_type}

        USER = self.fetchUserInfo(author_id)[f'{author_id}']
        ALLUSERS = self.get_users(USER, **context)

        self.KEYWORDS = {
            r"\$USER": USER.first_name,
            r"\$RANDOM": lambda _: random.choice(ALLUSERS).first_name,
            r"\$RAND(\d+)": lambda x: str(random.randint(1, int(x))),
        }

        for key in self.wordLists:
            self.KEYWORDS[r'\$'+key.upper()] = lambda _, k=key: random.choice(self.wordLists[k])
            self.KEYWORDS[r'\$(\w+)_'+key.upper()] = lambda s, k=key: random.choice([n for n in self.wordLists[k] if n[:len(s)]==s.lower()]+[''])

        messageHandled = True
        
        self.markAsDelivered(thread_id, message_object.uid)
        self.markAsRead(thread_id)

        # Message handler
        if author_id != self.uid:
            self.add_to_message_history(message_object, thread_id)
            # Add and item
            if re.match(self.NEW_ITEM_PATTERN, message_object.text):
                self.add_to_bucket(message_object, context)
            # Give an item
            elif re.match(self.GIVE_ITEM_PATTERN, message_object.text):
                self.give_item_to(message_object, context)
            # Add a response
            elif re.match(self.NEW_RESPONSE_PATTERN, message_object.text):
                self.add_to_responses(message_object, context, responseType='then')
            # Add a choice response
            elif re.match(self.NEW_CHOICE_PATTERN, message_object.text):
                self.add_to_responses(message_object, context, responseType='choice')
            elif re.match(self.NEW_TREE_PATTERN, message_object.text):
                self.add_to_responses(message_object, context, responseType='tree')
            # Remove a response
            elif re.match(self.DELETE_RESPONSE_PATTERN, message_object.text):
                self.delete_response(message_object, context)
            # Look up help
            elif re.match(self.HELP_PATTERN, message_object.text):
                self.respond_with_help_doc(message_object, **context)
            # Look for quiet command
            elif re.match(self.QUIET_PATTERN, message_object.text):
                self.global_quiet(message_object, context)
            # Look for a new timer 
            elif re.match(self.TIMER_PATTERN, message_object.text):
                self.add_new_timer(message_object, context)
            # Look for a reponse
            elif self.last_message_was_haiku(thread_id):
                self.HISTORY['message'][thread_id] = []
                self.send(Message(text='Was that a haiku?'), **context)
            # Look for a time out 
            elif re.match(self.TIMEOUT_PATTERN, message_object.text):
                self.time_out(message_object, context)
            else:
                messageHandled = False

            if not messageHandled and (random.random() < self.RESPONSE_PROB or re.search('bucket', message_object.text, flags=re.IGNORECASE)):
                messageHandled = self.respond_to_message(message_object, context)

            if not messageHandled and re.match(self.BAND_PATTERN, message_object.text):
                messageHandled = self.check_band_name(message_object, context)

            if not messageHandled and random.random() < self.GIF_PROB:
                messageHandled = self.random_gif_response(message_object, context)


bucket = Bucket()
bucket.listen()
