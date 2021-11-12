import re
import json
import fbchat 
import datetime

from importlib import resources

from fbchat._listen import *
from fbchat import _util, _exception, _session, _graphql, _events

from . import assets
from .functions import load_word_lists
from .responder import Responder, TimedResponder
from .inventory import LimitedInventory
from .signals import events, delayed_actions


class Bucket(fbchat.Listener):

    def __init__(self, session, **kwargs):
        super().__init__(session=session, chat_on=True, foreground=True)
        self.client = fbchat.Client(session=session)

        self.id = session.user.id

        self.actions = {}
        self.probability = {}
        self.assets = {}
        self.delayed_actions = []

        self.help = self.load_assets('help.txt')
        self.probability = self.load_assets('probability.json')
        
        
        self.responder = Responder(resources.path(assets, 'responses.json').__enter__())
        self.timed_responder = TimedResponder(resources.path(assets, 'timed_responses.json').__enter__())
        self.inventory = LimitedInventory(resources.path(assets, 'inventory.json').__enter__(), 30)

        self.add_actions(**self.load_assets('actions.json'))

    
    def load_assets(self, asset_name):

        asset_text = resources.read_text(assets, asset_name)
        if asset_name.split('.')[-1] == 'json':
            return json.loads(asset_text)
        else:
            return asset_text


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


    def check_for_delayed_actions(self):

        if len(self.delayed_actions) == 0:
            return None

        drop_actions = []
        for i, (runtime, action, meta) in enumerate(self.delayed_actions):
            if runtime <= datetime.datetime.now():
                delayed_actions.send(action, meta=meta, bucket=self)
                drop_actions.append(i)
        
        for i in drop_actions:
            self.delayed_actions.pop(i)
            

    def check_for_timed_actions(self):
        response = self.timed_responder.check()
        if response is not None:
            delayed_actions.send(response, meta={}, bucket=self)


    def listen(self):
        """Run the listening loop continually.

        This is a blocking call, that will yield events as they arrive.

        This will automatically reconnect on errors, except if the errors are one of
        `PleaseRefresh` or `NotLoggedIn`.

        Example:
            Print events continually.

            >>> for event in listener.listen():
            ...     print(event)
        """
        if self._sequence_id is None:
            self._sequence_id = fetch_sequence_id(self.session)

        # Make sure we're connected
        while not self._reconnect():
            pass

        yield _events.Connect()

        while True:

            self.check_for_delayed_actions()

            rc = self._mqtt.loop(timeout=1.0)

            # The sequence ID was reset in _handle_ms
            # TODO: Signal to the user that they should reload their data!
            if self._sequence_id is None:
                self._sequence_id = fetch_sequence_id(self.session)
                self._messenger_queue_publish()

            # If disconnect() has been called
            # Beware, internal API, may have to change this to something more stable!
            if self._mqtt._state == paho.mqtt.client.mqtt_cs_disconnecting:
                break  # Stop listening

            if rc != paho.mqtt.client.MQTT_ERR_SUCCESS:
                # If known/expected error
                if rc == paho.mqtt.client.MQTT_ERR_CONN_LOST:
                    yield _events.Disconnect(reason="Connection lost, retrying")
                elif rc == paho.mqtt.client.MQTT_ERR_NOMEM:
                    # This error is wrongly classified
                    # See https://github.com/eclipse/paho.mqtt.python/issues/340
                    yield _events.Disconnect(reason="Connection error, retrying")
                elif rc == paho.mqtt.client.MQTT_ERR_CONN_REFUSED:
                    raise _exception.NotLoggedIn("MQTT connection refused")
                else:
                    err = paho.mqtt.client.error_string(rc)
                    log.error("MQTT Error: %s", err)
                    reason = "MQTT Error: {}, retrying".format(err)
                    yield _events.Disconnect(reason=reason)

                while not self._reconnect():
                    pass

                yield _events.Connect()

            if self._tmp_events:
                yield from self._tmp_events
                self._tmp_events = []

    
