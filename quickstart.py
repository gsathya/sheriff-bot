# This Python file uses the following encoding: utf-8
import config
import json
import time

from httplib2 import Http

CURRENT_TREE_STATE = None
CURRENT_ROLL_STATE = None

CHAT_URL = config.chat_url
TREE_URL = 'https://v8-status.appspot.com/current?format=json'
ROLL_URL = 'https://chromium-review.googlesource.com/changes/?q=owner:v8-ci-autoroll-builder@chops-service-accounts.iam.gserviceaccount.com+project:chromium/src&n=1&o=MESSAGES'
MSG_HEADERS = {'Content-Type': 'application/json; charset=UTF-8'}


class TreeState():
    def __init__(self, is_open, message, date):
        self.is_open = is_open
        self.message = message
        self.date = date
        self.thread_name = None


class RollState():
    def __init__(self):
        self.date = None
        self.msg = None
        self.status = None
        self.version = None
        self.number = None
        self.thread_name = None


def make_widgets(status, time, version):
    widgets = [
        {
            "keyValue": {
                "topLabel": "Status",
                "content": status
            }
        },
        {
            "keyValue": {
                "topLabel": "Time",
                "content": time
            }
        }
    ]
    if version is not None:
        widgets.append({
            "keyValue": {
                "topLabel": "Version",
                "content": version
            }
        })
    return widgets


def make_cards(title, status, time, message, url_title, link, version=None):
    widgets = make_widgets(status, time, version)
    return [
        {
            "header": {
                "title": title,
            },
            "sections": [
                {
                    "widgets": widgets
                },
                {
                    "header": "Message",
                    "widgets": [
                        {
                            "textParagraph": {
                                "text": message
                            }
                        }
                    ]
                },
                {
                    "widgets": [
                        {
                            "buttons": [
                                {
                                    "textButton": {
                                        "text": "OPEN %s" % url_title,
                                        "onClick": {
                                                "openLink": {
                                                    "url": link
                                                }
                                        }
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]


def send_msg(cards, state):
    body = {'cards': cards}

    if state:
        body['thread'] = state.thread_id

    http_obj = Http()
    response, content = http_obj.request(
        uri=CHAT_URL,
        method='POST',
        headers=MSG_HEADERS,
        body=json.dumps(body),
    )

    content = json.loads(content)
    new_thread_id = content.get("thread", None)
    return new_thread_id


def waterfall_status():
    h = Http()
    resp, content = h.request(TREE_URL)
    if resp.status != 200:
        raise Exception(
            'Reponse status: %s, reason: %s' %
            (resp.status, resp.reason))

    tree_state = json.loads(content)

    return TreeState(tree_state['general_state'] == 'open',
                     tree_state['message'],
                     tree_state['date'])


def check_tree():
    global CURRENT_TREE_STATE
    try:
        tree_state = waterfall_status()
    except Exception as e:
        print e
        return

    if CURRENT_TREE_STATE and CURRENT_TREE_STATE.is_open == tree_state.is_open:
        return

    if tree_state.is_open:
        msg = "Passing"
    else:
        msg = "Broken"

    cards = make_cards(
        "Tree",
        msg,
        tree_state.date,
        tree_state.message,
        "TREE",
        "http://v8-status.appspot.com/")
    tree_state.thread_id = send_msg(cards, CURRENT_TREE_STATE)
    CURRENT_TREE_STATE = tree_state


def roll_status():
    h = Http()
    resp, content = h.request(ROLL_URL)
    if resp.status != 200:
        raise Exception(
            'Reponse status: %s, reason: %s' %
            (resp.status, resp.reason))

    content = content[4:]  # strip some leading garbage
    content = json.loads(content)[0]
    roll_state = RollState()

    for msg in reversed(content['messages']):
        tag = None
        message = None

        try:
            tag = msg['tag']
            message = msg['message']
        except KeyError as e:
            # found a message without these, let's ignore this and
            # check the other messages.
            print "Did not find key: %s" % e
            print "Full message: %s" % json.dumps(msg)
            continue

        if "CQ is trying the patch" in message:
            continue
        elif "This CL passed the CQ dry run" in message:
            break
        elif "autogenerated:gerrit:newPatchSet" in tag:
            break
        elif "autogenerated:gerrit:merged" in tag:
            roll_state.status = "Merged"
        elif "-Commit-Queue" in message:
            break
        elif "abandon" in tag:
            break
        else:
            roll_state.status = "Failed"

        roll_state.msg = msg["message"]
        roll_state.date = msg["date"]
        break

    version = content['subject'].split(' ')[-1]
    roll_state.version = version[:-1]  # remove ending '.'

    return roll_state


def check_roll():
    global CURRENT_ROLL_STATE

    try:
        roll_state = roll_status()
    except Exception as e:
        print e
        return

    if not roll_state.status:
        return

    if CURRENT_ROLL_STATE and CURRENT_ROLL_STATE.status == roll_state.status:
        return

    msg = "%s %s (%s) : %s" % (roll_state.status,
                               roll_state.version, roll_state.date, roll_state.msg)
    print msg

    cards = make_cards(
        "Roll",
        roll_state.status,
        roll_state.date,
        roll_state.msg,
        "CI",
        "https://chromium-review.googlesource.com/q/owner:v8-ci-autoroll-builder%2540chops-service-accounts.iam.gserviceaccount.com",
        roll_state.version)
    roll_state.thread_id = send_msg(cards, CURRENT_ROLL_STATE)
    CURRENT_ROLL_STATE = roll_state


def check():
    check_tree()
    check_roll()


def main():
    while True:
        check_tree()
        check_roll()

        time.sleep(5)


if __name__ == '__main__':
    main()
