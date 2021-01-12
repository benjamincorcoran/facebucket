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
            data = re.split('\n',f.read())
        
        # Verb dataset has whitespace seperated conjugations
        if fileName == 'verb':
            data = [re.split('\s+', verb) for verb in data]
        
        wordLists[fileName] = data
    
    return wordLists
