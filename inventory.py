import re
import json
import pickle
import random


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