# -*- coding: utf-8 -*-
"""
Created on Sat Oct 15 17:08:42 2016

@author: Roberto
"""

# TODO add "clean" to clean files and logs
# TODO user administration

import os, logging, re, json, requests
from collections import OrderedDict
from configparser import ConfigParser
from getpass import getpass
from shutil import copyfileobj
from threading import Timer
import time

## To install bs4:
# pip install beautifulsoup4
## In case "Couldn't find a tree builder":
# pip install lxml
##  or possibly:
# sudo apt install python-lxml
from bs4 import BeautifulSoup

## To install the telegram module:
# pip install python-telegram-bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler

api = 'rundb/api/v1/'

# Decorators
class Userlevel(object):
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
            chat = instance.chats[user.id]
            if update.message:
                text = update.message.text
            elif update.callback_query:
                text = "[Button_{}]".format(update.callback_query.data)
            else:
                logging.warning("couldn't establish user. Update is:" + str(update))
                return None
            negate_text = instance.config['MESSAGES']['negate']
            if username in instance.blocked:
                auth = [] # no access
                negate_text = 'You have been blocked and cannot issue any command.'
            elif self.userlevel == 'any':
                auth = True
            elif self.userlevel == 'user':
                auth = instance.users
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
    
    # The cfg_text variable holds the basic structure of the config file.
    # At instantiation, the config file is checked for the fields listed here.
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
                    ('tick', '/tick command is received by an admin'),
                    ('untick', '/untick command is received by an admin'),
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
                 'tick': [[InlineKeyboardButton("Start ticking", callback_data='T')]],
                 'untick': [[InlineKeyboardButton("Stop ticking", callback_data='U')]],
                 'back': [[InlineKeyboardButton("Back", callback_data='B')]]
                                 
                                 }
    
    images = [['Bead_density_200.png', 'bead density'],
              ['basecaller_results/wells_beadogram.png', 'bead quality data'],
              ['basecaller_results/readLenHisto2.png', 'read size distribution'],
              ['iontrace_Library.png', 'key signal data']]
    
    def __init__(self):
        self.admins = None
        self.users = None
        self.queue = None
        self.blocked = None
        self.rt = dict() # {id: RepeatTimer()}
        self.runs = dict()
        
        # chats are stored as: {id: {'status': <status>, 'lastpin': <time>}, 
        # where 'status' can be: 'start', 'join', 'monitor', 'back', 'bye'
        # and 'lastpin' is the last time the user entered their pin.
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
        dispatcher.add_handler(CommandHandler('tick', self.tick))
        dispatcher.add_handler(CommandHandler('untick', self.untick))
        dispatcher.add_handler(CommandHandler('monitor', self.monitor))
        dispatcher.add_handler(CommandHandler('join', self.join))
        dispatcher.add_handler(CommandHandler('bye', self.bye))
        dispatcher.add_handler(CallbackQueryHandler(self.button))
        
        print('Listening...')
        self.updater.start_polling()


    # Config loading and saving
    def get_config(self):
        print('Reading configurations file...')
        config = ConfigParser()
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
                self.admins = todict(self.config['COMM']['admins'])
                self.users = todict(self.config['COMM']['users'])
                self.users.update(self.admins)
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
            

    # Bot methods, ordered by user level and then alphabetically
    # The first are general methods; no clearance
    def button(self, bot, update):
        query = update.callback_query
        self.this_query = query
        sender = {'M': self.monitor,
                  'Q': self.join,
                  'K': self.kill,
                  'T': self.tick,
                  'U': self.untick,
                  'E': self.bye,
                  'B': self.start}
                  
        if query.data in sender:
            sender[query.data](bot, update)
            
        elif query.data.startswith("Run_"):
            run_id = int(query.data[4:])
            this_run = self.runs.get(run_id, None)
            try:
                self.run_report(bot, update, this_run)
            except error.TimedOut:
                user = get_user(update)
                bot.sendMessage(chat_id=user.id, text="Sorry, I lost connection to Telegram while fulfilling your request.")
                logging.warning("Lost connection to Telegram.")
                self.chats[user.id]['status'] = 'back'
                self.keyboard(bot, update)
                
        
        elif query.data.startswith("App_"):
                app_username = query.data[4:]
                self.approve(bot, update, app_username)
        
        elif query.data.startswith("Blo_"):
                block_username = query.data[4:]
                self.block(bot, update, block_username)
        

    def keyboard(self, bot, update):
        '''
        Offer command options to the user.
        '''
        keyboard = []
        user = get_user(update)
        text = "How can I help you, {}?".format(user.first_name)
        status = self.chats[user.id]['status']
        if status == 'start':
            if user.username in self.users:
                keyboard.extend(self.keyboards['start'])
            elif user.username in self.blocked or user.username in self.queue:
                return
            else:
                keyboard.append([InlineKeyboardButton("Join queue",
                                                          callback_data='Q')])
        
        if status == 'monitor' and self.runs:
            text = "Select a run for more information:"
            keyboard.append([InlineKeyboardButton(str(run),
                    callback_data='Run_'+str(run)) for run in self.runs])
        
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
        
        if status == 'back' or status != 'start':
            keyboard.extend(self.keyboards['back'])
        
           
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.sendMessage(chat_id=user.id, text=text, reply_markup=reply_markup)


    def report_link(self, bot, update, run):
        user = get_user(update)
        run_dir_id = run['id']
        report_pdf = self.get_pdf(run_dir_id)
        if report_pdf:
            self.pdf(bot, update, run_dir_id)
        else:
            bot.sendMessage(chat_id=user.id, text="The pdf report is not ready yet.")
        self.chats[user.id]['status'] = 'monitor'
        self.keyboard(bot, update)
            


    # Scraping
    def read_monitor(self):
        '''
        Scrape data about current runs from the server and return it.
        
        '''
        
        flag = ''
        
        api_page = self.server+api+'monitorresult/'
        
        logging.info("Contacting: "+api_page)
        try:
            response = requests.get(api_page,
                                         auth=self.auth, 
                                         verify=False)
            monitor_json = json.loads(response.text)
            
        except Exception as exc:
            logging.warning("Server unreachable or bad auth: " + exc)
            flag = 'no_connection'
            return [None, flag]
        flag = 'ok'
        # meta = monitor_json['meta']
        runs = {obj['id']: obj for obj in monitor_json['objects'] if obj}
        return [runs, flag]


    # file retrieving
    def get_image(self, run_id, filename):
        loc = 'report/{}/metal/{}'.format(run_id, filename)
        # Removing dirs from filename
        destname = filename[filename.rfind('/')+1:]
        dest = 'download/{}_{}'.format(run_id, destname)
        return self.get_file(loc, dest)
        
        
    def get_pdf(self, run_id):
        loc = 'report/latex/{}.pdf'.format(run_id)
        dest = 'download/{}.pdf'.format(run_id)
        return self.get_file(loc, dest)


    def pdf(self, bot, update, report_id):
        user = get_user(update)
        with open('download/{}.pdf'.format(report_id), 'rb') as document:
            bot.sendDocument(chat_id=user.id, document=document)        
        
    def get_file(self, loc, dest):
        try:
            response = requests.get(self.server+loc, auth=self.auth,
                                    verify=False, stream=True)
            with open(dest, 'wb') as out_file:
                copyfileobj(response.raw, out_file)
            return dest
        except:
            return None

    # User actions
    # For practicality, both `join` and `start` are entry points for new chats.
    @Userlevel('any')
    def join(self, bot, update):
        '''
        Add the user to the join queue, or view queue if admin
        '''
        user = get_user(update)
        if user.username in self.queue:
            bot.sendMessage(chat_id=user.id, 
                    text="Hello, {}. You are already in the queue.".format(user.username))
            self.chats[user.id]['status'] = 'start'
        elif user.username not in self.users:
            self.chats[user.id] = {'status': 'join', 'lastpin': 0}
            self.queue.add(user.username)
            self.save_config()
            bot.sendMessage(chat_id=user.id, 
                    text="You have been added to the queue, {}.".format(user.username))
            
        else:
            if not self.queue:
                bot.sendMessage(chat_id=user.id, text="There are no users in the queue.")
                self.chats[user.id]['status'] = 'start'
            else:
                bot.sendMessage(chat_id=user.id, 
                        text="The following users are in the queue:\n" + \
                        ''.join(['@{}\n'.format(name) for name in self.queue]))
                self.chats[user.id]['status'] = 'join'
        self.keyboard(bot, update)


    @Userlevel('any')
    def start(self, bot, update):
        '''
        The basic command to start a chat.
        
        '''
        user = get_user(update)
        # If the message is from a truster user or admin, no special handling
        if user.username in self.users:
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
            self.chats[user.id] = {'status': 'start', 'lastpin': 0}
            bot.sendMessage(chat_id=user.id, 
                            text=self.config['MESSAGES']['start'])
        self.chats[user.id]['status'] = 'start'
        self.keyboard(bot, update)
    

    @Userlevel('user')
    def bye(self, bot, update):
        user = get_user(update)
        self.chats[user.id]['status'] = 'bye'
        bot.sendMessage(chat_id=user.id, 
                        text="Goodbye, {}. Type /start to restart.".format(user.first_name))


    @Userlevel('user')
    def monitor(self, bot, update):
        '''
        Return data about the current runs in progress.
        
        '''
        user = get_user(update)
        runs, flag = self.read_monitor()
        
        if flag == 'no_connection':
            bot.sendMessage(chat_id=user.id,
                            text="I'm sorry {}, I couldn't connect to the server.".format(
                            user.first_name))
        
        elif flag == 'no_data':
            bot.sendMessage(chat_id=user.id,
                            text="I'm sorry {}, I couldn't retrieve any data.".format(
                            user.first_name))
            self.chats[user.id]['status'] = 'start'
            self.keyboard(bot, update)
            return
        elif flag == 'multiple':
            bot.sendMessage(chat_id=user.id, 
                            text="{}, I found multiple data, which was unexpected."
                            "However, I hope this is the list of runs.".format(
                            user.first_name))
        elif flag == 'ok':
            bot.sendMessage(chat_id=user.id, 
                            text="I have found {0} runs:".format(
                            len(runs)))
            if (not runs) and self.runs:
                bot.sendMessage(chat_id=user.id, 
                        text="However, I have {0} runs in menory:".format(
                        len(self.runs)))
        else:
            bot.sendMessage(chat_id=user.id, 
                            text="I'm sorry, something went unexpectedly wrong.")

        if runs:
            self.runs.update(runs)
        if self.runs:
            for run_dir_id, run in sorted(self.runs.items()):
                # TODO see flows
                runname = re.sub('Auto_[\w]*?_', '', run['resultsName'])
                run_status = run['status']
                string = ('[{}]\n{}\n'        
                          'Status: {}'.format(run_dir_id, runname,         
                                              run_status))
                bot.sendMessage(chat_id=user.id, text=string)
            self.chats[user.id]['status'] = 'monitor'

        self.keyboard(bot, update)


    @Userlevel('user')
    def run_report(self, bot, update, run):
        user = get_user(update)
        # TODO see flows
        runname = re.sub('Auto_[\w]*?_', '', run['resultsName'])
        run_dir_id = run['id']
        
        if run['analysismetrics'] is None:
            bot.sendMessage(chat_id=user.id, text='No analysis metrics yet.')
        else:
            add_wells = int(run['analysismetrics']['total_wells']) - \
                                int(run['analysismetrics']['excluded'])
            bead = int(run['analysismetrics']['bead'])
            live = int(run['analysismetrics']['live'])
            lib = int(run['analysismetrics']['lib'])
            libFinal = int(run['analysismetrics']['libFinal'])
        if run['libmetrics'] is None:
            bot.sendMessage(chat_id=user.id, text='No library metrics yet.')
        else:
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
                      'Status: {} {}'.format(run_dir_id, runname, 
                                          *pcsquares(bead/add_wells), mark(loading_ok), # Loading
                                          *pcsquares(live/bead), # Live
                                          *pcsquares(lib/live), # Library
                                          *pcsquares(libFinal/lib), mark(usable_ok), # Usable
                                          pcsquares(key_signal/100)[0], key_signal, mark(key_sig_ok),
                                          mean_length,
                                          run_status,
                                          ['(at last monitoring)', ''][run_status=='Completed']))        
            bot.sendMessage(chat_id=user.id, text=string)

            for image_data in self.images:
                image = self.get_image(run_dir_id, image_data[0])
                if image:
                    bot.sendPhoto(chat_id=user.id, photo=open(image, 'rb'))
                else:
                    bot.sendMessage(chat_id=user.id,
                                    text="[no {} image]".format(image_data[1]))
        self.report_link(bot, update, run)



    @Userlevel('admin')
    def approve(self, bot, update, username):
        user = get_user(update)
        self.users.add(username)
        self.queue.remove(username)
        self.save_config()
        bot.sendMessage(chat_id=user.id, 
                text="User {} has been approved.".format(username))
        self.keyboard(bot, update)
    

    @Userlevel('admin')
    def block(self, bot, update, username):
        user = get_user(update)
        self.blocked.add(username)
        self.queue.remove(username)
        self.save_config()
        bot.sendMessage(chat_id=user.id, 
                text="User {} has been blocked.".format(username))
        self.keyboard(bot, update)


    @Userlevel('admin')
    def kill(self, bot, update):
        '''
        Stop the updater.
        '''
        user = get_user(update)
        bot.sendMessage(chat_id=user.id, 
                        text=self.config['MESSAGES']['kill'])
        #self.updater.stop() # is just not working to stop the script
        os._exit(0)
    
    @Userlevel('admin')
    def tick(self, bot, update):
        '''
        Start ticking system uptime every half an hour.
        '''
        user = get_user(update)
        self.rt[user] = RepeatedTimer(30*60, self.send_tick, user, bot)
        bot.sendMessage(chat_id=user.id, 
                        text=self.config['MESSAGES']['tick'])        
        self.send_tick(user, bot, complete=True)
        
    @Userlevel('admin')
    def untick(self, bot, update):
        '''
        Start ticking system uptime every half an hour.
        '''
        user = get_user(update)
        if self.rt.get(user, False):
            self.rt[user].stop()
            bot.sendMessage(chat_id=user.id, 
                            text=self.config['MESSAGES']['untick'])
    
    def send_tick(self, user, bot, complete = False):
        global text
        response = requests.get(self.server+'configure/services/',
                                auth=self.auth, 
                                verify=False)
        soup = BeautifulSoup(response.text, 'lxml')
        table = soup.find_all('table') # new method name in BS4 is find_all
        if table:
            vm_info = table[0]
            headtext = get_tag_text(vm_info.thead, 'th')
            bodytext = get_tag_text(vm_info.tbody, 'td')
            if len(headtext) == len(bodytext):
                retlist = []
                for head, body in zip(headtext, bodytext):
                    retlist.append('{}: {}'.format(head, body))
                if complete:
                    retstring = 'Server status:\n'+('\n'.join(retlist))
                else:
                    retstring = retlist[-1]
                bot.sendMessage(chat_id=user.id, 
                                text=retstring)
                return
        bot.sendMessage(chat_id=user.id,
                        text="Warning: Could not retrieve VM info.")
        return
        
        
        
        bot.sendMessage(chat_id=user.id, 
                text=text[:50])

