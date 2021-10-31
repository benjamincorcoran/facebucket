import re
import json
import fbchat 

from importlib import resources

from . import assets
from .functions import load_word_lists
from .responder import Responder
from .inventory import LimitedInventory
from .signals import events


class Bucket(fbchat.Listener):

    def __init__(self, session, **kwargs):
        super().__init__(session=session, chat_on=True, foreground=True)
        self.client = fbchat.Client(session=session)

        self.id = session.user.id

        self.actions = {}
        self.probability = {}
        self.assets = {}

        self.load_assets()

        self.responder = Responder(resources.path(assets, 'responses.json').__enter__())
        self.inventory = LimitedInventory(resources.path(assets, 'inventory.json').__enter__(), 30)

    
    def load_assets(self):

        for asset in resources.contents(assets):

            if asset.split('.')[-1] in ['txt','json']:
                asset_text = resources.read_text(assets, asset)

                if asset[-4:] == '.txt':
                    self.assets[asset[:-4]] = asset_text

                elif asset == 'probability.json':
                    self.probability = json.loads(asset_text)

                elif asset == 'actions.json':
                    self.add_actions(**json.loads(asset_text))
        


    def set_probability(self, **kwargs):
        if all(k in self.probability.keys() for k in kwargs.keys()):
            self.probability.update(kwargs)

            with open(resources.path(assets, 'probability.json').__enter__(), 'w') as f:
                json.dump(self.probability, f)

    
    def add_actions(self, **kwargs):
        for action, trigger in kwargs.items():
            self.actions[action] = re.compile(trigger, flags=re.DOTALL+re.IGNORECASE)


    def run(self):
        for event in self.listen():
            events.send(type(event), event=event, bucket=self)
    
