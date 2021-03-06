from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
import json
import requests
import unicodedata
import os
import praw
import bs4

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db = SQLAlchemy(app)
reddit = praw.Reddit(client_id=os.environ['PRAW_CLIENT_ID'],
                     client_secret=os.environ['PRAW_CLIENT_SECRET'],
                     user_agent='a facebook messenger bot')
FB_PAT = os.environ['FB_PAT']

quick_replies_list = [{
        "content_type":"text",
        "title":"Meme",
        "payload":"Meme",
    },
    {
        "content_type":"text",
        "title":"Motivation",
        "payload":"Motivation",
    },
    {
        "content_type":"text",
        "title":"Shower Thoughts",
        "payload":"ShowerThoughts",
    },
    {
        "content_type":"text",
        "title":"Jokes",
        "payload":"Jokes",
    }]

@app.route('/', methods=['GET'])
def handle_verification():
    print("Handling Verification.")
    if request.args.get('hub.verify_token', '') == os.environ['VERIFY_TOKEN']:
        print("Verification successful!")
        return request.args.get('hub.challenge', '')
    else:
        print("Verification failed!")
        return 'Error, wrong validation token'

@app.route('/', methods=['POST'])
def handle_messages():
    print("Handling Messages")
    payload = request.get_data()
    print(payload)
    for sender, message in messaging_events(payload):
        print("Incoming from {}: {}".format(sender, message))
        process_message(sender, message)
    return "ok"

def messaging_events(payload):
    """Generate tuples of (sender_id, message_text) from the
    provided payload.
    """
    data = json.loads(payload)
    messaging_events = data["entry"][0]["messaging"]
    for event in messaging_events:
        if "message" in event and "quick_reply" in event["message"] and "payload" in event["message"]["quick_reply"]:
            yield event["sender"]["id"], event["message"]["quick_reply"]["payload"].encode('unicode_escape')
        elif "message" in event and "text" in event["message"]:
            yield event["sender"]["id"], event["message"]["text"].encode('unicode_escape')
        else:
            yield event["sender"]["id"], "I can't echo this"


def process_message(recipient, message):
    try:
        message = message.decode('ascii')
    except AttributeError:
        pass

    command = message.split()[0].lower()

    myUser = get_or_create(db.session, Users, name=recipient)

    if command == 'images':
        search_images(message, recipient)
    elif command == 'define':
        search_definitions(message, recipient)
    elif command == 'manga':
        search_manga(message, recipient)
    elif command in ['shower', 'showerthoughts']:
        subreddit_name = 'showerthoughts'
        payload = get_new_self_post(subreddit_name, myUser)
        send_text(recipient, payload['title'], quick_replies_list)
    elif command in ['joke', 'jokes']:
        subreddit_name = 'jokes'
        payload = get_new_self_post(subreddit_name, myUser)
        send_text(recipient, payload['title'])
        send_text(recipient, payload['body'], quick_replies_list)
    elif command in ['meme', 'memes']:
        subreddit_name = 'meme'
        payload = get_post_image(subreddit_name, myUser)
        send_image(recipient, payload, quick_replies_list)
    elif command in ['motivation', 'getmotivated']:
        subreddit_name = 'getmotivated'
        payload = get_post_image(subreddit_name, myUser)
        send_image(recipient, payload, quick_replies_list)
    elif command in ['commands', 'help']:
        send_commands_list(recipient)
    else:
        send_text(recipient, "Unknown command. Send 'commands' or 'help' to get the list of available commands.")

def get_new_self_post(subreddit_name, myUser):
    payload = {}

    for submission in reddit.subreddit(subreddit_name).hot(limit=None):
        if ((submission.is_self == True) and ( submission.link_flair_text is None)):
            query_result = Posts.query.filter(Posts.name == submission.id).first()

            if query_result is None:
                myPost = Posts(submission.id, submission.title)
                myUser.posts.append(myPost)
                db.session.commit()
                payload['title'] = submission.title
                payload['body'] = submission.selftext
                break
            elif myUser not in query_result.users:
                myUser.posts.append(query_result)
                db.session.commit()
                payload['title'] = submission.title
                payload['body'] = submission.selftext
                break
            else:
                continue

    return payload

def get_post_image(subreddit_name, myUser):
    payload = "http://imgur.com/WeyNGtQ.jpg"

    for submission in reddit.subreddit(subreddit_name).hot(limit=None):
        if (submission.link_flair_css_class == 'image') or ((submission.is_self != True) and ((".jpg" in submission.url) or (".png" in submission.url))):
            query_result = Posts.query.filter(Posts.name == submission.id).first()
            if query_result is None:
                myPost = Posts(submission.id, submission.url)
                myUser.posts.append(myPost)
                db.session.commit()
                payload = submission.url
                break
            elif myUser not in query_result.users:
                myUser.posts.append(query_result)
                db.session.commit()
                payload = submission.url
                break
            else:
                continue

    return payload

