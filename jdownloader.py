from pathlib import Path
from theme import bcolors, print_file_info
import myjdapi

import config

config.JDOWNLOADER_FOLDERWATCH = Path(config.JDOWNLOADER_FOLDERWATCH)


class JDownloaderCore:
    def __init__(self, folderwatch=None, myjd=None):
        self.folderwatch = folderwatch
        self.myjd = myjd

    def setup(self):
        if not config.JDOWNLOADER_FOLDERWATCH.is_dir():
            print(f"{bcolors.FAIL}ERROR:{bcolors.ENDC} JDownloader Folder Watch directory is not found")
            raise Exception("JDownloader Folder Watch Directory is not found")
        if self.myjd:
            print(f"{bcolors.OKGREEN}Connecting to My.JDownloader{bcolors.ENDC}")
            self.jd_connect()

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
                        "packageName" : f.subfolder
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
        return True

    def jdownloader_single_file_download(self, f):
        if not self.folderwatch and not self.myjd:
            raise Exception("Neither folderwatch nor MYJDownloader are enabled")
        
        if self.folderwatch:
            return self.folderwatch_single_file_download(f)
        if self.myjd:
            return self.myjdownloader_single_file_download(f)

    def folderwatch_single_file_download(self, f) -> bool:
        """Sends a download to JDownloader Folder Watch"""
        file_name = Path(f.url).name + ".crawljob"
        file_size = '{0:.2f}'.format(f.size / 1048576)
        with open(config.JDOWNLOADER_FOLDERWATCH / file_name, "w") as fo:
            fo.write("->NEW ENTRY<-\n")
            fo.write("   text=" + f.url + "\n")
            fo.write("   packageName=" + str(f.subfolder) + "\n")
            fo.write("   autoStart=true\n") # Starts the download after a timeout. This works only if autoConfirm is set.
            fo.write("   autoConfirm=true\n") # Moves the links to the downloadlist (aftera timeout)
            fo.write(f"   comment=Room: {f.room.name} Uploader: {f.uploader} Size: {file_size} MB\n")
            fo.write("\n")
        return True
