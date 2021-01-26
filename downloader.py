#!/usr/bin/env python3
from tqdm import tqdm
import argparse
import requests
import string
import random
from datetime import datetime, timedelta, date
import time
from pathlib import Path
import re

from jdownloader import JDownloaderCore
from volapi import Room

import config
from theme import bcolors, print_file_info, short_time
import unified_duplicate_checker

class VolaDLException(Exception):
    def __init__(self, kill=False):
        self.kill = kill

class VolaDL(object):
    def __init__(self, room, password, downloader=None, logger=None, myjdownloader=None, jdownloader=None, folder=None):
        """Initialize Object"""
        self.counter = 0
        self.headers = config.HEADERS
        self.cookies = config.COOKIES
        self.downloader = config.DOWNLOADER
        self.logger = config.LOGGER

        self.vola_user = config.VOLAFILE_USER or "downloader"

        self.room = room
        self.password = password
        if downloader is not None:
            self.downloader = downloader
        if logger is not None:
            self.logger = logger
        
        # FolderWatch method takes priority over MyJDownloader
        self.myjdownloader = None
        self.jdownloader = jdownloader
        if self.jdownloader is None:
            self.jdownloader = config.USE_JDOWNLOADER_FOLDERWATCH
        if self.jdownloader is None:
            self.myjdownloader = myjdownloader
            if self.myjdownloader is None:
                self.myjdownloader = config.USE_MYJDOWNLOADER

        self.download_all = config.DOWNLOAD_ALL_ON_ROOM_ENTER
        self.duplicate = not config.ALLOW_DUPLICATES
        self.continue_running = config.CONTINUE_RUNNING
        self.max_file_size = config.MAXIMUM_FILE_SIZE

        self.download_path = config.DOWNLOAD_PATH
        if folder:
            self.download_path = folder
        self.log_path = Path(config.LOG_PATH) / self.room
        self.refresh_delta = timedelta(days=1)
        self.start_time = datetime.now()
        self.user_whitelist = []
        self.user_blacklist = []
        self.filename_whitelist = []
        self.filename_blacklist = []
        self.filetype_whitelist = []
        self.filetype_blacklist = []

        if self.jdownloader or self.myjdownloader:
            self.jdcore = JDownloaderCore(
                folderwatch=self.jdownloader,
                myjd=self.myjdownloader
            )
            try:
                self.jdcore.setup()
            except:
                raise VolaDLException(kill=True)

        # Load previously downloaded files so we don't download them again
        self.jd_logpath = Path(config.LOG_PATH) / ("[" + self.room + "] downloaded.txt")
        self.jd_downloaded_urls = self.get_logged_urls(self.jd_logpath)

        if self.config_check():
            print(bcolors.FAIL+'### YOU CAN NOT USE A BLACKLIST AND A WHITELIST FOR THE SAME FILTER.'+bcolors.ENDC)
            raise VolaDLException(kill=True)

    def dl(self, firstStart: bool):
        """Main method that gets called at the start"""

        def onfile(f):
            """Listener on new files in the room"""
            if self.max_file_size > -1 and f.size / 1048576 >= self.max_file_size:
                print_file_info(f)
                print(bcolors.FAIL + 'File is too big to download.' + bcolors.ENDC)
            elif self.file_check(f):
                self.single_file_download(f, quiet=False)
            else:
                print_file_info(f)
                print(f'  {bcolors.WARNING}File got filtered out.{bcolors.ENDC}')

        def ontime(t):
            """React to time events emitted by volafile socket connection, used for maintenance"""
            if datetime.now() > self.start_time + self.refresh_delta:
                # if the refresh delta has passed, restart the bot
                st = short_time()
                print(bcolors.OKTEAL+f"[{st}] A day has passed. Reloading bot."+bcolors.ENDC)
                self.close()
                return t
            # check for connections
            if self.listen:
                if not self.listen.connected:
                    print(bcolors.FAIL+"Connected has been lost."+bcolors.ENDC)
                    self.close()
            return t

        def onmessage(m):
            """React to and log chat messages"""
            self.log_room(m)

        self.listen = self.create_room()

        if firstStart:
            print("dl() starting up listeners")
        if self.download_all and self.downloader:
            if firstStart:
                print("Downloading room on enter")
            duplicate_temp = self.duplicate
            self.duplicate = True
            self.download_room(firstStart=firstStart)
            self.duplicate = duplicate_temp
        if not self.continue_running:
            raise VolaDLException(kill=True)
        if self.downloader:
            self.listen.add_listener("file", onfile)
        if self.logger:
            self.listen.add_listener("chat", onmessage)
        if self.downloader or self.logger:
            self.listen.add_listener("time", ontime)
            try:
                self.listen.listen()
            except OSError as err:
                if err.errno in {
                            121, # semaphore timeout period has expired on Windows
                        }:
                    print(bcolors.WARNING+"!!! Semaphore timeout period has expired !!!"+bcolors.ENDC)
                    self.close()
        else:
            print('### You need to activate either LOGGER or DOWNLOADER for the bot to continue running')
            raise VolaDLException(kill=True)

    def log_room(self, msg):
        if msg.nick == 'News' and msg.system:
            return False
        time_now = datetime.now()
        prefix = VolaDL.prefix(msg)
        self.log_path.mkdir(parents=True, exist_ok=True)
        file_name = time_now.strftime("[%Y-%m-%d]") + "[" + self.room + "].txt"
        path = self.log_path / str(file_name)

        st = short_time(time_now)
        print(f'{bcolors.HEADER}[{st}]{bcolors.ENDC} {prefix}{msg.nick}: {str(msg)}')
        log_msg = '[{}][{}][{}][{}]\n'.format(str(time_now.strftime("%Y-%m-%d--%H:%M:%S")), prefix, msg.nick, str(msg))
        with path.open("a", encoding="utf-8") as fl:
            fl.write(log_msg)

    def download_room(self, firstStart=True):
        """Download the whole room on enter"""
        time.sleep(2)
        file_list = self.listen.files
        for f in file_list:
            if not self.max_file_size == -1 and f.size / 1048576 >= self.max_file_size:
                print_file_info(f)
                print(bcolors.FAIL + 'File is too big to download.' + bcolors.ENDC)
            elif self.file_check(f):
                self.single_file_download(f, quiet=not firstStart)
            elif firstStart:
                print_file_info(f)
                print(bcolors.WARNING + '  File got filtered out.' + bcolors.ENDC)
        if firstStart:
            print(f'{bcolors.OKBLUE}### ### ###')
            print('Downloading the room has finished. Leave this running to download new files/log')
            print(f'### ### ###{bcolors.ENDC}')

    def download_file(self, url, download_path) -> bool:
        """ Downloads a file from volafile and shows a progress bar
        Returns False if there was an error """
        chunk_size = 1024
        try:
            r = requests.get(url, stream=True, headers=self.headers, cookies=self.cookies)
            r.raise_for_status()
            if not r:
                return False
            total_size = int(r.headers.get("content-length", 0))
            temp_path = download_path.with_suffix(download_path.suffix + ".part")
            with temp_path.open("wb") as fl:
                for data in tqdm(iterable=r.iter_content(chunk_size=chunk_size), total=total_size / chunk_size,
                                 unit="KB", unit_scale=True):
                    fl.write(data)
            temp_path.rename(download_path)
            return True
        except Exception as ex:
            print("[-] Error: " + str(ex))
            return False

    def manual_single_file_download(self, f) -> bool:
        """Returns False if there was an error"""
        file_name = Path(f.url).name
        download_path = f.subfolder / file_name
        download_path.parent.mkdir(parents=True, exist_ok=True)

        if self.duplicate and download_path.is_file():
            print(f"{bcolors.WARNING}File exists already!{bcolors.ENDC}")
            return False
        elif download_path.is_file():
            new_name = download_path.stem + "-" + VolaDL.id_generator() + download_path.suffix
            download_path = download_path.with_name(new_name)
        self.counter += 1
        print(f'[{self.counter}] Downloading to: {download_path}')
        return self.download_file(f.url, download_path)


    def parse_download_path(self, path: str, f):
        path = path.replace("{ROOM}", f.room.name)
        d = 2 # try to adjust expiration date
        if f.expire_time - 2*60*60*24 > datetime.now().timestamp():
            d = 4

        dreg = re.compile(r"{DATE:([^}]+)}")
        while dreg.search(path):
            m = dreg.search(path)
            ymd = datetime.fromtimestamp(f.expire_time - d*60*60*24).strftime(m.group(1))
            path = dreg.sub(ymd, path, count=1)
        path = path.replace("{UPLOADER}", f.uploader)
        return Path(path)


    def single_file_download(self, f, quiet=False) -> bool:
        """Prepares a single file from vola for download"""
        already_downloaded = f.url in self.jd_downloaded_urls
        if not quiet or not already_downloaded:
            print_file_info(f)
        if not already_downloaded and unified_duplicate_checker.is_duplicate_file(f):
            print(f'{bcolors.FAIL}  Unified Duplicate Checker: File is a duplicate{bcolors.ENDC}')
            already_downloaded = True
        if already_downloaded:
            return True

        f.subfolder = self.parse_download_path(self.download_path, f)
        if self.myjdownloader or self.jdownloader:
            ret = self.jdcore.jdownloader_single_file_download(f)
            if ret:
                self.counter += 1
                if self.jdownloader:
                    print(f'  {bcolors.OKGREEN}[{bcolors.ENDC}{self.counter}{bcolors.OKGREEN}] Sent to Folder Watch{bcolors.ENDC}')
                elif self.myjdownloader:
                    print(f'  {bcolors.OKGREEN}[{bcolors.ENDC}{self.counter}{bcolors.OKGREEN}] Sent to My.JDownloader{bcolors.ENDC}')
                # Add the url to the logged urls file
                self.log_file(f)
            return ret
        else:
            print_file_info(f)
            return self.manual_single_file_download(f)

    def log_url(self, url: str) -> None:
        """Log that a url was downloaded so we don't download it again"""
        with self.jd_logpath.open("a", encoding="utf-8") as f:
            f.write(url + '\n')

    def log_file(self, f) -> None:
        self.jd_downloaded_urls.append(f.url)
        unified_duplicate_checker.log_file(f.name, f.size, f.checksum)
        self.log_url(f.url)

    def get_logged_urls(self, path):
        """Retrieve the room's logged urls so we don't download them again"""
        if path.is_file():
            with path.open("r", encoding="utf-8") as f:
                return list(set(f.read().splitlines()))
        return []

    def config_check(self):
        """Checks filter configs for validity and prepares them for filtering"""
        if (config.USE_USER_BLACKLIST and config.USE_USER_WHITELIST) or (
                config.USE_FILENAME_BLACKLIST and config.USE_FILENAME_WHITELIST) or (
                config.USE_FILETYPE_BLACKLIST and config.USE_FILETYPE_WHITELIST):
            return (config.USE_USER_BLACKLIST and config.USE_USER_WHITELIST) or (
                    config.USE_FILENAME_BLACKLIST and config.USE_FILENAME_WHITELIST) or (
                           config.USE_FILETYPE_BLACKLIST and config.USE_FILETYPE_WHITELIST)
        else:
            if config.USE_USER_BLACKLIST:
                self.user_blacklist = config.USER_BLACKLIST
                self.config_list_prepare(self.user_blacklist)
            if config.USE_USER_WHITELIST:
                self.user_whitelist = config.USER_WHITELIST
                self.config_list_prepare(self.user_whitelist)
            if config.USE_FILETYPE_BLACKLIST:
                self.filetype_blacklist = config.FILETYPE_BLACKLIST
                self.config_list_prepare(self.filetype_blacklist)
            if config.USE_FILETYPE_WHITELIST:
                self.filetype_whitelist = config.FILETYPE_WHITELIST
                self.config_list_prepare(self.filetype_whitelist)
            if config.USE_FILENAME_BLACKLIST:
                self.filename_blacklist = config.FILENAME_BLACKLIST
                self.config_list_prepare(self.filename_blacklist)
            if config.USE_FILENAME_WHITELIST:
                self.filename_whitelist = config.FILENAME_WHITELIST
                self.config_list_prepare(self.filename_whitelist)
            return False

    def config_list_prepare(self, config_list):
        """Add #roomname to filters if needed"""
        for idx, item in enumerate(config_list):
            if '#' not in str(item):
                item = item + '#{}'.format(self.room)
                config_list[idx] = item

    def file_check(self, file):
        """Check file against filters"""
        user_bool = True
        filename_bool = True
        filetype_bool = True

        if config.USE_USER_BLACKLIST:
            if str(file.uploader) + '#{}'.format(self.room) in self.user_blacklist:
                user_bool = False
        elif config.USE_USER_WHITELIST:
            user_bool = False
            if str(file.uploader) + '#{}'.format(self.room) in self.user_whitelist:
                user_bool = True

        if config.USE_FILENAME_BLACKLIST:
            for item in self.filename_blacklist:
                if item.lower().split('#')[0] in str(file.name).lower() and '#{}'.format(self.room) in item:
                    filename_bool = False
            for item in config.FILENAME_BLACKLIST_RE:
                if re.search(item, str(file.name), flags=re.IGNORECASE):
                    filename_bool = False
        elif config.USE_FILENAME_WHITELIST:
            filename_bool = False
            for item in self.filename_whitelist:
                if item.lower().split('#')[0] in str(file.name).lower() and '#{}'.format(self.room) in item:
                    filename_bool = True

        if config.USE_FILETYPE_BLACKLIST:
            if str(file.filetype) + '#{}'.format(self.room) in self.filetype_blacklist:
                filetype_bool = False
        elif config.USE_FILETYPE_WHITELIST:
            filetype_bool = False
            if str(file.filetype) + '#{}'.format(self.room) in self.filetype_whitelist:
                filetype_bool = True

        return user_bool and filename_bool and filetype_bool


    def create_room(self):
        """return a volapi room"""
        if self.password is None:
            r = Room(name=self.room, user=self.vola_user)
        elif self.password[0:4] == '#key':
            r = Room(name=self.room, user=self.vola_user, key=self.password[4:])
        else:
            r = Room(name=self.room, user=self.vola_user, password=self.password)
        if config.VOLAFILE_USER_PASSWORD != '':
            time.sleep(1)
            try:
                r.user.login(config.VOLAFILE_USER_PASSWORD)
                time.sleep(1)
            except RuntimeError:
                print(f'{bcolors.FAIL}###{bcolors.ENDC} LOGIN FAILED, PLEASE CHECK YOUR CONFIG BEFORE USING THE BOT')
                raise VolaDLException(kill=True)
            print('### USER LOGGED IN')
            cookie_jar = r.conn.cookies
            cookies_dict = {}
            for cookie in cookie_jar:
                if "volafile" in cookie.domain:
                    cookies_dict[cookie.name] = cookie.value
            self.cookies = {**self.cookies, **cookies_dict}
        return r

    def close(self):
        """only closes the current session, afterwards the downloader reconnects"""
        print("Closing current instance")
        self.listen.close()
        del self.listen
        return ""

    @staticmethod
    def id_generator(size=7, chars=string.ascii_uppercase + string.digits):
        """returns an id"""
        return ''.join(random.choice(chars) for _ in range(size))

    @staticmethod
    def prefix(msg):
        prefix = ''
        if msg.purple:
            prefix += "@"
        if msg.owner:
            prefix += "$"
        if msg.janitor:
            prefix += "~"
        if msg.green:
            prefix += "+"
        if msg.system:
            prefix += "%"
        return prefix


