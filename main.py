# -*- coding: utf-8 -*-
"""
Created on Sat Oct 15 17:08:42 2016

@author: Roberto
"""

from telegram.ext import Updater, CommandHandler, MessageHandler
import logging
import configparser
import getpass
import requests
from collections import OrderedDict
import bs4
import json


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
            user = update.message.from_user.username
            if self.userlevel == 'any':
                auth = True
            elif self.userlevel == 'user':
                auth = instance.users
            else:
                auth = instance.admins
            if auth is True or user in auth:
                logging.info("Approved {0} command from: {1}".format( 
                        update.message.text, update.message.from_user.username))
                return action(*args)     
            else:
                logging.info("Blocked {0} command from: {1}".format( 
                        update.message.text, update.message.from_user.username))
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
                    ('users', 'Trusted users')])),
            ('MESSAGES', OrderedDict([
                    ('start', 'Initial greeting, /start command is received by an unknown user'),
                    ('kill', '/kill command is received by an admin'),
                    ('negate', 'Command issued by unauthorized user')]))
            ])
    # Fields listed under `optionals` can be left blank in the config file;
    # 'users' specifically can be blank, because 'admins' cannot.
    optionals = ['server', 'users']

    
    def __init__(self):
        self.config = self.get_config()
        if not self.config:
            print('Invalid configurations file. Aborting.')
            return None
        self.admins = tolist(self.config['COMM']['admins'])
        self.users = self.admins + tolist(self.config['COMM']['users'])
        self.server = format_server_address(self.config['NETWORK']['server'])
        # Input user (if not in config) and password (always)
        user = self.config['NETWORK'].get('user', notblank('Username at ' + self.server))
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
        start_handler = CommandHandler('start', self.start)
        dispatcher.add_handler(start_handler)
        kill_handler = CommandHandler('kill', self.kill)
        dispatcher.add_handler(kill_handler)
        monitor_handler = CommandHandler('monitor', self.monitor)
        dispatcher.add_handler(monitor_handler)
        
        
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
                return None
            else:
                return config
        
    def save_config(self):
        with open('IonWatcher.cfg', 'w') as f:
            f.write('# Configurations file for IonWatcher Bot\n\n')
            for category in self.cfg_text:
                f.write('[{}]\n\n'.format(category))
                for item in self.cfg_text[category]:
                    f.write('# ' + self.cfg_text[category][item] + '\n')
                    f.write('{0} = {1}\n'.format(item, self.config[category][item]))
                f.write('\n')
            


    # Bot commands

    @Usercheck('any')
    def start(self, bot, update):
        '''
        The basic command to start a chat.
        
        '''
        self.message = update.message
        bot.sendMessage(chat_id=update.message.chat_id, 
                        text=self.config['MESSAGES']['start'])
        # self.keyboard(bot, update)
    

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
        pass
    
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


def tolist(string):
    '''
    return a list of usernames from a comma-separated string.
    '''
    return [item.strip() for item in string.split(',')]

if __name__ == '__main__':
    loop = Mainloop()
    
    
    