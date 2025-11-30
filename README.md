<h2> How to run the bot?** </h2>

Make sure you have python 3.9.6+ installed

Clone this repo: `git clone https://github.com/stetat/ToDo-bot.git`

Get into a newly cloned directory: `cd ToDo-bot`

Create a virtual environment `python -m venv .venv`

Activate virtual environment on Mac/Linux: source .venv/bin/activate on Windows (PowerShell terminal): `.venv\Scripts\Activate.ps1`

Install dependencies: `pip install -r requirements.txt`

Create a new file called .env, inside that file, add two variables: `PERPLEXITY_API_KEY="YOUR PERPLEXITY API" 
                                                                    BOT_TOKEN="YOUR TELEGRAM BOT TOKEN"`

Open a new terminal (let's call it t2, whereas main terminal is t1) (Both t1 and t2 should have the virtual environment open)

In t1 write this command, to start fastApi server: `fastapi dev main.py`

In t2 write this command, to start Telegram bot logic: `python tg_bot.py`

You can now move to your telegram bot and interact with it


<hr>

<h2>What can this bot do?</h2>
1. Create a new task'\n'
2. Show all users' tasks'\n'
3. Update the status for users' tasks'\n'
4. Delete tasks in bulk'\n'
5. Show done/incomplete statistics for the user'\n'
6. Get AI advice for any task ( limited by 5 requests per user per day )'\n'


