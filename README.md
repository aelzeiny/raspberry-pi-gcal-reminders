# Google Calendar Reminder Device
## I am an old man...

With Remote Work being the center of my life, I can be really bad at attending meetings on time. 
All discipline of what does and doesn't constitute "working hours" has completely eroded. 
I disconnect during the day and reconnect at night.

My phone is already oversaturated with notifications across Slack, Discord, Email, and social media.

I needed one device with a single purpose: to shout at me when I should be in a meeting.

## Technical Implementation
On my Rasberry PI is a CRON job that runs every minute, and executes this script.

1. Hit GCalendar's API to get recent events
2. Check SQLite DB to see if the event has been broadcasted yet
3. If the event has not been broadcasted, hit AWS's Polly API to generate text-to-speech of the event
4. Broadcast the event. Save the broadcast's ID into an SQLite DB.