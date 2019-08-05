import os, logging, time
from threading import Timer
## To install the telegram module:
# pip install python-telegram-bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from .config import BotConfig
from .decorators import Usercheck
from .chat import Chat

TICK_TIMER = 30 # minutes

class Mainloop:
    '''
    This class harbors the main bot loop.
    '''
    
    def __init__(self):
        self.starttime = time.time()
        self.rt = dict() # {id: RepeatTimer()}
        self.chats = {}
        self.cfg = BotConfig(self)
        if not self.cfg.ok:
            print('Configurations could not be loaded. Ending the script.')
            os._exit(0)

        # Keyboard buttons, based on status
        self.keyboards = {'administration': [[InlineKeyboardButton("Administration", callback_data='A')]],
                          'admin': [[InlineKeyboardButton("Start ticking", callback_data='T'),
                                    InlineKeyboardButton("Stop ticking", callback_data='U')],
                                    [InlineKeyboardButton("View queue", callback_data='Q'),
                                    InlineKeyboardButton("Download log", callback_data='L')],
                                    [InlineKeyboardButton("Kill the bot", callback_data='K')]],
                          'exit': [[InlineKeyboardButton("Exit", callback_data='E')]],
                          'back': [[InlineKeyboardButton("Back", callback_data='B')]],
                          'instr': []
                         }
        for instrument in self.cfg.instr.keys():
            inst_name = self.cfg.config[instrument]['name']
            self.keyboards['instr'].append([InlineKeyboardButton(inst_name, \
                                           callback_data=instrument)])  

        # Create updater and dispatcher
        self.updater = Updater(token=self.cfg.config['NETWORK']['token'])
        dispatcher = self.updater.dispatcher

        # register basic handlers
        dispatcher.add_handler(CommandHandler('start', self.start))
        dispatcher.add_handler(CommandHandler('kill', self.kill))
        dispatcher.add_handler(CommandHandler('tick', self.tick))
        dispatcher.add_handler(CommandHandler('untick', self.untick))
        dispatcher.add_handler(CommandHandler('join', self.join))
        dispatcher.add_handler(CommandHandler('log', self.send_log))
        dispatcher.add_handler(CommandHandler('bye', self.bye))
        dispatcher.add_handler(CallbackQueryHandler(self.button))

        # Start
        logging.info("Server started.")
        print('Listening...')
        self.updater.start_polling()

                
    # Bot methods, ordered by user level and then alphabetically
    # The first are general methods; no clearance
    def button(self, bot, update):
        '''
        Handler for all button events.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        query = update.callback_query
        user = update.effective_user
        if user.id not in self.chats:
            self.newchat(user)
        # In all of the following cases, execute the relative function.
        sender = {'A': self.admin,
                  'L': self.send_log,
                  'Q': self.join,
                  'K': self.killwarning,
                  'T': self.tick,
                  'U': self.untick,
                  'E': self.bye,
                  'B': self.start}
                  
        if query.data in sender:
            sender[query.data](bot, update)
        
        # Handle user approval and denial
        elif query.data.startswith("App_"):
            app_username = query.data[4:]
            self.approve(bot, update, app_username)
        
        elif query.data.startswith("Blo_"):
            block_username = query.data[4:]
            self.block(bot, update, block_username)
        
        # Handle main instrument buttons
        elif query.data in self.cfg.instr.keys():
            self.chats[user.id].set_status('instr', instr=query.data)
            bot.sendMessage(chat_id=user.id, text='Entering {} menu.'.format(\
                            self.cfg.config[query.data]['name']))
            self.keyboard(bot, update)
            
        # Handle instrument-specific buttons
        elif self.chats[user.id].status == 'instr':
            context = self.chats[user.id].context
            instr_handler = self.cfg.instr[context]
            # Might be changeable, so needs to be redone each time
            command = dict()
            for _button_name, method, local_callback_data in instr_handler.keyboard:
                full_callback_data = context + '_' + local_callback_data
                command[full_callback_data] = [method, local_callback_data]
                if query.data in command.keys():
                    # Ugly but works
                    next_status = command[query.data][0](bot, update, command[query.data][1])
                    self.chats[user.id].set_status(next_status)
                    self.keyboard(bot, update)
            
        # Handle PIN inline keyboard events
        elif query.data.startswith("Pin_"):
            pin_digit = query.data[4]
            message, to_keyboard, action = self.chats[user.id].handle_pin(\
                    pin_digit=pin_digit, cfg_sha=self.cfg.users[user.username][0])
            if action == 'update_cfg':
                # This will keep updated both self.cfg.users and self.cfg.admins
                self.cfg.users[user.username][0] = self.chats[user.id].sha
                self.chats[user.id].set_sha(None)
                self.cfg.save_config()
            elif action == 'user_to_queue':
                self.cfg.users.pop(user.username)
                if user.username in self.cfg.admins:
                    self.cfg.admins.pop(user.username)
                self.cfg.queue.add(user.username)
                self.save_config()
                logging.info("User {} has been returned to the queue "
                             "for failing 3 authentication attempts.".format(\
                                     user.username))
            if message != '':
                bot.sendMessage(chat_id=user.id, text=message)
            if to_keyboard:
                self.keyboard(bot, update)
            


            
    def keyboard(self, bot, update):
        '''
        Offer command options to the user, based on the user's current status.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        keyboard = []
        user = update.effective_user
        text = "How can I help you, {}?".format(user.first_name)
        status = self.chats[user.id].status
        context = self.chats[user.id].context
        markup = InlineKeyboardMarkup
        if status == 'start':
            if user.username in self.cfg.admins:
                keyboard.extend(self.keyboards['administration'])
            if user.username in self.cfg.users:
                keyboard.extend(self.keyboards['instr'])
                keyboard.extend(self.keyboards['exit'])
            elif user.username in self.cfg.blocked or user.username in self.cfg.queue:
                return
            else:
                keyboard.append([InlineKeyboardButton("Join queue",
                                                          callback_data='Q')])

        if status == 'join':
            if user.username in self.cfg.admins:
                text = "Choose any action:"
                for queued in self.cfg.queue:
                    keyboard.append([InlineKeyboardButton("Approve "+queued, 
                                                          callback_data='App_'+queued),
                                     InlineKeyboardButton("Block", 
                                                          callback_data='Blo_'+queued)])
        
        if status == 'instr':
            instr_handler = self.cfg.instr[context]
            # Might be changeable, so needs to be redone each time
            for button_name, _method, callback_data in instr_handler.keyboard:
                keyboard.append([InlineKeyboardButton(button_name,
                        callback_data=context+'_'+callback_data)])

        if status == 'admin':
            text = "Entering admin menu."
            keyboard.extend(self.keyboards['admin'])

        if status == 'back' or status not in ('start', 'newpin', 'pincheck'):
            keyboard.extend(self.keyboards['back'])
        
        if status in ('newpin', 'pincheck'):
            text = "Please enter your PIN using the following buttons:"
            for row in range(2):
                keyboard.append([])
                for number in range(5):
                    strnum = str(5 * row + number)
                    keyboard[-1].append(InlineKeyboardButton(strnum,
                                                              callback_data='Pin_'+strnum))
            
        reply_markup = markup(keyboard)
        bot.sendMessage(chat_id=user.id, text=text, reply_markup=reply_markup)


    def newchat(self, user):
        '''
        Add a new chat to the dictionary of chats.
        :param user: telegram.User object for the current user.
        '''
        self.chats[user.id] = Chat(user)
        logging.info("Initiated chat with user: {}".format(user.username))

       
    def firstpin(self, bot, update):
        '''
        Register a user's PIN.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        user = update.effective_user
        bot.sendMessage(chat_id=user.id, text="Please choose a 4-digit PIN.")
        self.chats[user.id].set_status('newpin')
        self.keyboard(bot, update)
        

    def pincheck(self, bot, update):
        '''
        Verify a user's PIN.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        user = update.effective_user
        bot.sendMessage(chat_id=user.id, text="Please enter your PIN.")
        self.chats[user.id].set_status('pincheck')
        self.keyboard(bot, update)
        

    # User actions
    # For practicality, both `join` and `start` are entry points for new chats.
    @Usercheck('any')
    def join(self, bot, update):
        '''
        Add the user to the join queue, or view queue if admin
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        user = update.effective_user
        if user.username in self.cfg.queue:
            bot.sendMessage(chat_id=user.id, 
                    text="Hello, {}. You are already in the queue.".format(user.username))
            self.chats[user.id].set_status('start')
        elif user.username not in self.cfg.users:
            self.chats[user.id].set_status('join')
            self.cfg.queue.add(user.username)
            self.save_config()
            bot.sendMessage(chat_id=user.id, 
                    text="You have been added to the queue, {}.".format(user.username))
            
        else:
            if not self.cfg.queue:
                bot.sendMessage(chat_id=user.id, text="There are no users in the queue.")
                self.chats[user.id].set_status('start')
            else:
                bot.sendMessage(chat_id=user.id, 
                        text="The following users are in the queue:\n" + \
                        ''.join(['@{}\n'.format(name) for name in self.cfg.queue]))
                self.chats[user.id].set_status('join')
        self.keyboard(bot, update)


    @Usercheck('any')
    def start(self, bot, update):
        '''
        The basic command to start a chat.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        user = update.effective_user
        if user.id not in self.chats:
            self.newchat(user)
        # If the message is from a truster user or admin, no special handling
        if user.username in self.cfg.users:
            pass
        
        # If the user is still in the queue, inform him/her
        elif user.username in self.cfg.queue:
                bot.sendMessage(chat_id=user.id, 
                                text="Hello, {}. I'm afraid you haven't been "
                                "cleared from the queue yet. Please speak to "
                                "an administrator to get clearance.".format(
                                user.username))
        
        # If it's a new user, greet him/her
        else:
            bot.sendMessage(chat_id=user.id, 
                            text=self.cfg.config['MESSAGES']['start'])
        self.chats[user.id].set_status('start')
        self.keyboard(bot, update)
    

    @Usercheck('user')
    def bye(self, bot, update):
        '''
        If PIN is enabled, ask for PIN at next interaction. Also say goodbye.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        user = update.effective_user
        self.chats[user.id].set_status('bye')
        bot.sendMessage(chat_id=user.id, 
                        text="Goodbye, {}. Type /start to restart.".format(user.first_name))


    @Usercheck('admin')
    def admin(self, bot, update):
        user = update.effective_user
        if user.username in self.cfg.admins:
            self.chats[user.id].set_status('admin')
            self.keyboard(bot, update)

    @Usercheck('admin')
    def approve(self, bot, update, username):
        '''
        Transfer a user from the queue to registered users.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        :param username: the user's Telegram nickname.
        '''
        user = update.effective_user
        self.cfg.users[username] = [None]
        self.cfg.queue.remove(username)
        self.save_config()
        bot.sendMessage(chat_id=user.id, 
                text="User {} has been approved.".format(username))
        self.keyboard(bot, update)
    

    @Usercheck('admin')
    def block(self, bot, update, username):
        '''
        Transfer a user from the queue to blocked users.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        :param username: the user's Telegram nickname.
        '''
        user = update.effective_user
        self.cfg.blocked.add(username)
        self.cfg.queue.remove(username)
        self.save_config()
        bot.sendMessage(chat_id=user.id, 
                text="User {} has been blocked.".format(username))
        self.keyboard(bot, update)


    @Usercheck('admin')
    def kill(self, bot, update):
        '''
        End execution of the bot.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        user = update.effective_user
        bot.sendMessage(chat_id=user.id, 
                        text=self.cfg.config['MESSAGES']['kill'])
        #self.updater.stop() # is just not working to stop the script
        os._exit(0)

    
    @Usercheck('admin')
    def killwarning(self, bot, update):
        user = update.effective_user
        bot.sendMessage(chat_id=user.id, 
                        text="Please use the command /kill to stop the bot.")


    @Usercheck('admin')
    def send_log(self, bot, update):
        user = update.effective_user
        with open('IonWatcher.log', 'rb') as document:
            bot.sendDocument(chat_id=user.id, document=document, filename='IonWatcher.log.txt')

        
    @Usercheck('admin')
    def tick(self, bot, update):
        '''
        Start ticking system uptime every half an hour.
        This helps keeping the bot reachable by Telegram when its IP is not static.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        user = update.effective_user
        if user.id not in self.rt.keys():
            self.rt[user.id] = RepeatedTimer(TICK_TIMER * 60, self.send_tick, bot, user)
            bot.sendMessage(chat_id=user.id, 
                            text=self.cfg.config['MESSAGES']['tick'])        
            self.send_tick(bot, user)
        else:
            self.send_tick(bot, user)

        
    @Usercheck('admin')
    def untick(self, bot, update):
        '''
        Stop ticking system uptime every half an hour.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param update: the received update, automatically informed by python-telegram-bot.
        '''
        user = update.effective_user
        if user.id in self.rt.keys():
            self.rt[user.id].stop()
            gone = self.rt.pop(user.id)
            bot.sendMessage(chat_id=user.id, 
                            text=self.cfg.config['MESSAGES']['untick'])
    

    def send_tick(self, bot, user):
        '''
        Send a "tick" to the user.
        :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
        :param user: telegram.User object.
        '''
        delta = time.time() - self.starttime
        days, remainder = divmod(delta, 60*60*24)
        hms = time.strftime('%H:%M:%S', time.gmtime(remainder))
        bot.sendMessage(chat_id=user.id,
                        text="Bot uptime: {} days {}".format(days, hms))
    


class RepeatedTimer(object):
    '''
    Class used to offer periodic "ticks" to users.
    From StackOverflow user MestreLion (.../users/624066/mestrelion):
    https://stackoverflow.com/questions/474528/what-is-the-best-way-to-repeatedly-execute-a-function-every-x-seconds-in-python
    
    '''

    def __init__(self, interval, function, *args, **kwargs):
        '''
        Instantiate the timer.
        :param interval: timer interval (in seconds).
        :param function: the function to be called every x seconds.
        :param args: any args to be passed to the functon.
        :param kwargs: any kwargs to be passed to the functon.
        '''
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


