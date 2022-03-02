import re
import os
import time
import fbchat 
import blinker
import datetime
import random
import yt_dlp

from .functions import get_gif, get_keywords, send_file

events = blinker.Signal()
actions = blinker.Signal()
responses = blinker.Signal()
delayed_actions = blinker.Signal()


# Handle message events
@events.connect_via(fbchat.MessageEvent)
def on_message(sender, event: fbchat.MessageEvent, bucket):
    '''
    Handle all message events
    Args: 
        sender: Object that send the message
        event: The fbchat.event object 
        client: Bucket client object
    '''

    if event.author.id == bucket.id:
        return None

    # Mark the message as read
    bucket.client.mark_as_read([event.thread], at=datetime.datetime.now())

    if not isinstance(event.message.text, str):
        return None

    keywords = get_keywords(event, bucket)

    # If is a valid action 
    for action, pattern in bucket.actions.items():      
        if pattern.match(event.message.text):
            return actions.send(action, pattern=pattern, event=event, bucket=bucket, keywords=keywords)
    
    # Else look for a saved message
    response = bucket.responder.check(event.message.text, keywords)

    kwargs = dict(response=response, event=event, bucket=bucket)

    if response is not None:
        if re.findall('\$TIMEOUT', response):
            responses.send('timeout', **kwargs)
        elif re.findall('\$URL', response):
            responses.send('file',  **kwargs)
        else:
            responses.send('known_response',  **kwargs)
    else:
        responses.send('gif',  **kwargs)



@responses.connect_via('known_response')
def on_known_response(responsetype, response, event, bucket):
    if random.random() < bucket.probability['response']:
        event.thread.send_text(response)


@responses.connect_via('timeout')
def on_timeout_trigger(responsetype, response, event, bucket):
    response = response.replace('\$TIMEOUT').strip()
    event.thread.send_text(response)
    
    if not isinstance(event.thread, fbchat.Group):
        return None

    in_time = datetime.datetime.now() + datetime.timedelta(seconds=30)
    meta = dict(user_id = event.author.id, thread_id = event.thread.id)
    bucket.delayed_actions.append((in_time, 'time_in', meta))

    try:
        event.thread.remove_participant([event.author.id])
    except Exception as e:
        print(e)


@responses.connect_via('file')
def on_send_file(responsetype, response, event, bucket):
    if random.random() < bucket.probability['response']:
        url = re.findall('\$URL:(.*)', response)[0]
        send_file(url, bucket.client, event.thread)


@responses.connect_via('gif')
def on_send_gif(responsetype, response, event, bucket):
    if random.random() < bucket.probability['gif']:
        url = get_gif(event.message.text)
        send_file(url, bucket.client, event.thread)


@events.connect_via(fbchat.PeopleAdded)
@actions.connect_via('help')
def on_person_added(sender, event, bucket, **kwargs):
    '''
    Handle People being added and removed
    '''
    event.thread.send_text(bucket.help)


@actions.connect_via('quiet')
def on_global_quiet(sender, pattern, event, bucket, keywords):
    quiet_time = int(re.findall(pattern, event.message.text)[0])

    if quiet_time < 60:
        event.thread.send_text(f"Okay, I'll be quiet for {quiet_time} minutes")
        time.sleep(60*quiet_time)
    else:
        event.thread.send_text(f"Err... I'll be quiet for an hour.")
        time.sleep(60*60)



@actions.connect_via('new_response')
@actions.connect_via('new_choice')
@actions.connect_via('new_tree')
def on_new_response(sender, pattern, event, bucket, keywords):

    new_response = re.findall(pattern, event.message.text)[0]
    author = keywords['\$USER']

    confirm = f"Okay {author}, if someone says '{new_response[0]}' then I'll reply "

    if sender=='new_response':
        confirm += f"'{new_response[1]}'."
    elif sender=='new_choice':
        new_response = (new_response[0], [_.strip() for _ in new_response[1].split(';')])
        confirm += f"I'll reply with one of '{', '.join(new_response[1])}'."
    elif sender == 'new_tree':
        new_response = [new_response[0], json.loads(new_response[1])]
        confirm += f"'{new_response[1][0]}' then enter this tree {new_response[1][1]}."
    

    bucket.responder.add(*new_response)
    event.thread.send_text(confirm)


@actions.connect_via('set_probability')
def on_set_probability(sender, pattern, event, bucket, keywords):

    prob, value = re.findall(pattern, event.message.text)[0]
    bucket.set_probability(**{prob.lower():float(value)})

    event.thread.send_text(f'Probability of {prob} set to {value}.')


@actions.connect_via('delete_response')
def on_delete_response(sender, pattern, event, bucket, keywords):

    old_response = re.findall(pattern, event.message.text)[0]
    bucket.responder.remove(old_response)
    event.thread.send_text(f"Okay, I wont respond to '{old_response}' anymore.")


@actions.connect_via('new_item')
def on_new_item(sender, pattern, event, bucket, keywords):

    item = re.findall(pattern, event.message.text)[0]
    dropped = bucket.inventory.add(item)
    if dropped is None:
        confirm = f'*Bucket is holding {item}*'
    else:
        confirm = f'*Bucket dropped {dropped} so bucket could hold {item}.*'

    event.thread.send_text(confirm)


@actions.connect_via('give_item')
def on_give_item(sender, pattern, event, bucket, keywords):
    
    item = bucket.inventory.get()
    target = re.findall(pattern, event.message.text)[0]

    confirm = f'*Bucket gave {target} {item}.*'
    event.thread.send_text(confirm)    


@actions.connect_via('band_name')
def on_band_name(sender, pattern, event, bucket, keywords):
    if random.random() < bucket.probability['band']:
    
        band_name = re.findall(pattern, event.message.text)[0]
        response = f'{band_name} would be a good name for a $GENRE band.'
        response = bucket.responder.apply_keywords(response, keywords)
        event.thread.send_text(response)


@delayed_actions.connect_via('time_in')
def on_time_in(sender, meta, bucket):

    user_id = meta['user_id']
    thread_id = meta['thread_id']

    thread = bucket.client.fetch_thread_info([thread_id]).__next__()
    thread.add_participants([user_id])
    thread.send_text('I hope you learned your lesson.')


@actions.connect_via('youtube_url')
@actions.connect_via('twitter_url')
def on_video(sender, pattern, event, bucket, keywords):

    url = re.findall(pattern, event.message.text)[0]


    options = {'noplaylist':True,
               'outtmpl':'tmpfile',
               'format':'best'}

    try:            
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except:
        return None

    event.thread.send_text('Give me a minute...')
    
    try:
        with open('./tmpfile', 'rb') as f:
            video = f.read()
        
        files = bucket.client.upload([('tmpfile', video, 'video/mp4')])
        event.thread.send_files(files)

        os.unlink('./tmpfile')
    
    except:
        return None

    
    

