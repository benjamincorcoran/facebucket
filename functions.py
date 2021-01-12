#! /usr/bin/python
# Filename: functions.py

# Helper functions for the facebook bucket bot

import re
import os
import glob
import json


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
