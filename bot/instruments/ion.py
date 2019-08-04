from telegram import error
import json, logging, re
from shutil import copyfileobj
from collections import OrderedDict
import requests
## To install bs4:
# pip install beautifulsoup4
## In case "Couldn't find a tree builder":
# pip install lxml
##  or possibly:
# sudo apt install python-lxml
from bs4 import BeautifulSoup
from ..decorators import Usercheck

class Handler:
    # Specify the authorization mode to contact the server (see config.py)
    authmode = 'http_pw'
    
    api = 'rundb/api/v1/'
    
    def __init__(self, server, mainloop):
        self.methods = OrderedDict([('Check runs in progress', self.monitor)])
        self.server = server
        self.mainloop = mainloop
        self.init_specifics()
        # ("Button name", <method>, "callback_data")
        self.keyboard = [("Monitor runs", self.monitor, "Monitor")]
        

    def init_specifics(self):
        self.runs = dict()
        # File location and description of downloadable images on the server    
        self.images = [['Bead_density_200.png', 'bead density'],
                       ['basecaller_results/wells_beadogram.png', 'bead quality data'],
                       ['basecaller_results/readLenHisto2.png', 'read size distribution'],
                       ['iontrace_Library.png', 'key signal data']]

    
    def init_connection(self, username, pw):
        self.auth = requests.auth.HTTPBasicAuth(username, pw)
        runs, flag = self.read_monitor()
        return flag


    def report_link(self, bot, update, run):
        '''
        Attempt to deliver a run's PDF report.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        :param run: serialized run data read from the server by self.read_monitor().
        '''
        user = update.effective_user
        run_dir_id = run['id']
        report_pdf = self.get_pdf(run_dir_id)
        if report_pdf:
            self.pdf(bot, update, run_dir_id)
        else:
            bot.sendMessage(chat_id=user.id, text="The pdf report is not ready yet.")
        self.chats[user.id]['status'] = 'monitor'
        self.keyboard(bot, update)
            

    
    # EACH INSTRUMENT-SPECIFIC METHOD MUST:
    # 1. BE LISTED IN self.keyboard
    # 2. ACCEPT PARAMETERS (self, bot, update, callback_data)
    # 3. RETURN THE NEXT STATUS FOR THE CHAT
    # 4. NOT CALL THE KEYBOARD AGAIN
    # 5. BE DECORATED BY Usercheck AT THE APPROPRIATE CLEARANCE LEVEL
    
    @Usercheck('user')
    def monitor(self, bot, update, callback_data):
        '''
        Return data about the current runs in progress.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        user = update.effective_user
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
            # self.runs.update(runs)
            self.runs = runs
            # Clean the keyboard
            torem = [item for item in self.keyboard if item[2].startswith('Run_')]
            for item in torem:
                self.keyboard.remove(item)
            for run_dir_id, run in sorted(self.runs.items()):
                # TODO see flows
                runname = re.sub('Auto_[\w]*?_', '', run['resultsName'])
                run_status = run['status']
                string = ('[{}]\n{}\n'        
                          'Status: {}'.format(run_dir_id, runname,         
                                              run_status))
                bot.sendMessage(chat_id=user.id, text=string)
            self.keyboard.append([(str(run), self.run_report, \
                                   'Run_'+str(run)) for run in self.runs])
        return 'instr'
        
        


    @Usercheck('user')
    def run_report(self, bot, update, callback_data):
        '''
        Message run report data to the user.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        :param callback_data: the callback_data string, that contains the run ID.
        '''
        user = update.effective_user
        
        # runs         
        run_id = int(callback_data[4:])
        run = self.runs.get(run_id, None)
        try:
            self.run_report(bot, update, run)
        except error.TimedOut:
            bot.sendMessage(chat_id=user.id, text="Sorry, I lost connection to Telegram while fulfilling your request.")
            logging.warning("Lost connection to Telegram.")
            self.chats[user.id].set_status('start')
            self.keyboard(bot, update)
                
                
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


    def read_monitor(self):
        '''
        Scrape data about current runs from the server and return it.
        
        '''
        
        flag = ''
        
        api_page = self.server+self.api+'monitorresult/'
        
        logging.info("Contacting: "+api_page)
        try:
            response = requests.get(api_page,
                                         auth=self.auth, 
                                         verify=False)
            monitor_json = json.loads(response.text)
            
        except:
            logging.warning("Server unreachable or bad auth.")
            flag = 'no_connection'
            return [None, flag]
        flag = 'ok'
        # meta = monitor_json['meta']
        runs = {obj['id']: obj for obj in monitor_json['objects'] if obj}
        return [runs, flag]


    def send_server_data(self, user, bot, complete = False):
        '''
        Send a "tick" to the user.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        :param complete: if True, information is more verbose.
        '''
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


def get_tag_text(bs4tag, tagstring):
    '''
    Return text from a beautofulsoup tag and string.
    :param bs4tag: the tag to be searched for the string.
    :param tagstring: the string to be searched within the tag.
    '''
    taglist = bs4tag.find_all(tagstring)
    taglist = [collapse(item.text) for item in taglist]
    return taglist


def collapse(text):
    '''
    Collapse all whitespace in a string.
    Solution derived from StackOVerflow user Alex Martelli (.../95810/alex-martelli):
    https://stackoverflow.com/questions/1274906/collapsing-whitespace-in-a-string
    :param text: the text to be processed.
    '''
    rex = re.compile(r'\W+')
    return rex.sub(' ', text).strip()

    # file retrieving methods
    def get_image(self, run_id, filename):
        '''
        Attempt to retrieve an image file from the server.
        :param run_id: the run's ID within the server.
        :param filename: location of the image.
        '''
        loc = 'report/{}/metal/{}'.format(run_id, filename)
        # Removing dirs from filename
        destname = filename[filename.rfind('/')+1:]
        dest = 'download/{}_{}'.format(run_id, destname)
        return self.get_file(loc, dest)
        
        
    def get_pdf(self, run_id):
        '''
        Attempt to retrieve an PDF file from the server.
        :param run_id: the run's ID within the server.
        '''
        loc = 'report/latex/{}.pdf'.format(run_id)
        dest = 'download/{}.pdf'.format(run_id)
        return self.get_file(loc, dest)


    def pdf(self, bot, update, report_id):
        '''
        Deliver a PDF file to the user.
        '''
        user = update.effective_user
        with open('download/{}.pdf'.format(report_id), 'rb') as document:
            bot.sendDocument(chat_id=user.id, document=document)        

        
    def get_file(self, loc, dest):
        '''
        Generic method to retrieve a file from the server and save it locally.
        :param loc: path to the file on the server.
        :param dest: path to the locally saved copy.
        '''
        try:
            response = requests.get(self.server+loc, auth=self.auth,
                                    verify=False, stream=True)
            with open(dest, 'wb') as out_file:
                copyfileobj(response.raw, out_file)
            return dest
        except:
            return None
    

def pcsquares(value):
    '''
    Offer a visual representation of a number 0.0 - 1.0.
    Return a string with unicode representations of open and closed boxes,
    with each box representing the value of 0.2 (20%), rounded down.
    :param value: The value to be represented (float or int).
    '''
    valuepc = value  * 100
    blue = int(min((valuepc // 20)+1, 5))
    white = 5 - blue
    return  [u'\U0001F535' * blue + u'\U000026AA' * white, value]

    
def mark(boolean):
    '''
    Return the unicode representation of a checked mark or an X.
    :param bool boolean: The True / False information to represent visually.
    '''
    return [u'\U0000274C', u'\U00002705'][boolean]
