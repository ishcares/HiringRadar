---
title: HiringRadar
emoji: 🎯
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# HiringRadar 🎯


## The Problem
Freshers in India miss job and internship openings at top product companies 
like Razorpay, CRED, and Groww — not because they aren't qualified, but 
because they find out too late. By the time it shows up on LinkedIn or 
Naukri, hundreds have already applied.

## What it does
HiringRadar is a Telegram bot that scrapes job listings directly from 
top Indian product company career pages the moment they're posted and 
sends them straight to you on Telegram — no middleman, no delay.

## Companies it tracks
- Razorpay
- PhonePe
- Groww
- CRED

## How to use it
1. Clone the repo
2. Add your bot token to `.env`
3. Run `python bot.py`

## Tech stack
- Python
- BeautifulSoup
- Requests
- Telegram Bot API

## Coming soon
- More product companies
- Domain filtering (ML, backend, frontend)
- Internship alerts