def parse_args():
    """Parses user arguments"""
    parser = argparse.ArgumentParser(
        description="volafile downloader",
        epilog="Pretty meh"
    )
    parser.add_argument('--room', '-r', type=str, required=True,
                        help='Room name, as in https://volafile.org/r/ROOMNAME')
    parser.add_argument('--passwd', '-p', type=str,
                        help='Room password to enter the room.')
    parser.add_argument('--downloader', '-d',
                        action=argparse.BooleanOptionalAction,
                        help='Do you want to download files')
    parser.add_argument('--logger', '-l',
                        action=argparse.BooleanOptionalAction,
                        help='Do you want to log the room')
    parser.add_argument('--folder', '-f', type=str,
                        help='Folder to place downloads in')
    parser.add_argument("-myjd", "--myjdownloader",
                        action=argparse.BooleanOptionalAction,
                        help="Use My.JDownloader to download links.")
    parser.add_argument("-jd", "--jdownloader",
                        action=argparse.BooleanOptionalAction,
                        help="Use JDownloader Folder Watch to download links.")
    parser.add_argument("--username", "-u", type=str,
                        help="Username to use in the room")
    return parser.parse_args()




if __name__ == "__main__":
    a = parse_args()
    lister = [a.room, a.passwd, a.downloader, a.logger, a.myjdownloader, a.jdownloader, a.folder]
    firstStart = True
    while True:
        print(f"{bcolors.OKGREEN}Creating VolaDL object{bcolors.ENDC}")
        try:
            v = VolaDL(*lister)

            if a.username:
                v.vola_user = a.username

            v.dl(firstStart=firstStart)
        except VolaDLException as err:
            if err.kill:
                break
        firstStart = False

