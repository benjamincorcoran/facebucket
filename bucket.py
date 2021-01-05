import re
import json
import fbchat
import pickle
import random
import collections
import time
import contextlib

from fbchat import log, Client
from fbchat import Message, User, ThreadType, ThreadLocation

fbchat._util.USER_AGENTS    = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36"]
fbchat._state.FB_DTSG_REGEX = re.compile(r'"name":"fb_dtsg","value":"(.*?)"')

RESPONSE_PATH = 'RESPONSES.json'
ITEMS_PATH = 'ITEMS.json'
SESSION_PATH = 'SESSION.pickle'
HELP_PATH = 'HELP.json'

# Subclass fbchat.Client and override required methods
class Bucket(fbchat.Client):

    def __init__(self, *args, **kwargs):

        self.get_session()
        super(Bucket, self).__init__('<email>', '<password>', session_cookies=self.SESSION_COOKIES)

        self.CLEAN_PATTERN = re.compile(r'[^A-Za-z0-9\s\$;]')

        self.RESPONSES = self.load_responses()
        self.ITEMS = self.load_items()[0]
        self.RESPONSE_PROB = 0.8

        self.KEYWORDS = None

        self.NEW_RESPONSE_PATTERN = re.compile(r'if (.*) then (.*)', flags=re.IGNORECASE+re.DOTALL)
        self.NEW_CHOICE_PATTERN = re.compile(r'if (.*) choose (.*)', flags=re.IGNORECASE+re.DOTALL)
        self.DELETE_RESPONSE_PATTERN = re.compile(r'bucket no more (.*)', flags=re.IGNORECASE+re.DOTALL)
        self.NEW_ITEM_PATTERN = re.compile(r'give bucket (.*)', flags=re.IGNORECASE+re.DOTALL)
        self.GIVE_ITEM_PATTERN = re.compile(r'bucket give (\w+) a present', flags=re.IGNORECASE)
        self.HELP_PATTERN = re.compile(r'bucket help ?(.*)?', flags=re.IGNORECASE)
        self.QUIET_PATTERN = re.compile(r'bucket shut up (\d+)', flags=re.IGNORECASE)

        self.BUCKET_SIZE = 30

    def get_session(self):
        with open(SESSION_PATH,'rb') as f:
            self.SESSION_COOKIES = pickle.load(f)

    def clean_pattern(self, string):
        clean = re.sub(self.CLEAN_PATTERN, '', string)
        pattern = re.sub('\$WORD','([A-Za-z]+)',clean, flags=re.IGNORECASE)
        bordered = re.compile(rf'\b{pattern}\b', flags=re.IGNORECASE)

        return bordered

    def load_items(self, newItem=None, gift=False):
        with open(ITEMS_PATH) as f:
            items = json.load(f)
        
        dropped = None
        if newItem is not None:
            if len(items) >= self.BUCKET_SIZE and items:
                i = random.randint(0, len(self.ITEMS)-1)
                dropped = items.pop(i)
            
            items.append(newItem)
            with open(ITEMS_PATH, 'w') as f:
                f.write(json.dumps(items, indent=4))

        if gift is True and items:
             i = random.randint(0, len(self.ITEMS)-1)
             dropped = items.pop(i)
             with open(ITEMS_PATH, 'w') as f:
                f.write(json.dumps(items, indent=4))

        return items, dropped
    
    def load_responses(self, newResponse=None, delete=None):

        with open(RESPONSE_PATH) as f:
            responses = json.load(f)
        
        if newResponse is not None:
            responses[newResponse[0].lower()] = newResponse[1]
        
            with open(RESPONSE_PATH, 'w') as f:
                f.write(json.dumps(responses, indent=4))

        elif delete is not None and delete.lower() in responses.keys():
            del responses[delete.lower()]
        
            with open(RESPONSE_PATH, 'w') as f:
                f.write(json.dumps(responses, indent=4))

        regexResponses = {self.clean_pattern(pattern):response for pattern, response in responses.items()}
        return regexResponses
    
    @contextlib.contextmanager
    def appearing_in_thought(self, thread_id, thread_type):  
        # Create illusion of thought     
        self.setTypingStatus(fbchat.TypingStatus(1), thread_id=thread_id, thread_type=thread_type)
        time.sleep(int(random.random()*2))
        yield None
        self.setTypingStatus(fbchat.TypingStatus(0), thread_id=thread_id, thread_type=thread_type)

    def add_to_responses(self, message_object, thread_id, thread_type, responseType='then'):

        user = self.KEYWORDS['\$USER']

        with self.appearing_in_thought(thread_id, thread_type):
            if responseType == 'then':
                newResponse = re.findall(self.NEW_RESPONSE_PATTERN, message_object.text)
                newResponse = newResponse[0]
                msg = f"Okay {user}, if someone says '{newResponse[0]}' then I'll reply '{newResponse[1]}'."
            
            elif responseType == 'choice':
                newResponse = re.findall(self.NEW_CHOICE_PATTERN, message_object.text)[0]
                newResponse = (newResponse[0], [_.strip() for _ in  newResponse[1].split(';')])
                msg = f"Okay {user}, if someone says '{newResponse[0]}' then I'll reply with one of '{', '.join(newResponse[1])}'."
       
        self.RESPONSES = self.load_responses(newResponse=newResponse)
        self.send(Message(text=msg), thread_id=thread_id, thread_type=thread_type)

    def delete_response(self, message_object, thread_id, thread_type):

        with self.appearing_in_thought(thread_id, thread_type):
            trigger = re.findall(self.DELETE_RESPONSE_PATTERN, message_object.text)[0]
            self.RESPONSES = self.load_responses(delete=trigger)

        msg = f"Okay, I wont respond to '{trigger}' anymore :)"
        self.send(Message(text=msg), thread_id=thread_id, thread_type=thread_type)


    def add_to_bucket(self, message_object, thread_id, thread_type):

        with self.appearing_in_thought(thread_id, thread_type):
            newItem = re.findall(self.NEW_ITEM_PATTERN, message_object.text)[0]
            self.items, dropped = self.load_items(newItem=newItem)

        if dropped is None:
            msg = f"Bucket is holding {newItem}."
        else:
            msg = f"Bucket dropped {dropped}. Bucket is now holding {newItem}."
        
        self.send(Message(text=msg), thread_id=thread_id, thread_type=thread_type)

    def give_item_to(self, message_object, thread_id, thread_type):

        capture = re.findall(self.GIVE_ITEM_PATTERN, message_object.text)[0].title()

        if capture == 'Everyone' and thread_type == ThreadType.GROUP:
            users = self.fetchUserInfo(*self.fetchGroupInfo(thread_id)[thread_id].participants)
            targets = [user.first_name.title() for uid, user in users.items() if user.first_name.title() != 'Bot']
        elif capture == 'Everyone':
            targets = [self.fetchUserInfo(thread_id)[thread_id].first_name]
        else:
            targets = [capture]

        with self.appearing_in_thought(thread_id, thread_type):
            for target in targets:
                self.ITEMS, gift = self.load_items(gift=True)

                if gift is None:
                    msg = f"I'm empty :("
                    break
                else: 
                    msg = f"Bucket gave {target} {gift}."
                
                self.send(Message(text=msg), thread_id=thread_id, thread_type=thread_type)
        

    def respond_with_help_doc(self, message_object, thread_id, thread_type):
        with open(HELP_PATH) as f:
            helpText = json.load(f)

        specific = re.findall(self.HELP_PATTERN,message_object.text)[0]
        if specific != '':
            msg = helpText[specific.lower()]
        else:
            msg = helpText['help']
        
        
        self.send(Message(text=msg), thread_id=thread_id, thread_type=thread_type)

    def global_quiet(self, message_object, thread_id, thread_type):
        minutes = int(re.findall(self.QUIET_PATTERN,message_object.text)[0])

        if minutes <= 60:
            msg = f"Okay, I'll be quiet for {minutes} minutes."
        else:
            minutes = 60
            msg = f"Err, I'll be quiet for an hour, but I wont be silenced."

        self.send(Message(text=msg), thread_id=thread_id, thread_type=thread_type)
        self.stopListening()
        time.sleep(minutes*60)
        self.listen()

    def respond_to_message(self, message_object, thread_id, thread_type):
        incoming_msg = re.sub(self.CLEAN_PATTERN, '', message_object.text)
        
        matches = {}
        for pattern, response in self.RESPONSES.items():
            search = re.search(pattern, incoming_msg)
            if search:
                matches[pattern.pattern]=(response, search.groups())
        
        if len(matches) > 0:
            bestMatch = matches[max(matches.keys(), key=len)]
            response = bestMatch[0]
            captures = bestMatch[1]

            if isinstance(response, list):
                response = random.choice(response)

            for pattern, replacement in self.KEYWORDS.items():
                if callable(replacement):
                    for find in re.findall(pattern, response):
                        response = re.sub(pattern, replacement(find), response, count=1)
                else:
                    response = re.sub(pattern, replacement, response)

                for capture in captures:
                    response = re.sub(r"\$WORD",capture,response,count=1)

            self.send(Message(text=response, reply_to_id=message_object.uid), thread_id=thread_id, thread_type=thread_type)
           
    def onPeopleAdded(self, added_ids, author_id, thread_id):
        self.markAsRead(thread_id)
        self.respond_with_help_doc(Message(text='bucket help'), thread_id, ThreadType.GROUP)
    
    def onPendingMessage(self, thread_id, thread_type, metadata, msg):
        self.moveThreads(ThreadLocation.INBOX, thread_id)
        self.markAsRead(thread_id)
        self.respond_with_help_doc(Message(text='bucket help'), thread_id, ThreadType.GROUP)

    def onMessage(self, author_id, message_object, thread_id, thread_type, **kwargs):

        self.markAsDelivered(thread_id, message_object.uid)
        self.markAsRead(thread_id)

        USER = self.fetchUserInfo(author_id)[f'{author_id}']

        if thread_type == ThreadType.GROUP:
            ALLUSERS = [user for uid, user in self.fetchUserInfo(*self.fetchGroupInfo(thread_id)[thread_id].participants).items()]
        else:
            ALLUSERS = [USER]

        self.KEYWORDS = {
            "\$USER": USER.first_name,
            "\$RANDOM": random.choice(ALLUSERS).first_name,
            "\$RAND(\d+)": lambda x: str(random.randint(1,int(x)))
        } 

        # Message handler 
        if author_id != self.uid:
            # Add and item
            if re.match(self.NEW_ITEM_PATTERN, message_object.text):
                self.add_to_bucket(message_object, thread_id, thread_type)
            # Give an item
            elif re.match(self.GIVE_ITEM_PATTERN, message_object.text):
                self.give_item_to(message_object, thread_id, thread_type)
            # Add a response
            elif re.match(self.NEW_RESPONSE_PATTERN, message_object.text):
                self.add_to_responses(message_object, thread_id, thread_type, responseType='then')
            # Add a choice response
            elif re.match(self.NEW_CHOICE_PATTERN, message_object.text):
                self.add_to_responses(message_object, thread_id, thread_type, responseType='choice')
            # Remove a response
            elif re.match(self.DELETE_RESPONSE_PATTERN, message_object.text):
                self.delete_response(message_object, thread_id, thread_type)
            # Look up help 
            elif re.match(self.HELP_PATTERN, message_object.text):
                self.respond_with_help_doc(message_object, thread_id, thread_type)
            # Look for quiet command
            elif re.match(self.QUIET_PATTERN, message_object.text):
                self.global_quiet(message_object, thread_id, thread_type)
            # Look for a reponse
            elif random.random() < self.RESPONSE_PROB:
                self.respond_to_message(message_object, thread_id, thread_type)
                


bucket = Bucket()
bucket.listen()