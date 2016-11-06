# README #

# What is IonWatcherBot #

IonWatcherBot is a simple [Telegram bot](https://core.telegram.org/bots) which, when connected to a Torrent Server via network, is able to fetch information about runs in progress and send it to trusted users, without exposing the Torrent Server itself outside the network.

IonWatcherBot is currently in **early alpha version**, having decent basic functionality but needing a few quick fixes about the following limitations:  

* it does not yet use the Torrent Server API;
* it only connects to one Ion Torrent server;
* it uses Telegram usernames for authentication, which are unique but are changeable;
* it lacks administrative tools to remotely clear the logfile and data caches.


# How to install IonWatcherBot #

1 . Requisites:  

 * Python 3.5+ (I suggest [Anaconda Python](https://www.continuum.io/downloads))  
 * The [Beautiful Soup 4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) library (beautifulsoup4)  
 * The [Requests](http://docs.python-requests.org/en/master/) API (requests)  
 * The [Python Telegram Bot](https://github.com/python-telegram-bot/python-telegram-bot) library (python-telegram-bot).
  
2 . Download or clone the source code for IonWatcherBot to a computer with Internet access and with network connection to the Torrent Server.  

3 . Within the Telegram app, [create a new bot](https://core.telegram.org/bots#creating-a-new-bot). In short:  

 * Start a chat with @ BotFather  
 * Send the command `/newbot` to start creating the bot  
 * Choose a display name for the bot (i.e. "Ion Watcher")  
 * Choose a username for the bot (i.e. "IW05UH_bot")  
 * The BotFather will send you an Authorization Token. It's a unique identifier for the bot. Save this string, you will enter it on the bot's configuration file.  

4 . Personalize the `IonWatcher.cfg.EXAMPLE` file:  

 * rename or copy it to `IonWatcher.cfg`;  
 * on line 6, replace `aDdYoUrToKenHere:AskBotFatherForIt` with your bot's token;  
 * on line 8, replace `myserver.mydomain.edu` with your Torrent Server address;  
 * if needed, replace the default username on line 10;  
 * add your Telegram username as administrator on line 15, like this: `admins = MyTelegramUsername`.  

# Executing IonWatcherBot #

 * execute the script, e.g. from within the ionwatcherbot directory, type `python main.py` (or `python3` depending on your settings);  
 * enter the Torrent Server password.  

# Contacting the bot #

 * Start a chat with the username you chose for the bot (i.e. @ IW05UH_bot).  
 * Administrators have the right to approve or block an user that has asked to join the user queue, and to shut down the bot remotely via the unlisted command, `/kill`.  
 * Administrators and approved users have the rights to monitor runs on the Torrent Server and to view the user queue (Telegram users awaiting approval as bot users).  
 * Users in the queue and blocked users have no available action.  
 * Unknown users can add themselves to the queue.  
  

# LICENSE #

**IonWatcherBot is offered under the GNU General Public License.**  
**Please read it here: https://www.gnu.org/copyleft/gpl.html**


# FAQ #

**1 . Will the bot keep running if I close the terminal/command window after I successfully launched it?**  
A. Not per se, but this is doable. On Linux, for example, you could use `screen` to run the bot without having to keep an active terminal:  
`ssh` to the computer (with Linux) running the bot    
`cd` to the ionwatcherbot directory  
`screen python main.py`  
(input password)  
`CTRL-a d`  
(detached)  

To resume:  
`ssh` to the same computer  
`screen -r`