# Helper functions
def notblank(info, secret = False):
    text = ''
    hidden = [input, getpass]
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
    return a set of strings from a concatenated string (comma-separated).
    
    '''
    return set([item.strip() for item in string.split(',') if item.strip() != ''])


def todict(string):
    '''
    return a dictionary from a concatenated string (comma-separated key:value pairs).
    
    '''
    out = dict()
    for item in string.split(','):
        if item.strip() != '':
            if ":" in item:
                key, value = item.split(":")
                out[key.strip()] = value.strip()
            else:
                out[item.strip()] = None
    return out

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


def get_tag_text(bs4tag, tagstring):
    taglist = bs4tag.find_all(tagstring)
    taglist = [collapse(item.text) for item in taglist]
    return taglist

def collapse(text):
    '''
    Solution derived from StackOVerflow user Alex Martelli (.../95810/alex-martelli):
    https://stackoverflow.com/questions/1274906/collapsing-whitespace-in-a-string
    
    '''
    rex = re.compile(r'\W+')
    return rex.sub(' ', text).strip()

class RepeatedTimer(object):
    '''
    From StackOverflow user MestreLion (.../users/624066/mestrelion):
    https://stackoverflow.com/questions/474528/what-is-the-best-way-to-repeatedly-execute-a-function-every-x-seconds-in-python
    
    '''
    def __init__(self, interval, function, *args, **kwargs):
        self._timer     = None
        self.interval   = interval
        self.function   = function
        self.args       = args
        self.kwargs     = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False



if __name__ == '__main__':
    loop = Mainloop()

