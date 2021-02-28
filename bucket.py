import re
import json
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

from fbchat import log, Client
from fbchat import Message, User, ThreadType, ThreadLocation

from functions import *

fbchat._util.USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36"]
fbchat._state.FB_DTSG_REGEX = re.compile(r'"name":"fb_dtsg","value":"(.*?)"')

SESSION_PATH = './assets/SESSION.pickle'


class Inventory(object):

    def __init__(self, path):
        
        self.path = path
        
        with open(self.path, 'r') as f:
            self.ITEMS = json.load(f)

    def add(self, item):
        self.ITEMS.append(self.clean(item))
        self.save()

    def get(self):
        if len(self.ITEMS) > 0:
            item = self.ITEMS.pop(random.randint(0, len(self.ITEMS)))
        else:
            item = None
        self.save()
        return item

    def clean(self, text):
        CLEAN_PATTERN = re.compile(r'[^A-Za-z0-9\s\$;]')
        return re.sub(CLEAN_PATTERN, '', text).lower()

    def has(self, item):
        if self.clean(item) in set(self.ITEMS):
            return True
        else:
            return False

    def save(self):
        with open(self.path, 'w') as f:
            f.write(json.dumps(self.ITEMS, indent=4))


class LimitedInventory(Inventory):

    def __init__(self, path, size):

        self.path = path
        self.SIZE = size

        with open(self.path, 'r') as f:
            self.ITEMS = json.load(f)

    def add(self, item):
        if len(self.ITEMS) > self.SIZE:
            drop = self.get()
        else:
            drop = None

        self.ITEMS.append(item)
        self.save()
        return drop


class Responder(object):

    def __init__(self, path):

        self.CLEAN_PATTERN = re.compile(r'[^A-Za-z0-9\s\$;]')
        self.path = path
        self.load()

    def load(self):
        with open(self.path, 'r') as f:
            self.rawResponses = json.load(f)

        self.RESPONSES = {
            self.parse(trigger): response for trigger,
            response in self.rawResponses.items()}

    def clean(self, text):
        '''
        Remove non alpha numeric, change $word to capture group and
        border pattern.
        '''
        return re.sub(self.CLEAN_PATTERN, '', text)

    def parse(self, text):
        pattern = re.sub(
            r'\$WORD',
            '([A-Za-z]+)',
            self.clean(text),
            flags=re.IGNORECASE)
        bordered = re.compile(rf'\b{pattern}\b', flags=re.IGNORECASE)
        return bordered

    def add(self, trigger, response):
        self.rawResponses[trigger.lower()] = response
        self.save()
        self.load()

    def remove(self, trigger):
        try:
            del self.rawResponses[trigger.lower()]
            self.save()
            self.load()
        except KeyError:
            pass

    def save(self):
        with open(self.path, 'w') as f:
            f.write(json.dumps(self.rawResponses, indent=4))

    def check(self, message):
        matches = []
        message = self.clean(message)
        for trigger, response in self.RESPONSES.items():
            check = re.search(trigger, message)
            if check:
                matches.append((trigger, response, check.groups()))

        if len(matches) > 0:
            return max(matches, key=lambda x: len(x[0].pattern))
        else:
            return None

class TimedResponder(Responder):

    def parse(self, text):
        return text

    def check(self, time):
        matches = []
        for thread_id, threadTimers in self.RESPONSES.items():
            for trigger, [thread_type, response] in threadTimers.items():
                if pycron.is_now(trigger):
                    matches.append([thread_id, thread_type, response])
        
        if len(matches) > 0:
            return matches
        else:
            return None

    def add(self, thread_id, trigger, response):
        if thread_id not in self.rawResponses.keys():
            self.rawResponses[thread_id] = {}

        self.rawResponses[thread_id][trigger.lower()] = response
        self.save()
        self.load()
    
    def remove(self, thread_id, trigger):  
        self.rawResponses[thread_id] = {k:[t,v] for k,[t,v] in self.rawResponses[thread_id].items() if v.lower() != trigger.lower()}
        self.save()
        self.load()


