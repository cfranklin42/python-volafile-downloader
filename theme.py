from pathlib import Path
from datetime import datetime

# Color Theme
# Valid colors: white, red, yellow, blue, teal, green, purple
# New File Notice
# FILE: New File.zip [Uploader] (60.00 MB)
C_FILE_NOTICE = "teal"
C_FILE_NAME = "white"
C_FILE_BRACKETS = "blue"
C_FILE_UPLOADER = "white"
C_FILE_PAREN = "blue"
C_FILE_SIZE = "white"

BC = {
    "teal": '\033[96m',
    "white": '\033[0m',
    "blue": '\033[94m',
    "purple": '\033[95m',
    "red": '\033[91m',
    "green": '\033[92m',
    "yellow": '\033[93m',
    "endc": '\033[0m',
}

class bcolors:
    HEADER = '\033[95m' # purple
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    OKTEAL = '\033[96m'
    WARNING = '\033[93m' # yellow
    FAIL = '\033[91m' # red
    ENDC = '\033[0m'

    def disable(self):
        self.HEADER = ''
        self.OKBLUE = ''
        self.OKGREEN = ''
        self.WARNING = ''
        self.FAIL = ''
        self.ENDC = ''

def short_time(t=None):
    """ Time used in printed messages """
    if t is None:
        t = datetime.now()
    return str(t.strftime("%H:%M:%S"))

def print_file_info(f):
    """
    f.url, f.size, f.uploader
    """
    file_size = f'{f.size / (1024*1024):.2f}'
    file_link = create_hyperlink(f.url, Path(f.url).name)
    print(f'{BC[C_FILE_NOTICE]}[{short_time()}] FILE: '\
          f'{BC[C_FILE_NAME]}{file_link} '\
          f'{BC[C_FILE_BRACKETS]}[{BC[C_FILE_UPLOADER]}{f.uploader}{BC[C_FILE_BRACKETS]}] '\
          f'{BC[C_FILE_PAREN]}({BC[C_FILE_SIZE]}{file_size} MB{BC[C_FILE_PAREN]}){BC["endc"]}')

def create_hyperlink(url, text):
    """ Creates a VTE hyperlink clickable in a terminal window """
    if True: # TODO: Check for capability or config
        return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"
    else:
        return text

