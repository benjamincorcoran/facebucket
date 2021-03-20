#! /usr/bin/python
# Filename: functions.py

# Helper functions for the facebook bucket bot

import re
import os
import glob
import json
import fbchat
import pickle
import getpass


fbchat._util.USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36"]


SESSION_PATH = './assets/SESSION.pickle'


def create_session():
    '''
    Create and pickle the fbchat cookies for a persistent session
    '''
    email = input('Email Address: ')
    pw = getpass.getpass('Pass: ')
    client = fbchat.Client(email, pw)

    with open(SESSION_PATH, 'wb') as f:
        pickle.dump(client.getSession(), f)


def load_data(path):
    '''
    Load json data into Buckets memory from the data directory

    Args:
        path (str): path to the data directory
    Returns:
        dict: Dictionary containing all the data
    '''
    data = {}

    for path in glob.glob(f'{path}/*.json'):
        fileName = os.path.splitext(os.path.basename(path))[0]

        with open(path) as f:
            data[fileName] = json.load(f)

    return data


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
