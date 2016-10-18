# -*- coding: utf-8 -*-
"""
Created on Sat Oct 15 17:08:42 2016

@author: Roberto
"""

# TODO add "clean" to clen files and logs
# TODO user administration

# pip install python-telegram-bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
# pip install beautifulsoup4
# In case "Couldn't find a tree builder": pip install lxml
import bs4
import logging
import configparser
import getpass
import requests
from collections import OrderedDict
import json
import re
import shutil
import os


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
            instance.last_bot = bot
            user = get_user(update)
            username = user.username
            if update.message:
                text = update.message.text
            elif update.callback_query:
                text = "[Button_{}]".format(update.callback_query.data)
            else:
                logging.warning("couldn't establish user. update is:" + str(update))
                return None
            negate_text = instance.config['MESSAGES']['negate']
            if username in instance.blocked:
                auth = [] # no access
                negate_text = 'You have been blocked and cannot issue any command.'
            elif self.userlevel == 'any':
                auth = True
            elif self.userlevel == 'user':
                auth = instance.users.union(instance.admins)
            else:
                auth = instance.admins
            if auth is True or username in auth:
                logging.info("Approved {0} command from: {1}".format( 
                        text, username))
                return action(*args)     
            else:
                logging.info("Blocked {0} command from: {1}".format( 
                        text, username))
                bot.sendMessage(chat_id=user.id, 
                        text=negate_text)
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
                    ('queue', 'Join queue'),
                    ('blocked', 'Blocked users')])),
            ('MESSAGES', OrderedDict([
                    ('start', 'Initial greeting, /start command is received by an unknown user'),
                    ('kill', '/kill command is received by an admin'),
                    ('negate', 'Command issued by unauthorized user')]))
            ])
    # Fields listed under `optionals` can be left blank in the config file;
    # 'users' specifically can be blank, because 'admins' cannot.
    optionals = ['server', 'users', 'queue', 'blocked']

    
    # Keyboard buttons, based on status
    keyboards = {'start': [[InlineKeyboardButton("Monitor runs", callback_data='M')],
                           [InlineKeyboardButton("View queue", callback_data='Q')],
                           [InlineKeyboardButton("Exit", callback_data='E')]],
                 'kill': [[InlineKeyboardButton("Kill the bot", callback_data='K')]],
                 'back': [[InlineKeyboardButton("Back", callback_data='B')]]
                                 
                                 }
    
    def __init__(self):
        self.admins = None
        self.users = None
        self.queue = None
        self.blocked = None
        self.runs = []
        
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
                self.blocked = toset(self.config['COMM']['blocked'])
                self.server = format_server_address(self.config['NETWORK']['server'])
                return True
    
    
    def clean_config_data(self, configloc, userset):
        self.config['COMM'][configloc] = \
                [re.sub('[\{\}\']', '', str(userset)), ''][userset == set()]
    
    def save_config(self):
        self.clean_config_data('admins', self.admins)
        self.clean_config_data('users', self.users)
        self.clean_config_data('queue', self.queue)
        self.clean_config_data('blocked', self.blocked)
       
        with open('IonWatcher.cfg', 'w') as f:
            f.write('# Configurations file for IonWatcher Bot\n\n')
            for category in self.cfg_text:
                f.write('[{}]\n\n'.format(category))
                for item in self.cfg_text[category]:
                    f.write('# ' + self.cfg_text[category][item] + '\n')
                    f.write('{0} = {1}\n'.format(item, str(self.config[category][item])))
                f.write('\n')
            

    # Bot comm methods, ordered by user level and then alphabetically
    # The first are eneral methods; no clearance
    def button(self, bot, update):
        query = update.callback_query
        self.this_query = query
        sender = {'M': self.monitor,
                  'Q': self.join,
                  'K': self.kill,
                  'E': self.bye,
                  'B': self.start}
                  
        if query.data in sender:
            sender[query.data](bot, update)
            
        elif query.data.startswith("Run_"):
            run_id = int(query.data[4:])
            this_run = [run for run in self.runs if run['id']==run_id][0]
            self.run_report(bot, update, this_run)
        
        elif query.data.startswith("App_"):
                app_username = query.data[4:]
                self.approve(bot, update, app_username)
        
        elif query.data.startswith("Blo_"):
                block_username = query.data[4:]
                self.block(bot, update, block_username)


    def bye(self, bot, update):
        user = get_user(update)
        bot.sendMessage(chat_id=user.id, 
                        text="Goodbye {}! Type /start to interact again.".format(
                            user.first_name))


    def keyboard(self, bot, update):
        '''
        Offer command options to the user.
        '''
        keyboard = []
        user = get_user(update)
        text = "How can I help you, {}?".format(user.first_name)
        status = self.chats.get(user.id, 'start')
        if status == 'start':
            if user.username in self.admins.union(self.users):
                keyboard.extend(self.keyboards['start'])
            elif user.username in self.queue.union(self.blocked):
                return
            else:
                keyboard.append([InlineKeyboardButton("Join queue",
                                                          callback_data='Q')])
        
        if status == 'monitor' and self.runs:
            text = "Select a run for more information:"
            keyboard.append([InlineKeyboardButton(str(run['id']),
                    callback_data='Run_'+str(run['id'])) for run in self.runs])
        
        if status == 'join':
            if user.username in self.admins:
                text = "Choose any action:"
                for queued in self.queue:
                    keyboard.append([InlineKeyboardButton("Approve "+queued, 
                                                          callback_data='App_'+queued),
                                     InlineKeyboardButton("Block", 
                                                          callback_data='Blo_'+queued)])
            elif user.username in self.users:
                text = "End of queue."
        
        if status != 'start':
            keyboard.extend(self.keyboards['back'])
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.sendMessage(chat_id=user.id, text=text, reply_markup=reply_markup)


    @Usercheck('any')
    def join(self, bot, update):
        '''
        Add the user to the join queue, or view queue if admin
        '''
        user = get_user(update)
        if user.username in self.queue:
            bot.sendMessage(chat_id=user.id, 
                    text="Hello, {}. You are already in the queue.".format(user.username))
            self.chats[user.id] = 'start'
        elif user.username not in self.admins.union(self.users):
            self.queue.add(user.username)
            self.save_config()
            bot.sendMessage(chat_id=user.id, 
                    text="You have been added to the queue, {}.".format(user.username))
            
        else:
            if not self.queue:
                bot.sendMessage(chat_id=user.id, text="There are no users in the queue.")
                self.chats[user.id] = 'start'
            else:
                bot.sendMessage(chat_id=user.id, 
                        text="The following users are in the queue:\n" + \
                        ''.join(['@{}\n'.format(name) for name in self.queue]))
                self.chats[user.id] = 'join'
        self.keyboard(bot, update)


    @Usercheck('any')
    def start(self, bot, update):
        '''
        The basic command to start a chat.
        
        '''
        user = get_user(update)
        # If the message is from a truster user or admin, no special handling
        if user.username in self.admins.union(self.users):
            pass
        
        # If the user is still in the queue, inform him/her
        elif user.username in self.queue:
                bot.sendMessage(chat_id=user.id, 
                                text="Hello, {}. I'm afraid you haven't been "
                                "cleared from the queue yet. Please speak to "
                                "an administrator to get clearance.".format(
                                user.username))
        
        # If it's a new user, greet him/her
        else:
            bot.sendMessage(chat_id=user.id, 
                            text=self.config['MESSAGES']['start'])
        self.chats[user.id] = 'start'
        self.keyboard(bot, update)
    

    @Usercheck('user')
    def monitor(self, bot, update):
        '''
        Return data about the current runs in progress.
        
        '''
        user = get_user(update)
        self.runs, flag = self.read_monitor()
        self.runs = sorted(self.runs, key = lambda x: int(x['id']))
        if flag == 'no_data':
            bot.sendMessage(chat_id=user.id,
                            text="I'm sorry {}, I couldn't retrieve any data.".format(
                            user.first_name))
            return
        elif flag == 'multiple':
            bot.sendMessage(chat_id=user.id, 
                            text="{}, I found multiple data, which was unexpected."
                            "However, I hope this is the list of runs.".format(
                            user.first_name))
        else:
            bot.sendMessage(chat_id=user.id, 
                            text="I have found {0} runs:".format(
                            len(self.runs)))
        for run in self.runs:
            # TODO see flows
            runname = re.sub('Auto_[\w]*?_', '', run['resultsName'])
            run_dir_id = run['id']
            run_status = run['status']
            string = ('[{}]\n{}\n'        
                      'Status: {}'.format(run_dir_id, runname,         
                                          run_status))
            bot.sendMessage(chat_id=user.id, text=string)
        self.chats[user.id] = 'monitor'
        self.keyboard(bot, update)
                

    @Usercheck('user')
    def run_report(self, bot, update, run):
        user = get_user(update)
        # TODO see flows
        runname = re.sub('Auto_[\w]*?_', '', run['resultsName'])
        run_dir_id = run['id']
        add_wells = int(run['analysismetrics']['total_wells']) - \
                            int(run['analysismetrics']['excluded'])
        bead = int(run['analysismetrics']['bead'])
        live = int(run['analysismetrics']['live'])
        lib = int(run['analysismetrics']['lib'])
        libFinal = int(run['analysismetrics']['libFinal'])
        key_signal = run['libmetrics']['aveKeyCounts']
        mean_length = run['libmetrics']['q20_mean_alignment_length']
        run_status = run['status']
        loading_ok = (100 * bead/add_wells) >= int(run['experiment']['qcThresholds']['Bead Loading (%)'])
        usable_ok = (100 * libFinal/lib) >= int(run['experiment']['qcThresholds']['Usable Sequence (%)'])
        key_sig_ok = key_signal >=  int(run['experiment']['qcThresholds']['Key Signal (1-100)'])
        string = ('[{}]\n{}\n'
                  '{} Loading: {:.1%} {}\n'
                  '{} Live: {:.1%}\n'
                  '{} Library: {:.1%}\n'
                  '{} Usable: {:.1%} {}\n'
                  '{} Key signal: {} {}\n'
                  'Mean length: {}\n'
                  'Status: {}'.format(run_dir_id, runname, 
                                      *pcsquares(bead/add_wells), mark(loading_ok), # Loading
                                      *pcsquares(live/bead), # Live
                                      *pcsquares(lib/live), # Library
                                      *pcsquares(libFinal/lib), mark(usable_ok), # Usable
                                      pcsquares(key_signal/100)[0], key_signal, mark(key_sig_ok),
                                      mean_length,
                                      run_status))        
        bot.sendMessage(chat_id=user.id, text=string)
        bot.sendPhoto(chat_id=user.id, photo=open(self.get_image(run_dir_id), 'rb'))
        self.keyboard(bot, update)


    @Usercheck('admin')
    def approve(self, bot, update, username):
        user = get_user(update)
        self.users.add(username)
        self.queue.remove(username)
        self.save_config()
        bot.sendMessage(chat_id=user.id, 
                text="User {} has been approved.".format(username))
        self.keyboard(bot, update)
    

    @Usercheck('admin')
    def block(self, bot, update, username):
        user = get_user(update)
        self.blocked.add(username)
        self.queue.remove(username)
        self.save_config()
        bot.sendMessage(chat_id=user.id, 
                text="User {} has been blocked.".format(username))
        self.keyboard(bot, update)


    @Usercheck('admin')
    def kill(self, bot, update):
        '''
        Stop the updater.
        '''
        user = get_user(update)
        bot.sendMessage(chat_id=user.id, 
                        text=self.config['MESSAGES']['kill'])
        #self.updater.stop() # is just not working to stop the script
        os._exit(0)
    
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
        with open('testing_data/monitor/index.html', 'r') as f:
            recorded_text = f.read()
            soup = bs4.BeautifulSoup(recorded_text, 'lxml')
        elems=soup.select('script')
        data = [elem for elem in elems if 'var initial_runs' in elem.text]
        if not data:
            logging.warning("Couldn't fetch data for runs in progress. Dumping soup:")
            logging.warning(soup.text)
            flag = 'no_data'
            return [None, flag]
        elif len(data) > 1:
            logging.warning("Multiple entries for runs in progress. Dumping data:")
            logging.warning(str(data))
            flag = 'multiple'
        else:
            flag = 'ok'
        good = data[0].text[data[0].text.index('{'):data[0].text.rfind('}')+1]
        monitor_json = json.loads(good)
        runs = monitor_json['objects']
        return [runs, flag]


    def get_image(self, run_id):
        filename = 'Bead_density_200.png'
        loc = 'report/{}/metal/{}'.format(run_id, filename)
        dest = 'images/{}_{}'.format(run_id, filename)
        try:
            response = requests.get(self.server+loc, auth=self.auth,
                                    verify=False, stream=True)
            with open(dest, 'wb') as out_file:
                shutil.copyfileobj(response.raw, out_file)
            return dest
        except:
            return None
        


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


def get_user(update):
    if update.message:
        return update.message.from_user
    elif update.callback_query:
        return update.callback_query.from_user
    else:
        return None

def pcsquares(value):
    valuepc = value  * 100
    blue = int(min((valuepc // 20)+1, 5))
    white = 5 - blue
    return  [u'\U0001F535' * blue + u'\U000026AA' * white, value]
    
def mark(boolean):
    return [u'\U0000274C', u'\U00002705'][boolean]


if __name__ == '__main__':
    loop = Mainloop()
    
    
    