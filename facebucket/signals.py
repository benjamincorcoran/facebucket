import re
import fbchat 
import blinker
import datetime
import random

from .functions import get_gif, get_keywords

events = blinker.Signal()
actions = blinker.Signal()

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

    keywords = get_keywords(event, bucket)

    # Mark the message as read
    bucket.client.mark_as_read([event.thread], at=datetime.datetime.now())

    # If is a valid action 
    for action, pattern in bucket.actions.items():
        if pattern.match(event.message.text):
            return actions.send(action, pattern=pattern, event=event, bucket=bucket, keywords=keywords)
    
    # Else look for a saved message
    response = bucket.responder.check(event.message.text, keywords)
    if response is not None and random.random() < bucket.probability['response']:
        return event.thread.send_text(response)
    
    if random.random() < bucket.probability['gif']:
        pass



@events.connect_via(fbchat.PeopleAdded)
@events.connect_via(fbchat.PersonRemoved)
def on_person_added(sender, event: fbchat.PeopleAdded, bucket, keywords):
    '''
    Handle People being added and removed
    '''
    response = bucket.assets['sender']
    event.thread.send_text(response)


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
    value = float(value)
    bucket.set_probability(**{prob.lower():value})
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


