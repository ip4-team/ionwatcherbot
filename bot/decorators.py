'''

SECURITY

'''

import logging
import time

class Usercheck(object):
    '''
    This class holds a decorator that will be used to check for user privileges
    and PIN status after a command is received.
    
    '''
    
    def __init__(self, userlevel):
        '''
        :param str userlevel: `userlevel` can be: 'any', 'user', or 'admin'.
        '''
        self.userlevel = userlevel

    
    def __call__(self, action):
        '''
        :param action: the decorated function.
        '''
        def wrapper(sender, bot, update, *args):
            '''
            Wrapper function. Typical args include `bot`,
            :param sender: 'self' from the decorated function.
            :param bot: telegram.bot.Bot instance, automatically informed by python-telegram-bot.
            :param update: the received update, automatically informed by python-telegram-bot.
            :param args: any other arguments
            '''
            # Recovering the mainloop from instrument-specific calls
            if 'mainloop' in sender.__dir__():
                instance = sender.mainloop
            else:
                instance = sender
            user = update.effective_user
            username = user.username
            # chat control
            if user.id not in instance.chats:
                instance.newchat(user)
            # PIN control
            if instance.cfg.pin_timer != 0:
                if username in instance.cfg.users:
                    if instance.cfg.users[username][0] is None:
                        return instance.firstpin(bot, update)
                    elif time.time() - instance.chats[user.id].lastpin > instance.cfg.pin_timer * 60:
                        instance.chats[user.id].set_status('pincheck')
                        return instance.pincheck(bot, update)
            if update.message:
                logtext = update.message.text
            elif update.callback_query:
                logtext = "[Button_{}]".format(update.callback_query.data)
            else:
                logging.warning("couldn't establish user. Update is:" + str(update))
                return None
            negate_text = instance.cfg.config['MESSAGES']['negate']
            # Access control
            if username in instance.cfg.blocked:
                auth = [] # no access
                negate_text = 'You have been blocked and cannot issue any command.'
            elif self.userlevel == 'any':
                auth = True
            elif self.userlevel == 'user':
                auth = instance.cfg.users
            else:
                auth = instance.cfg.admins
            if auth is True or username in auth:
                logging.info("Approved {0} command from: {1}".format( 
                        logtext, username))
                return action(sender, bot, update, *args)     
            else:
                logging.info("Blocked {0} command from: {1}".format( 
                        logtext, username))
                bot.sendMessage(chat_id=user.id, 
                        text=negate_text)
                return None
        return wrapper
