import requests
from dotenv import load_dotenv
import os
import schedule
import time
from scraper import get_new_jobs


# Load .env file from .venv directory
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

def get_chat_id():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not found. Make sure .env is correctly set up.")
        return None
    
    response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates")
    updates = response.json()
    
    if not updates.get("ok"):
        print("Telegram API Error:", updates.get("description", "Unknown error"))
        return None
        
    results = updates.get("result", [])
    if not results:
        print("Error: No messages found. Please send a message to your Telegram bot first, then run this script.")
        return None
        
    return results[0]["message"]["chat"]["id"]

def send_message(chat_id, text):
    if not chat_id:
        print("Error: chat_id is invalid or None. Cannot send message.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload)
    print(response.json())

chat_id = get_chat_id()
if chat_id:
    jobs = get_new_jobs()
    if not jobs:
        send_message(chat_id,"No new jobs found.")
    else:
        for job in jobs:
            message = f"{job['company']}-{job['title']}\nLocation:{job['location']}\nLink:{job['url']}"
            send_message(chat_id,message)
#to schedule  and time for scraper

def job():
   jobs = get_new_jobs()
   for j in jobs:
      send_message(f"{j['title']}-{j['link']}")

schedule.every(4).hours.do(job)

while True:
   schedule.run_pending()
   time.sleep(60)