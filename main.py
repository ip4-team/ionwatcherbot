import logging
from bot.bot import Mainloop
from version import __version__

# Start log
logging.basicConfig(filename='IonWatcher.log',
                    format='%(asctime)s - %(name)s - %(levelname)s - '
                           '%(message)s',
                    level=logging.INFO)
logging.info("Script started: version {}".format(__version__))

loop = Mainloop()
