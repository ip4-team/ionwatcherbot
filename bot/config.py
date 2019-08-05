import os, re
from getpass import getpass
from collections import OrderedDict
from configparser import ConfigParser
from .instruments.instruments import Instruments

DOWNLOADS_MAIN_DIR = 'download'

class BotConfig:
    # The `cfg_text` variable holds the basic structure of the config file.
    # At instantiation, the config file is checked for the fields listed here.
    # When saving a config file, only the fields listed here will be saved.
    cfg_text = OrderedDict([
            ('NETWORK', OrderedDict([
                    ('token', 'Register your own copy of this bot with @BotFather, '
                              'and save your own token below.')])),
            ('COMM', OrderedDict([
                    ('pin', 'Ask for PIN at every X minutes (enter 0 to skip PIN checks):'),
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
    
    # Fields listed under `optionals` can be left blank in the config file.
    # 'pin' can be blank for compatibility with config files previous to v0.1.0.
    # 'users' can be blank because there will always be at least one member in 'admins'.
    optionals = ['pin', 'users', 'queue', 'blocked']
    
    # the `instr_cfg_text` holds data for instruments.
    instr_cfg_text = OrderedDict([
            ('name', 'Equipment name'),
            ('type', 'Equipment type (supported: ion)'),
            ('server', 'Equipment address'),
            ('user', 'Username (leave blank for none)'),
            ('pass', 'Password (leave blank for none, write "ASK" to ask for a password)')])
    
    def __init__(self, main):
        self.main = main
        self.ok = self.get_config()
    
    
    def get_config(self):
        '''
        Load configurations from the IonWatcher.cfg file.
        '''
        print('Reading configurations file...')
        if not os.path.isfile("IonWatcher.cfg"):
            print("Configuration file 'IonWatcher.cfg' not found.")
            return False
        config = ConfigParser()
        config.read("IonWatcher.cfg")
        aborting = False
        for category, items in self.cfg_text.items():
            for item in items:
                if item not in config[category] or config[category][item] == '':
                    if item not in self.optionals:
                        print('ERROR: Configurations file missing data: '
                              '[{0}] {1}'.format(category, item))
                        aborting = True
                        break
                    else:
                        config[category][item] = ''
            for item in config[category].keys():
                if item not in self.cfg_text[category].keys():
                    print('Warning: data [{0}] "{1}" not understood.'.format(
                          category, item))
        for instr_id in [key for key in config.keys() if key.startswith("INSTRUMENT")]:
            if all(key in config[instr_id] for key in ['name', 'type', 'server', 'user', 'pass']):
                print("Equipment config found: {} ({})".format(instr_id, config[instr_id]['name']))
            else:
                print("ERROR: invalid data for equipment '{}'".format(instr_id))
                aborting = True
                break
                
        if aborting:
            return False
        else:
            self.config = config
            # admins, users data must be loaded to adict;
            # queue and blocked can just be a set.
            # This must always be paired with `save_config`.
            self.admins = todict(self.config['COMM']['admins'])
            self.users = todict(self.config['COMM']['users'])
            # Admins are also loaded in the users dict, for easiness of checking privileges.
            self.users.update(self.admins)
            self.queue = toset(self.config['COMM']['queue'])
            self.blocked = toset(self.config['COMM']['blocked'])
            self.instr = dict()
            for instr_id in [key for key in config.keys() if key.startswith("INSTRUMENT")]:
                self.add_server(instr_id)
            if len(self.instr) == 0:
                print("No server successfully loaded.")
                return False
            self.pin_timer = int(self.config['COMM']['pin'])
            return True
    

    def clean_config_data(self, configloc, users):
        '''
        Remove unwanted characters for saving config; empty sets/dicts become ''
        :param str configloc: config key (always in 'COMM') to be updated
        :param users: users dict or set.
        '''
        self.config['COMM'][configloc] = \
                [re.sub('[\{\}\']', '', str(users)), ''][len(users) == 0]
    
    
    def update_config_data(self):
        self.clean_config_data('admins', self.admins)
        # Remove admins here to avoid saving them twice
        self.clean_config_data('users', dict([(key, value) for key, value in \
                self.users.items() if key not in self.admins]))
        self.clean_config_data('queue', self.queue)
        self.clean_config_data('blocked', self.blocked)
    
    def save_config(self):
        '''
        Save configuration data to the IonWatcher.cfg file.
        '''
        self.update_config_data()
       
        with open('IonWatcher.cfg', 'w') as f:
            f.write('# Configurations file for IonWatcher Bot\n\n')
            for category in self.cfg_text:
                f.write('[{}]\n'.format(category))
                for key, info in self.cfg_text[category].items():
                    f.write('# ' + info + '\n')
                    f.write('{0} = {1}\n'.format(key, str(self.config[category][key])))
                f.write('\n')
            f.write('# INSTRUMENTS\n')
            f.write('# Each equipment Must have a differently-named entry! ' + \
                    '(INSTRUMENT_01, INSTRUMENT_02...) \n')
            instr_keys = [key for key in self.config.keys() if key.startswith("INSTRUMENT")]
            for instrument in instr_keys:
                f.write('[{}]\n'.format(instrument))
                for key, info in self.instr_cfg_text.items():
                    f.write('# ' + info + '\n')
                    f.write('{0} = {1}\n'.format(key, str(self.config[instrument][key])))


    def add_server(self, instr_id):
        server = format_server_address(self.config[instr_id]['server'])
        instr_download_dir = "./{}/{}".format(DOWNLOADS_MAIN_DIR, instr_id)
        handler = Instruments[self.config[instr_id]['type']](server, instr_download_dir, self.main)
        username = self.config[instr_id]['user']
        flag = 'init'
        while flag != 'ok':
            authmode = handler.authmode
            if authmode == 'http_pw':
                # Input user (if not in config) and password (always)
                if username == '':
                    username = notblank('Username at {} {()}'.format(\
                                        self.config[instr_id]['name'], instr_id))
                if self.config[instr_id]['pass'].upper() == 'ASK':
                    pw = notblank('password', secret=True)
                else:
                    pw = self.config[instr_id]['pass']
            else:
                print("WARNING: unknown authmode for instrument type {}: {}".format(\
                      self.config[instr_id]['type'], authmode))
                return
            # Try if connection works
            print("Testing connection and authentication...")
            flag = handler.init_connection(username, pw)
            if flag != 'ok':
                opt = input("No connection or bad auth. (A)bort, (R)etry, (I)gnore? ")
                opt = opt.strip().upper()
                while opt not in ("A", "R", "I"):
                    opt = input("Invalid input. (A)bort, (R)etry, (I)gnore? ")
                    opt = opt.strip().upper()
                if opt == "A":
                    print("Aborting server connection.")
                    return False
                elif opt == "I":
                    flag = 'ok'
        # Everything OK, adding the server to the instrument list
        self.instr[instr_id] = handler
        # Verify that the instrument-specific download directory exists
        os.makedirs(instr_download_dir)
        

def toset(string):
    '''
    Split a string into a set (separator is comma).
    :param str string: The string to be separated.
    :return: a set.
    '''
    return set([item.strip() for item in string.split(',') if item.strip() != ''])


def todict(string):
    '''
    Return a dictionary from a concatenated string (comma-separated key:value pairs).
    :param str string: The string to be separated.
    :return: a dictionary.
    '''
    out = dict()
    for item in string.split(','):
        if item.strip() != '':
            if ":" in item:
                key, value = item.split(":")
                # Keep in list form
                value = value.strip(' []')
                if value == 'None':
                    value = None
                out[key.strip()] = [value]
            else:
                out[item.strip()] = [None]
    return out


def notblank(info, secret = False):
    '''
    Ask for input from the user; ask again if blank.
    :param str info: The string to be presented to the user when asking for input.
    :param bool secret: If True, use `getpass` to hide the user's text.
    '''
    text = ''
    hidden = [input, getpass]
    while not text:
        text = hidden[secret](info.capitalize()+': ')
    return text


def format_server_address(server):
    '''
    Attempt to format server address stored by admins in IonWatcher.cfg.
    Add 'http://' if missing, add last '/' if missing.
    :param str server: The server string obtained from config.
    :return: A (hopefully) correctly formed server string.
    '''
    
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
