# -*- coding: utf-8 -*-
"""
Created on Sat Oct 15 17:08:42 2016

@author: Roberto
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler
import logging
import configparser
import getpass
import requests
from collections import OrderedDict
import bs4
import json
import re


# Decorators
class Usercheck(object):
    '''
    This class holds a decorator that will be used to check for user privileges
    after a command is received.
    
    '''
    
    def __init__(self, userlevel):
        '''
        `userlevel` can be: 'any', 'user', 'admin'.
        '''
        self.userlevel = userlevel
    
    def __call__(self, action):
        def wrapper(*args):
            instance, bot, update = args[:3]
            instance.last_update = update
            if update.message:
                user = update.message.from_user.username
                text = update.message.text
            elif update.callback_query:
                user = update.callback_query.from_user.username
                text = "[Button_{}]".format(update.callback_query.data)
            else:
                logging.warning("couldn't establish user. update is:" + str(update))
                return None
            instance.last_message = update.message
            if self.userlevel == 'any':
                auth = True
            elif self.userlevel == 'user':
                auth = instance.users.union(instance.admins)
            else:
                auth = instance.admins
            if auth is True or user in auth:
                logging.info("Approved {0} command from: {1}".format( 
                        text, user))
                return action(*args)     
            else:
                logging.info("Blocked {0} command from: {1}".format( 
                        text, user))
                bot.sendMessage(chat_id=update.message.chat_id, 
                        text=instance.config['MESSAGES']['negate'])
                return None
        return wrapper

class Mainloop(object):
    
    # The cfg_text variable must hold  the basic structure of the config file.
    # At instantiation, the config file is checked for the field listed here.
    # When saving a config file, only the fields listed here will be saved.
    cfg_text = OrderedDict([
            ('NETWORK', OrderedDict([
                    ('token', 'Register your own copy of this bot with @BotFather, '
                              'and save your own token below.'),
                    ('server', 'Server address'),
                    ('user', 'Username for remote login to server')])),
            ('COMM', OrderedDict([
                    ('admins', 'Administrators'),
                    ('users', 'Trusted users'),
                    ('queue', 'Join queue')])),
            ('MESSAGES', OrderedDict([
                    ('start', 'Initial greeting, /start command is received by an unknown user'),
                    ('kill', '/kill command is received by an admin'),
                    ('negate', 'Command issued by unauthorized user')]))
            ])
    # Fields listed under `optionals` can be left blank in the config file;
    # 'users' specifically can be blank, because 'admins' cannot.
    optionals = ['server', 'users', 'queue']

    
    # Keyboard buttons, based on status
    keyboards = {'start': [[InlineKeyboardButton("Monitor runs", callback_data='M')],
                           [InlineKeyboardButton("View queue", callback_data='Q')]],
                 'kill': [[InlineKeyboardButton("Kill the bot", callback_data='K')]],
                 'exit': [[InlineKeyboardButton("Exit", callback_data='E')]]
                                 
                                 }
    
    def __init__(self):
        self.admins = None
        self.users = None
        self.queue = None
        
        # chats are stored in the form: {id: 'status'}, where 'status' can be:
        # 'start', 'adm_join', 'monitor'
        self.chats = {}
        config_set = self.get_config()
        if not config_set:
            print('Invalid configurations file. Aborting.')
            return None
        # Input user (if not in config) and password (always)
        user = self.config['NETWORK'].get('user', None)
        if not user:
            user = notblank('Username at {}'.format(self.server))
        self.auth = requests.auth.HTTPBasicAuth(user,
                                                notblank('password', secret=True))
    
        # Create updater and dispatcher
        self.updater = Updater(token=self.config['NETWORK']['token'])
        dispatcher = self.updater.dispatcher

        # Start log
        logging.basicConfig(filename='IonWatcher.log',
                            format='%(asctime)s - %(name)s - %(levelname)s - '
                                   '%(message)s',
                            level=logging.INFO)

        # register handlers
        dispatcher.add_handler(CommandHandler('start', self.start))
        dispatcher.add_handler(CommandHandler('kill', self.kill))
        dispatcher.add_handler(CommandHandler('monitor', self.monitor))
        dispatcher.add_handler(CommandHandler('join', self.join))
        dispatcher.add_handler(CommandHandler('bye', self.bye))
        dispatcher.add_handler(CommandHandler('keyboard', self.keyboard))
        dispatcher.add_handler(CallbackQueryHandler(self.button))
        
        
        print('Listening...')
        self.updater.start_polling()


    # Config loading and saving
    def get_config(self):
        print('Reading configurations file...')
        config = configparser.ConfigParser()
        config.read('IonWatcher.cfg')
        
        # Checking data
        aborting = False
        for category, items in self.cfg_text.items():
            for item in items:
                if item not in config[category] or config[category][item] == '':
                    if item not in self.optionals:
                        aborting = True
                        print('ERROR: Configurations file missing data: '
                              '[{0}] {1}'.format(category, item))
                    else:
                        config[category][item] = ''
            for item in config[category].keys():
                if item not in self.cfg_text[category].keys():
                    print('Warning: data [{0}] "{1}" not understood.'.format(
                          category, item))
            if aborting:
                return False
            else:
                self.config = config
                # Admins, users and queue must be transformed to list; pair with save_config
                self.admins = toset(self.config['COMM']['admins'])
                self.users = toset(self.config['COMM']['users'])
                self.queue = toset(self.config['COMM']['queue'])
                self.server = format_server_address(self.config['NETWORK']['server'])
                return True
        
    def save_config(self):
        self.config['COMM']['admins'] = re.sub('[\{\}\']', '', str(self.admins))
        if self.users:
            self.config['COMM']['users'] = re.sub('[\{\}\']', '', str(self.users))
        if self.queue:
            self.config['COMM']['queue'] = re.sub('[\{\}\']', '', str(self.queue))
       
        with open('IonWatcher.cfg', 'w') as f:
            f.write('# Configurations file for IonWatcher Bot\n\n')
            for category in self.cfg_text:
                f.write('[{}]\n\n'.format(category))
                for item in self.cfg_text[category]:
                    f.write('# ' + self.cfg_text[category][item] + '\n')
                    f.write('{0} = {1}\n'.format(item, str(self.config[category][item])))
                f.write('\n')
            


    # Bot commands

    @Usercheck('any')
    def start(self, bot, update):
        '''
        The basic command to start a chat.
        
        '''
        message = update.message
        # If the message is from a truster user or admin, start keyboard
        if message.from_user.username in self.admins.union(self.users):
            self.chats[message.chat_id] = 'start'
            self.keyboard(bot, update)
        
        # If the user is still in the queue, inform him/her
        elif message.from_user.username in self.queue:
                bot.sendMessage(chat_id=message.chat_id, 
                                text="Hello, {}. I'm afraid you haven't been "
                                "cleared from the queue yet. Please speak to "
                                "an administrator to get clearance.".format(
                                message.from_user.username))
        
        # If it's a new user, greet him/her
        else:
            bot.sendMessage(chat_id=message.chat_id, 
                            text=self.config['MESSAGES']['start'])
    

    @Usercheck('any')
    def join(self, bot, update):
        '''
        Add the user to the join queue
        '''
        if update.message.from_user.username in self.queue:
            bot.sendMessage(chat_id=update.message.chat_id, 
                            text="Hello, {}. You are already in the queue.".format(
                                update.message.from_user.username))
        else:
            bot.sendMessage(chat_id=update.message.chat_id, 
                            text="The following users are in the queue:{}".format(
                                '\n@'.join(self.queue)))
        if update.message.from_user.username in self.admins:
            self.chats[update.message.chat_id] = 'adm_join'
            self.keyboard(bot, update)


    @Usercheck('any')
    def bye(self, bot, update):
        bot.sendMessage(chat_id=update.message.chat_id, 
                        text="Goodbye {}!".format(
                            update.message.from_user.first_name))

    @Usercheck('admin')
    def kill(self, bot, update):
        '''
        Stop the updater.
        '''
        
        bot.sendMessage(chat_id=update.message.chat_id, 
                        text=self.config['MESSAGES']['kill'])
        self.updater.stop() # is just not working to stop the script
    
    
    @Usercheck('user')
    def monitor(self, bot, update):
        '''
        Return data about the current runs in progress.
        
        '''
        bot.sendMessage(chat_id=update.message.chat_id, 
                        text="Let's pretend I'm reading the 'runs in progress' page...")
        

    @Usercheck('any')
    def keyboard(self, bot, update):
        '''
        Offer command options to the user.
        '''
        
        status = self.chats.get(update.message.chat_id, 'start')
        if status == 'start':
            keyboard = self.keyboards['start']
        
        keyboard.extend(self.keyboards['exit'])
        if update.message.from_user.username in self.admins:
            keyboard.extend(self.keyboards['kill'])
        
        reply_markup = InlineKeyboardMarkup(keyboard)

        update.message.reply_text("Hello, {}. How can I help you?".format(
                update.message.from_user.first_name), reply_markup=reply_markup)
            

    def button(self, bot, update):
        query = update.callback_query
        self.this_query = query
        sender = {'M': self.monitor,
                  'Q': self.join,
                  'K': self.kill,
                  'E': self.bye}
                  
        sender[query.data](bot, update)
            
    
        bot.editMessageText(text="Selected option: %s" % query.data,
                            chat_id=query.message.chat_id,
                            message_id=query.message.message_id)


      
    
    # Scraping
    def read_monitor(self):
        '''
        Scrape data about current runs from the server and return it.
        
        '''
        
        flag = ''
        monitor_table = requests.get(self.server+'monitor/#full',
                                     auth=self.auth, 
                                     verify=False)
        soup = bs4.BeautifulSoup(monitor_table.text, 'lxml')
        elems=soup.select('script')
        data = [elem for elem in elems if 'var initial_runs' in elem.text]
        if not data:
            flag = 'no_data'
            return [None, flag]
        elif len(data) > 1:
            flag = 'multiple'
        else:
            flag = 'ok'
        good = data[0].text[data[0].text.index('{'):data[0].text.rfind('}')+1]
        monitor_json = json.loads(good)
        runs = monitor_json['objects']
        '''
        ['resultsName', 'reportLink', 'resource_uri', 'library', 
        'qualitymetrics', 'barcodeId', 'representative', 'libmetrics', 'eas', 
        'timeStamp', 'experiment', 'status', 'analysismetrics', 
        'processedflows', 'autoExempt', 'projects', 'reportStatus', 'id']
        '''
        


# Helper functions
def notblank(info, secret = False):
    text = ''
    hidden = [input, getpass.getpass]
    while not text:
        text = hidden[secret](info.capitalize()+': ')
    return text


def format_server_address(server):
    # Server address: add 'http://' if missing, add last '/' if missing etc
    if not server.startswith('http://') and not server.startswith('https://'):
        if not ':' in server:
            if not '//' in server:
                # Most likely just lacking 'https://' altogether
                server = 'http://' + server
            else:
                print(('Please check server address. '
                       'You entered: "{}"').format(server))
        else:
            # Since we have the ':', we can try rebuilding it
            server = server.split(':')[1].strip('/')
    if not server.endswith('/'):
        server = server + '/'
    print("Will contact: {}".format(server))
    return server


def toset(string):
    '''
    return a set of usernames from a comma-separated string.
    '''
    return set([item.strip() for item in string.split(',') if item.strip() != ''])

if __name__ == '__main__':
    loop = Mainloop()
    
    
    