def search_images(message, recipient):
    if '*' in message:
        index = int(message.split('*')[1])
        search_list = message.split('*')[0].split()
    else:
        index = 0
        search_list = message.split()

    if len(search_list) > 1:
        url = 'https://www.googleapis.com/customsearch/v1?key=' + os.environ['API_KEY'] + '&cx=' + os.environ['SE_ID'] + '&searchType=image&q=' + '+'.join(search_list[1:])
        res = requests.get(url)
        images = []

        data = res.json()
        items = data['items']
        for item in items:
            link = item['link']
            if '.jpg' in link:
                images.append(link)

        if(len(images) > 0):
            quick_reply = [{
                "content_type": "text",
                "title": "More images",
                "payload": " ".join(search_list) + ' *' + str(index + 1)
            }]

            for i in range(3):
                if(i + (index * 3) < len(images)):
                    send_image(recipient, images[i + (index * 3)], quick_reply)
                else:
                    send_text(recipient, 'No more images.')
        else:
            send_text(recipient, "No image found.")
    else:
        send_text(recipient, "Type 'images' plus search term. Ex: 'images james reid'")

def search_definitions(message, recipient):
    search_list = message.split()

    if len(search_list) > 1:
        url = 'https://www.merriam-webster.com/dictionary/' + search_list[1]
        res = requests.get(url)
        soup = bs4.BeautifulSoup(res.text, "html.parser")
        lis = soup.select('.definition-list')[0].select('li')

        if(len(lis) > 1):
            for index, li in enumerate(lis):
                definition = str(index + 1) + '.'
                spans = li.findAll('span', { 'class' : None })

                for span in spans:
                    definition += '\t' + unicodedata.normalize("NFKD", span.getText()) + '\n'

                send_text(recipient, definition)
        else:
            send_text(recipient, "No definition found.")
    else:
        send_text(recipient, "Type 'define' plus search term. Ex: 'define programming'")

def search_manga(message, recipient):
    #FORMAT: manga title *chapter *page
    if '*' in message:
        chapter = int(message.split('*')[1])
        page = int(message.split('*')[2])
        search_list = message.split('*')[0].split()
    else:
        search_list = message.split()

    if len(search_list) > 1:
        url = 'http://www.mangareader.net'
        res = requests.get(url + '/search/?w=' + '+'.join(search_list[1:]))
        soup = bs4.BeautifulSoup(res.text, "html.parser")
        manga_results = soup.select('.mangaresultitem .manga_name a')

        if len(manga_results) > 0:
            if '*' in text:
                print(url + manga_results[0].attrs['href'] + '/' + str(chapter) + '/' + str(page))
                res = requests.get(url + manga_results[0].attrs['href'] + '/' + str(chapter) + '/' + str(page))
            else:
                res = requests.get(url + manga_results[0].attrs['href'])
                soup = bs4.BeautifulSoup(res.text, "html.parser")
                latest_chapters = soup.select('#latestchapters li a')
                res = requests.get(url + latest_chapters[0].attrs['href'])
                page = 1
                print(url + latest_chapters[0].attrs['href'])

            soup = bs4.BeautifulSoup(res.text, "html.parser")
            img_element = soup.select('#img')
            title = soup.select('#mangainfo h1')[0].getText()
            title_array = title.split(" ")
            chapter = int(title_array[len(title_array) - 1])
            title += ' - Page ' + str(page)

            if len(img_element) > 0:
                img_url = img_element[0].get('src')
                text = text.split('*')[0]
                quick_reply = [
                    {
                        "content_type": "text",
                        "title": "Next Page",
                        "payload": text + ' *' + str(chapter) + ' *' + str(page + 1)
                    },
                    {
                        "content_type": "text",
                        "title": "Previous Chapter",
                        "payload": text + ' *' + str(chapter - 1) + ' *1'
                    },
                    {
                        "content_type": "text",
                        "title": "Next Chapter",
                        "payload": text + ' *' + str(chapter + 1) + ' *1'
                    }
                ]

                send_text(recipient, title)
                send_image(recipient, img_url, quick_reply)
            else:
                send_text(recipient, 'No image found.')
        else:
            send_text(recipient, 'Manga not found.')
    else:
        send_text(recipient, "Type 'manga' plus manga title. Ex: 'manga one piece'")

