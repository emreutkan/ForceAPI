import logging
import os
import sys
import time
import platform
from logging.handlers import RotatingFileHandler


class WindowsSafeRotatingFileHandler(RotatingFileHandler):
    """
    A RotatingFileHandler that handles Windows file locking issues gracefully.
    On Windows, if a file is open, it cannot be renamed. This handler catches
    PermissionError during rollover and continues logging without rotation.
    """
    
    def doRollover(self):
        """
        Do a rollover, as described in __init__().
        On Windows, catch PermissionError if file is locked.
        """
        # Close the stream first
        if self.stream:
            self.stream.close()
            self.stream = None
        
        # On Windows, give the OS a moment to release the file handle
        if platform.system() == 'Windows':
            time.sleep(0.1)
        
        if self.backupCount > 0:
            for i in range(self.backupCount - 1, 0, -1):
                sfn = "%s.%d" % (self.baseFilename, i)
                dfn = "%s.%d" % (self.baseFilename, i + 1)
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        try:
                            os.remove(dfn)
                        except (OSError, PermissionError):
                            pass  # Ignore if can't remove
                    try:
                        os.rename(sfn, dfn)
                    except (OSError, PermissionError):
                        # On Windows, if file is locked, skip rotation silently
                        # Rotation will be attempted again on next rollover
                        break
            
            dfn = self.baseFilename + ".1"
            if os.path.exists(self.baseFilename):
                try:
                    os.rename(self.baseFilename, dfn)
                except (OSError, PermissionError):
                    # On Windows, if file is locked, skip rotation silently
                    # The file will continue to grow, rotation will be attempted again later
                    pass
        
        if not self.delay:
            self.stream = self._open()

