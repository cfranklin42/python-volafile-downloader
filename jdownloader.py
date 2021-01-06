from pathlib import Path
from theme import bcolors, print_file_info
import myjdapi

import config
import unified_duplicate_checker

config.JDOWNLOADER_FOLDERWATCH = Path(config.JDOWNLOADER_FOLDERWATCH)
config.LOG_PATH = Path(config.LOG_PATH)

class JDownloaderCore:
    def __init__(self, room, subfolder, folderwatch=None, myjd=None):
        self.room = room
        self.subfolder = subfolder
        self.folderwatch = folderwatch
        self.myjd = myjd
        self.counter = 1
        # Load previously downloaded files so we don't download them again
        self.jd_logpath = config.LOG_PATH / ("[" + self.room + "] downloaded.txt")
        self.jd_downloaded_urls = self.get_logged_urls()

    def setup(self) -> bool:
        """ Returns True if there was an error """
        if not config.JDOWNLOADER_FOLDERWATCH.is_dir():
            print(f"{bcolors.FAIL}ERROR:{bcolors.ENDC} JDownloader Folder Watch directory is not found")
            return True
        if self.myjd:
            print(f"{bcolors.OKGREEN}Connecting to My.JDownloader{bcolors.ENDC}")
            self.jd_connect()
        return False

    def log_url(self, url: str) -> None:
        """Log that a url was downloaded so we don't download it again"""
        with self.jd_logpath.open("a", encoding="utf-8") as f:
            f.write(url + '\n')

    def log_file(self, f) -> None:
        unified_duplicate_checker.log_file(Path(f.url).name, f.size)
        self.log_url(f.url)

    def get_logged_urls(self):
        """Retrieve the room's logged urls so we don't download them again"""
        if self.jd_logpath.is_file():
            with self.jd_logpath.open("r", encoding="utf-8") as f:
                return list(set(f.read().splitlines()))
        return []

    def jd_connect(self):
        """ Connect to MyJDownloader using myjdapi and the login info in the config """
        self.jd = myjdapi.Myjdapi()
        self.jd.set_app_key("VolafileDownloader")
        self.jd.connect(config.jdownloader_username, config.jdownloader_password)
        self.jd.update_devices()
        self.jdDevice = self.jd.get_device(config.jdownloader_devicename)

    def jd_reconnect(self):
        try:
            self.jd.reconnect()
        except myjdapi.myjdapi.MYJDException:
            self.jd_connect()

    def myjdownloader_single_file_download(self, f) -> bool:
        """ Sends a download to My.JDownloader """
        file_name = Path(f.url).name
        res = None # MyJDownloader API response
        for retries in range(3): # Try 3 times
            if retries > 0:
                print(f"{bcolors.WARNING}Reattempt number {retries}...{bcolors.ENDC}")
            try:
                res = self.jdDevice.linkgrabber.add_links([{
                        "autostart" : True,
                        "links": f.url,
                        "packageName" : self.subfolder
                    }])
            except myjdapi.myjdapi.MYJDException:
                # If there is an error, first try to reconnect()
                # If that fails, restart MyJDAPI and try to connect() again
                self.jd_reconnect()
            else:
                break
        if res is None:
            print(f"{bcolors.FAIL}Failed to send link to My.JDownloader:{bcolors.ENDC} {file_name}")
            return False
        # Add the url to the logged urls file
        self.log_file(f)
        print(f'{bcolors.OKGREEN}[{bcolors.ENDC}{self.counter}{bcolors.OKGREEN}] Sent to My.JDownloader{bcolors.ENDC}')
        self.counter += 1
        return True

    def jdownloader_single_file_download(self, f, quiet=False):
        """ If quiet is True, only print file info of new downloads """
        already_downloaded = f.url in self.jd_downloaded_urls
        if not quiet or not already_downloaded:
            print_file_info(f)
        if not already_downloaded and unified_duplicate_checker.is_duplicate_file(f):
            print(f'{bcolors.FAIL}  Unified Duplicate Checker: File is a duplicate{bcolors.ENDC}')
            already_downloaded = True
        if already_downloaded:
            return True
        if self.folderwatch:
            return self.folderwatch_single_file_download(f)
        if self.myjd:
            return self.myjdownloader_single_file_download(f)

    def folderwatch_single_file_download(self, f) -> bool:
        """Sends a download to JDownloader Folder Watch"""
        file_name = Path(f.url).name + ".crawljob"
        file_size = '{0:.2f}'.format(f.size / 1048576)
        subfolder = getattr(f, 'subfolder', self.subfolder)
        with open(config.JDOWNLOADER_FOLDERWATCH / file_name, "w") as fo:
            fo.write("->NEW ENTRY<-\n")
            fo.write("   text=" + f.url + "\n")
            fo.write("   packageName=" + str(subfolder) + "\n")
            fo.write("   autoStart=true\n") # Starts the download after a timeout. This works only if autoConfirm is set.
            fo.write("   autoConfirm=true\n") # Moves the links to the downloadlist (aftera timeout)
            fo.write(f"   comment=Room: {f.room.name} Uploader: {f.uploader} Size: {file_size} MB\n")
            fo.write("\n")
        # Add the url to the logged urls file
        self.log_file(f)
        print(f'  {bcolors.OKGREEN}[{bcolors.ENDC}{self.counter}{bcolors.OKGREEN}] Sent to JDownloader{bcolors.ENDC}')
        self.counter += 1
        return True