def send_text(recipient, payload, quick_replies=[]):
    if len(quick_replies) > 0:
        r = requests.post("https://graph.facebook.com/v2.6/me/messages",
            params={"access_token": FB_PAT},
            data=json.dumps({
                "recipient": {"id": recipient},
                "message": {
                            "text": payload,
                            "quick_replies":quick_replies
                        }
            }),
            headers={'Content-type': 'application/json'})
    else:
        r = requests.post("https://graph.facebook.com/v2.6/me/messages",
            params={"access_token": FB_PAT},
            data=json.dumps({
                "recipient": {"id": recipient},
                "message": {
                            "text": payload
                        }
            }),
            headers={'Content-type': 'application/json'})

    if r.status_code != requests.codes.ok:
        print(r.text)

def send_image(recipient, payload, quick_replies=[]):
    print('Sending image: {}'.format(payload))

    if len(quick_replies) > 0:
        r = requests.post("https://graph.facebook.com/v2.6/me/messages",
            params={"access_token": FB_PAT},
            data=json.dumps({
                "recipient": {"id": recipient},
                "message": {
                                "attachment": {
                                    "type": "image",
                                    "payload": {
                                        "url": payload
                                    }
                                },
                                "quick_replies": quick_replies
                            }
            }),
            headers={'Content-type': 'application/json'})
    else:
        r = requests.post("https://graph.facebook.com/v2.6/me/messages",
            params={"access_token": FB_PAT},
            data=json.dumps({
                "recipient": {"id": recipient},
                "message": {
                                "attachment": {
                                    "type": "image",
                                    "payload": {
                                        "url": payload
                                    }
                                }
                            }
            }),
            headers={'Content-type': 'application/json'})

    if r.status_code != requests.codes.ok:
        print(r.text)

def send_commands_list(recipient):
    r = requests.post("https://graph.facebook.com/v2.6/me/messages",
        params={"access_token": FB_PAT},
        data=json.dumps({
            "recipient": {"id": recipient},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload":{
                        "template_type": "list",
                        "top_element_style": "compact",
                        "elements":[
                            {
                                "title": "Images",
                                "subtitle": "Retrieves images. Example: 'Images cute puppies'"
                            },
                            {
                                "title": "Define",
                                "subtitle": "Retrieves the definition of a word. Example: 'Define programming'" 
                            },
                            {
                                "title": "Manga",
                                "subtitle": "Retrieves the latest chapter of a manga. Example:'Manga Pne Piece'" 
                            }
                        ]
                    }
                }
            }
        }),
        headers={'Content-type': 'application/json'})

    if r.status_code != requests.codes.ok:
        print(r.text)

    r = requests.post("https://graph.facebook.com/v2.6/me/messages",
        params={"access_token": FB_PAT},
        data=json.dumps({
            "recipient": {"id": recipient},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload":{
                        "template_type": "list",
                        "top_element_style": "compact",
                        "elements":[
                            {
                                "title": "Motivation",
                                "subtitle": "Replies a motivational image or text. Just send 'Motivation' to the bot."
                            },
                            {
                                "title": "Meme",
                                "subtitle": "Replies a meme image. Just send 'Meme' to the bot."
                            },
                            {
                                "title": "Jokes",
                                "subtitle": "Replies a joke. Just send 'Jokes' to the bot." 
                            },
                            {
                                "title": "Shower Thoughts",
                                "subtitle": "Replies a random thought people had. Just send 'ShowerThoughts' to the bot." 
                            }
                        ]
                    }
                }
            }
        }),
        headers={'Content-type': 'application/json'})

    if r.status_code != requests.codes.ok:
        print(r.text)

def get_or_create(session, model, **kwargs):
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance
    else:
        instance = model(**kwargs)
        session.add(instance)
        session.commit()
        return instance

relationship_table=db.Table('relationship_table',                            
    db.Column('user_id', db.Integer,db.ForeignKey('users.id'), nullable=False),
    db.Column('post_id',db.Integer,db.ForeignKey('posts.id'),nullable=False),
    db.PrimaryKeyConstraint('user_id', 'post_id') )
 
class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255),nullable=False)
    posts=db.relationship('Posts', secondary=relationship_table, backref='users' )  

    def __init__(self, name=None):
        self.name = name
 
class Posts(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    name=db.Column(db.String, unique=True, nullable=False)
    url=db.Column(db.String, nullable=False)

    def __init__(self, name=None, url=None):
        self.name = name
        self.url = url

if __name__ == '__main__':
    app.run()
