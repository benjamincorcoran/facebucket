import re
import json 
import pycron

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
        if thread_id in self.rawResponses.keys():
            self.rawResponses[thread_id] = {k:[t,v] for k,[t,v] in self.rawResponses[thread_id].items() if v.lower() != trigger.lower()}
            self.save()
            self.load()
