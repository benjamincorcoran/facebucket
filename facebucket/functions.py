import os 
import re
import glob
import json
import fbchat
import getpass
import random
import requests

import nltk
nltk.download('stopwords')
from nltk.corpus import stopwords

from . import COOKIES_PATH, GIPHY_PATH

STOPWORDS = set(stopwords.words('english'))


def get_cookies_from_login(cookies_path=COOKIES_PATH):
    '''
    Log in with session and save cookies into a JSON
    file at COOKIES_PATH
    '''
    usr = input('Email address: ')
    psw = getpass.getpass('Password: ')

    session = fbchat.Session.login(usr, psw)

    with open(COOKIES_PATH, 'w') as f:
        json.dump(session.get_cookies(), f)

    return session


def get_session_from_cookies(cookies_path=COOKIES_PATH):
    '''
    Get a fbchat session from a saved cookies path
    '''
    with open(COOKIES_PATH, 'r') as f:
        cookies = json.load(f)
    
    session = fbchat.Session.from_cookies(cookies)
    return session


def get_session(cookies_path=COOKIES_PATH):
    '''
    Get an fbchat session, attempt to load from saved cookies 
    else prompt for password. 
    '''
    if os.path.isfile(cookies_path):
        session = get_session_from_cookies(cookies_path=cookies_path)
        if session.is_logged_in():
            return session

    session = get_cookies_from_login(cookies_path=cookies_path)
    if session.is_logged_in():
        return session
    else:
        raise AssertionError('Unable to log-in to facebook.')


def load_word_lists(path):
    '''
    Load wordlists into Buckets memory from a wordlists directory

    Args:
        path (str): path to the wordlists folder
    Returns:
        dict: Dictionary of wordlists by type
    '''

    wordLists = {}

    for path in glob.glob(f'{path}/*.txt'):
        fileName = os.path.splitext(os.path.basename(path))[0]

        with open(path) as f:
            data = re.split('\n', f.read())

        if fileName == 'noun':
            data = [re.split(r',', noun) for noun in data if len(re.split(r',',noun)) == 2]
            
            wordLists['nouns'] = [line[1] for line in data]
            wordLists['noun'] = [line[0] for line in data]

        # Verb dataset has whitespace seperated conjugations
        elif fileName == 'verb':
            data = [re.split(r'\s+', verb) for verb in data if len(re.split(r'\s+', verb)) == 5]
            wordLists['verbing'] = [line[4] for line in data]
            wordLists['verbs'] = [line[1] for line in data]
            wordLists['verbed'] = [line[2] for line in data]
            wordLists['verb'] = [line[0] for line in data]

        else:
            wordLists[fileName] = data

    return wordLists


def get_keywords(event, bucket):


    keywords = {}
    if isinstance(event.thread, fbchat.User):
        user = bucket.client._fetch_info([event.thread.id])
        keywords.update({'\$USER': user[event.thread.id]['first_name'],
                         '\$RANDOM': lambda _: random.choice([user[event.thread.id]['first_name'], 'Bucket'])})
    else:
        thread = bucket.client.fetch_thread_info([event.thread.id]).__next__()
        participants = {}
        for participant in thread.participants:
            participants.update(bucket.client._fetch_info([participant.id]))

        author_name = participants[event.author.id]['first_name']
        participant_names = [p['first_name'] for k,p in participants.items()]

        keywords.update({'\$USER': author_name,
                         '\$RANDOM': lambda _: random.choice(participant_names)})

    return keywords


def get_unique_word(text):
    uncommon = [_ for _ in filter(lambda w: not w in STOPWORDS, text.split())]
    if uncommon:
        return random.choice(uncommon)
    else:
        return None


def get_gif(text) -> str:
    
    unique_word = get_unique_word(text)

    if unique_word is None:
        return None

    with open(GIPHY_PATH, 'r') as f:
        giphyKey = f.read()

    URL = 'https://api.giphy.com/v1/gifs/translate?'
    params = {'api_key': giphyKey, 's':unique_word, 'weirdness':random.randint(1,10)}
    resp = requests.get(URL, params=params)

    if len(resp.json()['data']) > 0:
        gifid = resp.json()['data']['id']
        return f'https://media.giphy.com/media/{gifid}/giphy.gif'
    else:
        return False