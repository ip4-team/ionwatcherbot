import hashlib, time

class Chat:
    def __init__(self, user):
        self.user = user # telegram.User object
        self.status = 'start' # Chat status for persistency
        self.context = None # If monitoring an instrument
        self.lastpin = 0 # Last time user entered a PIN
        self.sha  = None # Used for double PIN verification
        self.pin = '' # Used for entering PIN digits
        self.pintries = 0 # How many times an invalid PIN has been entered
        
    
    def handle_pin(self, pin_digit, cfg_sha):
        '''
        :return: a tuple ("Message to the user", <offer a keyboard?> <action?>)
        '''
        if self.status not in ('newpin', 'pincheck'):
            return ("You are not entering a pin right now.", False, '')
        else:
            self.add_pin_digit(pin_digit)
            if len(self.pin) < 4:
                return("", False, "")
            else:
                sha = self.pin_to_sha()
                
                # Handle setting a new PIN
                if self.status == 'newpin':
                    if self.sha is None:
                        # This was the first round - still need to double check
                        self.set_sha(sha)
                        return ("Enter the new PIN a second time.", True, '')
                    else:
                        # Second round - the PIN must match to be valid
                        if self.sha == sha:
                            self.set_status('start')
                            self.reset_pin_time()
                            return ("Thank you. You PIN was saved.", True, 'update_cfg')
                        else:
                            self.set_sha(None)
                            self.pin = ''
                            return ("Your two entries did not match. Restarting.", True, '')
                        
                # Handle checking a PIN versus the saved sha256 in config
                elif self.status == 'pincheck':
                    if cfg_sha == sha:
                        self.reset_pin_time()
                        self.set_status('start')
                        return ("Thank you! You may now enter commands.", True, '')
                    else:
                        self.pintries += 1
                        self.pin = ''
                        if self.pintries < 3:
                            return ("Wrong PIN. This was your {} try. "
                                    "You will be locked after 3 attempts. \n"
                                    "If the connection is slow, please try "
                                    "entering the four digits slowly.".format(\
                                    ["first", "second"][self.pintries - 1]),
                                    True, '')
                        else:
                            self.pin = ''
                            self.pintries = 0
                            return("You have entered a wrong PIN thrice and " + \
                                   "have been returned to the queue.\n" + \
                                   "Please contact an administrator.", False, 'user_to_queue')


    def add_pin_digit(self, digit):
        self.pin = self.pin + digit
        
        
    def pin_to_sha(self):
        return hashlib.sha256(self.pin.encode()).hexdigest()
    

    def set_status(self, status, instr = None):
        if status not in ['start', 'join', 'admin', 'instr', 'back', 'bye', 'newpin', 'pincheck']:
            return
        if status == 'instr' and instr is not None:
                self.context = instr
        self.status = status
        if status in ('newpin', 'pincheck'):
            self.pin = ''
            self.sha = None
        if status == 'bye':
            self.lastpin = 0

        

    def set_sha(self, sha):
        self.sha = sha
        self.pin = ''
    

    def reset_pin_time(self):
        self.lastpin = time.time()
        self.pin = ''
        self.pintries = 0
        