# Subclass fbchat.Client and override required methods
class Bucket(fbchat.Client):

    def __init__(self, *args, **kwargs):

        # Bucket variables
        self.RESPONSE_PROB = 1
        self.BAND_NAME_PROB = 0.2
        self.BUCKET_SIZE = 30
        self.HISTORY = {
            'message': collections.defaultdict(lambda :['']),
            'sent':collections.defaultdict(lambda :[''])
        }

        self.KEYWORDS = None

        # Load session data
        with open(SESSION_PATH, 'rb') as f:
            self.SESSION_COOKIES = pickle.load(f)

        # Load JSON data into bucket memory
        data = load_data('./assets/data')

        # Create items invectory
        self.ITEMS = LimitedInventory(
            './assets/data/ITEMS.json', self.BUCKET_SIZE)
        self.RESPONSES = Responder('./assets/data/RESPONSES.json')
        self.BANDS = Inventory('./assets/data/BANDS.json')
        self.TIMERS = TimedResponder('./assets/data/TIMERS.json')
        self.HELP = data['HELP']

        # Load wordLists
        self.wordLists = load_word_lists('./assets/wordlists')

        # Set up minute started
        self.lastCheckTime = datetime.datetime.utcnow()

        super(
            Bucket,
            self).__init__(
            '<email>',
            '<password>',
            session_cookies=self.SESSION_COOKIES)

        # Patterns
        self.NEW_RESPONSE_PATTERN = re.compile(r'if (.*) then (.*)', flags=re.IGNORECASE + re.DOTALL)
        self.NEW_CHOICE_PATTERN = re.compile(r'if (.*) choose (.*)', flags=re.IGNORECASE + re.DOTALL)
        self.DELETE_RESPONSE_PATTERN = re.compile(r'bucket no more (.*)', flags=re.IGNORECASE + re.DOTALL)
        self.NEW_ITEM_PATTERN = re.compile(r'give bucket (.*)', flags=re.IGNORECASE + re.DOTALL)
        self.GIVE_ITEM_PATTERN = re.compile(r'bucket give (\w+) a present', flags=re.IGNORECASE)
        self.BAND_PATTERN = re.compile(r'^[^\s]+\s[^\s]+\s[^\s]+$', flags=re.IGNORECASE)
        self.TIMER_PATTERN = re.compile('bucket ((?:(?:(?:\d+,)+\d+|(?:\d+(?:\/|-)\d+)|(?:\*(?:\/|-)\d+)|\d+|\*) ?){5,7})\s(.*)', flags=re.IGNORECASE + re.DOTALL)
        self.HELP_PATTERN = re.compile(r'bucket help ?(.*)?', flags=re.IGNORECASE)
        self.QUIET_PATTERN = re.compile(r'bucket shut up (\d+)', flags=re.IGNORECASE)
        self.URL_PATTERN = re.compile(r'\$URL:([^\s]*\.[^\s]+)', flags=re.IGNORECASE)

    # @contextlib.contextmanager
    # def appearing_in_thought(self, thread_id, thread_type):
    #     # Create illusion of thought
    #     self.setTypingStatus(fbchat.TypingStatus(1), thread_id=thread_id, thread_type=thread_type)
    #     time.sleep(int(random.random()*2))
    #     yield None
    #     self.setTypingStatus(fbchat.TypingStatus(0), thread_id=thread_id, thread_type=thread_type)

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


    def add_to_responses(
            self,
            message_object,
            thread_id,
            thread_type,
            responseType='then'):

        user = self.KEYWORDS[r'\$USER']

        # with self.appearing_in_thought(thread_id, thread_type):

        if responseType == 'then':
            newResponse = re.findall(
                self.NEW_RESPONSE_PATTERN,
                message_object.text)[0]
            msg = f"Okay {user}, if someone says '{newResponse[0]}' then I'll reply '{newResponse[1]}'."

        elif responseType == 'choice':
            newResponse = re.findall(
                self.NEW_CHOICE_PATTERN,
                message_object.text)[0]
            newResponse = (newResponse[0], [_.strip()
                                            for _ in newResponse[1].split(';')])
            msg = f"Okay {user}, if someone says '{newResponse[0]}' then I'll reply with one of '{', '.join(newResponse[1])}'."

        self.RESPONSES.add(*newResponse)
        self.send(
            Message(
                text=msg),
            thread_id=thread_id,
            thread_type=thread_type)

    def delete_response(self, message_object, thread_id, thread_type):

        # with self.appearing_in_thought(thread_id, thread_type):

        trigger = re.findall(
            self.DELETE_RESPONSE_PATTERN,
            message_object.text)[0]

        self.RESPONSES.remove(trigger)
        self.TIMERS.remove(thread_id, trigger)
 

        msg = f"Okay, I wont respond to '{trigger}' anymore :)"
        self.send(
            Message(
                text=msg),
            thread_id=thread_id,
            thread_type=thread_type)

    def add_to_bucket(self, message_object, thread_id, thread_type):

        # with self.appearing_in_thought(thread_id, thread_type):

        newItem = re.findall(self.NEW_ITEM_PATTERN, message_object.text)[0]
        dropped = self.ITEMS.add(newItem)

        if dropped is None:
            msg = f"Bucket is holding {newItem}."
        else:
            msg = f"Bucket dropped {dropped}. Bucket is now holding {newItem}."

        self.send(
            Message(
                text=msg),
            thread_id=thread_id,
            thread_type=thread_type)

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

    def give_item_to(self, message_object, thread_id, thread_type):

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

        # with self.appearing_in_thought(thread_id, thread_type):
        for target in targets:
            gift = self.ITEMS.get()

            if gift is None:
                msg = f"I'm empty :("
                break
            else:
                msg = f"Bucket gave {target} {gift}."

            self.send(
                Message(
                    text=msg),
                thread_id=thread_id,
                thread_type=thread_type)

    def add_new_timer(self, message_object, thread_id, thread_type):
        
        user = self.KEYWORDS[r'\$USER']
        
        capture = re.findall(self.TIMER_PATTERN, message_object.text)[0]

        if thread_type == ThreadType.GROUP:
            ttype = 'GROUP'
        else:
            ttype = 'USER'
        
        self.TIMERS.add(thread_id, capture[0], [ttype, capture[1]])

        engCron = cd.get_description(capture[0])
        msg = f"Okay {user}. I'll say '{capture[1]}' {engCron.lower()}"

        self.send(Message(text=msg), thread_id=thread_id, thread_type=thread_type)

    def respond_with_help_doc(self, message_object, thread_id, thread_type):
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

    def global_quiet(self, message_object, thread_id, thread_type):
        minutes = int(re.findall(self.QUIET_PATTERN, message_object.text)[0])

        if minutes <= 60:
            msg = f"Okay, I'll be quiet for {minutes} minutes."
        else:
            minutes = 60
            msg = f"Err, I'll be quiet for an hour, but I wont be silenced."

        self.send(
            Message(
                text=msg),
            thread_id=thread_id,
            thread_type=thread_type)
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

    def check_band_name(self, message_object, thread_id, thread_type):
        bandName = re.findall(self.BAND_PATTERN, message_object.text)[0]
        if not self.BANDS.has(bandName):
            self.BANDS.add(bandName)
            if random.random() < self.BAND_NAME_PROB:
                genre = self.KEYWORDS[r'\$GENRE'](None)
                self.send(
                    Message(
                        text=f'{message_object.text} would be a good name for a {genre} band.'),
                    thread_id=thread_id,
                    thread_type=thread_type)

    def respond_to_message(self, message_object, thread_id, thread_type):

        match = self.RESPONSES.check(message_object.text)

        if match is not None:

            trigger = match[0]
            response = match[1]
            captures = match[2]

            attachments = None
            if re.search(self.URL_PATTERN, response):
                attachments = re.findall(self.URL_PATTERN, response)
                response = re.sub(self.URL_PATTERN, '', response)
                print(attachments)

            if isinstance(response, list):
                response = random.choice(response)

            response = self.apply_keywords(response)

            for capture in captures:
                response = re.sub(r"\$WORD", capture, response, count=1)

            response = re.sub(r'\b([aA])\b(?=\s+[aeiouAEIOU])',r'\1n',response)
            response = re.sub(r'\b([aA][nN])\b(?=\s+[^aeiouAEIOU])',r'a',response)

            if response + ''.join(attachments) != self.HISTORY['sent'][thread_id][-1]:
                if attachments is not None:
                    self.sendRemoteFiles(attachments, Message(text=response), thread_id=thread_id, thread_type=thread_type)
                else:
                    self.send(Message(text=response), thread_id=thread_id, thread_type=thread_type)
                self.add_to_sent_history(Message(text=response), thread_id)
                return True
        
        return False

    def onPeopleAdded(self, added_ids, author_id, thread_id):
        self.markAsRead(thread_id)
        self.respond_with_help_doc(
            Message(
                text='bucket help'),
            thread_id,
            ThreadType.GROUP)

    def onPendingMessage(self, thread_id, thread_type, metadata, msg):
        self.moveThreads(ThreadLocation.INBOX, thread_id)
        self.markAsRead(thread_id)
        self.respond_with_help_doc(
            Message(
                text='bucket help'),
            thread_id,
            thread_type)                         

    def onMessage(
            self,
            author_id,
            message_object,
            thread_id,
            thread_type,
            **kwargs):

        self.markAsDelivered(thread_id, message_object.uid)
        self.markAsRead(thread_id)

        USER = self.fetchUserInfo(author_id)[f'{author_id}']

        if thread_type == ThreadType.GROUP:
            ALLUSERS = [user for uid, user in self.fetchUserInfo(
                *self.fetchGroupInfo(thread_id)[thread_id].participants).items() if user.first_name != 'Bucket']
        else:
            ALLUSERS = [USER]

        self.KEYWORDS = {
            r"\$USER": USER.first_name,
            r"\$RANDOM": lambda _: random.choice(ALLUSERS).first_name,
            r"\$RAND(\d+)": lambda x: str(random.randint(1, int(x))),
        }

        for key in self.wordLists:
            self.KEYWORDS[r'\$'+key.upper()] = lambda _, k=key: random.choice(self.wordLists[k])
            self.KEYWORDS[r'\$(\w+)_'+key.upper()] = lambda s, k=key: random.choice([n for n in self.wordLists[k] if n[:len(s)]==s.lower()]+[''])

        messageHandled = True

        # Message handler
        if author_id != self.uid:
            self.add_to_message_history(message_object, thread_id)
            # Add and item
            if re.match(self.NEW_ITEM_PATTERN, message_object.text):
                self.add_to_bucket(message_object, thread_id, thread_type)
            # Give an item
            elif re.match(self.GIVE_ITEM_PATTERN, message_object.text):
                self.give_item_to(message_object, thread_id, thread_type)
            # Add a response
            elif re.match(self.NEW_RESPONSE_PATTERN, message_object.text):
                self.add_to_responses(
                    message_object,
                    thread_id,
                    thread_type,
                    responseType='then')
            # Add a choice response
            elif re.match(self.NEW_CHOICE_PATTERN, message_object.text):
                self.add_to_responses(
                    message_object,
                    thread_id,
                    thread_type,
                    responseType='choice')
            # Remove a response
            elif re.match(self.DELETE_RESPONSE_PATTERN, message_object.text):
                self.delete_response(message_object, thread_id, thread_type)
            # Look up help
            elif re.match(self.HELP_PATTERN, message_object.text):
                self.respond_with_help_doc(
                    message_object, thread_id, thread_type)
            # Look for quiet command
            elif re.match(self.QUIET_PATTERN, message_object.text):
                self.global_quiet(message_object, thread_id, thread_type)
            # Look for a new timer 
            elif re.match(self.TIMER_PATTERN, message_object.text):
                self.add_new_timer(message_object, thread_id, thread_type)
            # Look for a reponse
            elif self.last_message_was_haiku(thread_id):
                self.HISTORY['message'][thread_id] = []
                self.send(
                    Message(
                        text='Was that a haiku?'),
                    thread_id=thread_id,
                    thread_type=thread_type)
            else:
                messageHandled = False

            if not messageHandled and (
                random.random() < self.RESPONSE_PROB or re.search(
                    'bucket',
                    message_object.text,
                    flags=re.IGNORECASE)):
                messageHandled = self.respond_to_message(
                    message_object, thread_id, thread_type)
            if not messageHandled and re.match(
                    self.BAND_PATTERN, message_object.text):
                self.check_band_name(message_object, thread_id, thread_type)


bucket = Bucket()
bucket.listen()
