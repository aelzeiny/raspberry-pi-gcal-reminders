import subprocess

import boto3
import datetime as dt
import os
import sqlite3
from tempfile import NamedTemporaryFile
import logging

import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pendulum
from contextlib import closing

# If modifying these scopes, delete the file token.pickle.
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly'
]

logging.basicConfig(
    format='[%(asctime)s][%(levelname)s] %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)


db = sqlite3.connect('reminders.db')
polly = boto3.Session(profile_name='personal').client('polly', region_name='us-west-1')

OFFSETS = [5, 0]
TIMEZONE = pendulum.timezone('America/Los_Angeles')


def init_db():
    with closing(db.cursor()) as c:
        c.execute('''
        CREATE TABLE IF NOT EXISTS reminders(
           cal_id VARCHAR(128) NOT NULL,
           uid VARCHAR(64) NOT NULL,
           offset INT NOT NULL,
           start_dttm TIMESTAMP NOT NULL,
           PRIMARY KEY (cal_id, uid, offset)
        );
        ''')
        db.commit()


def pendulum_to_dttm(pendo):
    return dt.datetime(
        pendo.year,
        pendo.month,
        pendo.day,
        pendo.hour,
        pendo.minute,
        pendo.second,
        pendo.microsecond
    )


def serialize(cal_id, e_id, offset, start):
    with closing(db.cursor()) as c:
        c.execute('''
            INSERT INTO reminders (cal_id, uid, offset, start_dttm)
            VALUES (?, ?, ?, ?)
        ''', (cal_id, e_id, offset, pendulum_to_dttm(start)))
        db.commit()


def announce(text, voice: str):
    logging.info('ANNOUNCEMENT: %s', text)
    # now vocalize
    response = polly.synthesize_speech(
        LanguageCode='en-US',
        OutputFormat='mp3',
        Text=text,
        TextType='text',
        VoiceId=voice
    )
    with NamedTemporaryFile('wb') as tmp:
        tmp.write(response['AudioStream'].read())
        tmp.flush()
        subprocess.run([f'mplayer -volume 100 {tmp.name}'], shell=True, stdout=subprocess.PIPE)


def load_or_request_creds(pickle_name):
    """
    If a user credential file already exists as a serialized pickle, load it up.
    Otherwise launch GOauth & get token.
    """
    creds = None
    if os.path.exists(pickle_name):
        with open(pickle_name, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(pickle_name, 'wb') as token:
            pickle.dump(creds, token)
    return build('calendar', 'v3', credentials=creds)


def get_recent_broadcasted_events(start_dttm: dt.datetime, end_dttm: dt.datetime):
    with closing(db.cursor()) as c:
        c.execute('''
            SELECT cal_id, uid, offset
            FROM reminders
            WHERE 
                start_dttm > ? AND
                start_dttm < ?
        ''', (start_dttm, end_dttm))
        return set(tuple(r) for r in c.fetchall())


def scan_calendar(cal_key, email, cal_id, voice):
    service = load_or_request_creds(f'{email}.pickle')
    # Call the Calendar API
    now = pendulum.now(tz=TIMEZONE)
    yesterday = pendulum_to_dttm(now - dt.timedelta(days=1))
    tomorrow = pendulum_to_dttm(now + dt.timedelta(days=1))
    print('Getting the upcoming events for ', cal_key)
    events_result = service.events().list(
        calendarId=cal_id, timeMin=yesterday.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    broadcasted = get_recent_broadcasted_events(yesterday, tomorrow)

    for event in events:
        for offset in OFFSETS:
            start = pendulum.parse(
                event['start'].get('dateTime', event['start'].get('date')),
                tz=pendulum.timezone(event['start'].get('timeZone', TIMEZONE.name))
            ).astimezone(TIMEZONE)
            if start >= tomorrow or start <= yesterday:
                continue
            e_id = event['id']
            offsetted_start = start - dt.timedelta(minutes=offset + 1)
            remaining_time = (start - now).in_minutes()

            broadcast_id = (cal_key, e_id, offset)
            has_attendies = 'attendees' in event and len(event['attendees']) > 1
            has_summary = 'summary' in event
            if offsetted_start <= now and broadcast_id not in broadcasted and (has_attendies or not has_summary):
                event_time = start.time().strftime('%I:%M')
                if not offset:
                    announcement = f'{event["summary"]}' if has_summary else f'You have a meeting at {event_time}'
                else:
                    announcement = f'{remaining_time} minute reminder for {event.get("summary", event_time)}'
                announce(announcement, voice)
                serialize(cal_key, e_id, offset, start)


if __name__ == '__main__':
    init_db()
    logging.info('heartbeating...')
    all_cals = {
        'primary': ('Ivy', 'ahmed.elzeiny@gmail.com', 'primary'),
        'Y.T.': ('Joey', 'ahmed.elzeiny@gmail.com', 'ahmedelzeiny@google.com')
    }

    for cal_key in all_cals:
        curr_voice, email, cal_id = all_cals[cal_key]
        scan_calendar(cal_key, email, cal_id, curr_voice)

    db.close()
