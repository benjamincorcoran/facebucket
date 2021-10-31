import re 
import json 
import random
from importlib import resources
from . import assets
from .functions import load_word_lists



class Responder(object):

    def __init__(self, path):

        self.CLEAN_PATTERN = re.compile(r'[^A-Za-z0-9\s\$;]')
        self.path = path
        self.load()
        self.wordlists = load_word_lists(resources.path(assets, 'wordlists').__enter__())


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
    
    def apply_keywords(self, match, keywords):
        keywords[r"\$RAND(\d+)"] = lambda x: str(random.randint(1, int(x)))

        for key in self.wordlists:
            keywords[r'\$'+key.upper()] = lambda _, k=key: random.choice(self.wordlists[k])
            keywords[r'\$(\w+)_'+key.upper()] = lambda s, k=key: random.choice([n for n in self.wordlists[k] if n[:len(s)]==s.lower()]+[''])

        for keyword, replace in keywords.items():
            if callable(replace):
                for find in re.findall(keyword, match, flags=re.IGNORECASE):
                    match = re.sub(keyword, replace(find), match, count=1, flags=re.IGNORECASE)
            else:
                match = re.sub(keyword, replace, match, flags=re.IGNORECASE)
        return match

    def check(self, message, keywords):
        matches = []
        message = self.clean(message)
        for trigger, response in self.RESPONSES.items():
            check = re.search(trigger, message)
            if check:
                matches.append((trigger, response, check.groups()))

        if len(matches) > 0:
            ret = max(matches, key=lambda x: len(x[0].pattern))
            return self.apply_keywords(ret[1], keywords)
        else:
            return None

class MemoryResponder(Responder):
    def __init__(self, responses):

        self.CLEAN_PATTERN = re.compile(r'[^A-Za-z0-9\s\$;]')
        self.rawResponses = responses
        self.path = 'MEMORY'


        self.RESPONSES = {
            self.parse(trigger): response for trigger,
            response in self.rawResponses.items()}


