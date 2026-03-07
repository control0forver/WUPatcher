#!/usr/bin/python3

# For 3.8+ only!
import os
from pathlib import Path
os.chdir(Path(__file__).parent.absolute()) # Win11 is x64 only!
import typing
import sys
import shutil
import ctypes
import asyncio
import time
from queue import Queue
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

SYSROOT = Path(os.environ['WINDIR'])
SYSWIN32 = SYSROOT / "System32"
WIN_SOFTWARE_DISTRIBUTION_DOWNLOAD = SYSROOT / "SoftwareDistribution" / "Download"

g_target_dirs_queue: Queue[Path] = Queue()
g_cache_completed_update: typing.Set[str] = set()

def get_path_id(path: Path):
    return f"{path.name}_{os.path.getmtime(path)}"

def do_hook(targetDir):
    targetDir = Path(targetDir)
    targetDLL = (targetDir / "VERSION.dll")
    if targetDLL.exists():
        targetDLL.unlink()
    targetDLL.symlink_to("./AppraiserPatcher.dll")
    #shutil.copy("./AppraiserPatcher.dll", targetDLL)
    oriDll = (targetDir / "VERSION_.dll")
    if oriDll.exists():
        oriDll.unlink()
    #oriDll.symlink_to(SYSWIN32 / "VERSION.dll")
    shutil.copy(SYSWIN32 / "VERSION.dll", oriDll)

async def polling_async(interval = 5.0):
    import msvcrt # for kbhit, getch
    
    # print("[Z - Swithing polling interval between 0.01s, 0.1s, 1s and 15s]")
    while True:
        try:
            sleep_time = interval
            nCount = 0
            
            _put_backs = [] # retries
            while not g_target_dirs_queue.empty():
                entry = g_target_dirs_queue.get()
                _put_backs.append(entry)
                did = get_path_id(entry)
                if did in g_cache_completed_update:
                    _put_backs.pop()
                    continue
                # if not entry.is_dir():
                #     continue
                if not (entry / 'WindowsUpdateBox.exe').exists():
                    continue # retry later
                #if (entry / 'VERSION.dll').exists():
                #    continue # retry later
                
                print(f"[+ {datetime.now()}] Hooking {entry}")
                try:
                    do_hook(entry)
                    
                    print(f"[+ {datetime.now()}] Hooked {entry}")
                    _put_backs.pop()
                    g_cache_completed_update.add(did)
                    nCount += 1
                except Exception as e:
                    print(f"[! {datetime.now()}] Failed to hook {entry}")
                    import traceback; traceback.print_exc()
            for entry in _put_backs:
                # Queued for retry
                print(f"[!] {entry} will be retried later")
                g_target_dirs_queue.put(entry)
            
            if (nCount):
                last_info_display = None
                print(f"[+] Done {nCount} hook{'s' if nCount > 1 else ''}")
            else:
                last_info_display = "No update"
                print("No update :)", end='', flush=True)
                DISPLAY_TIME = min(1.2, sleep_time*0.2)
                if DISPLAY_TIME > 0.0:
                    try:
                        await asyncio.sleep(DISPLAY_TIME)
                    except asyncio.CancelledError: raise KeyboardInterrupt()
                    finally: sleep_time -= DISPLAY_TIME
        except Exception as e:
            import traceback; traceback.print_exc()
            print(e)
            
        if sleep_time > 0.0:
            if sleep_time >= 1.0:
                while msvcrt.kbhit(): msvcrt.getch() # clear input buffer
                while sleep_time > 0.0:
                    f1 = sleep_time > 10.0
                    f2 = sleep_time > 3.0
                    
                    v1 = "\r\033[J"
                    if last_info_display:
                        v1 += f"({last_info_display}) "
                        
                    if f1: # > 10s
                        v1 += f"Waiting for {sleep_time:.1f}s"
                    elif f2: # > 3s
                        v1 += f"Waiting for {sleep_time:.2f}s"
                    else:
                        v1 += f"Waiting for {sleep_time:.3f}s"
                    v1 += f" [Press Space to Skip]"
                    
                    print(v1, end="", flush=True)
                    bIsUserCancel = False
                    try:
                        PERIOD = \
                            1.0/25 # 25fps
                            # 1.0/20 # 20fps
                            # 1.0/15 # 15fps
                            # ((sleep_time / sleep_time) / 3) / (2*3)
                        start = time.time()
                        await asyncio.sleep(PERIOD)
                        sleep_time -= time.time() - start
                        if msvcrt.kbhit() and msvcrt.getch() == b' ':
                            bIsUserCancel = True
                            raise asyncio.CancelledError()
                    except asyncio.CancelledError:
                        print()
                        if not bIsUserCancel:
                            raise KeyboardInterrupt()
                        print("[+] Skipped waiting")
                        break
            else:
                await asyncio.sleep(sleep_time)
        print('\r\033[J', end="")

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def rerun_as_admin():
    try:
        script = os.path.abspath(sys.argv[0])
        params = ' '.join(sys.argv[1:])
        
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{script}" {params}',
            None,
            1
        )
        return True
    except Exception as e:
        print(f"Running as admin failed: {e}")
        return False

class Main:
    def __init__(self):
        self.observer = Observer()
        
    async def run_async(self):
        print("V3.2 @_@")
        
        if not is_admin():
            if rerun_as_admin():
                print("Re-running as admin, this program will exit now")
                return
            else:
                print("[!] No admin privilege, we may fail to modify downloaded updates")
        
        # Add initial dirs
        for dir_path in Path(WIN_SOFTWARE_DISTRIBUTION_DOWNLOAD).iterdir():
            g_target_dirs_queue.put(dir_path)

        class NewDirectoryHandler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    print(f"[+] {datetime.now()} New directory {event.src_path}")
                    g_target_dirs_queue.put(Path(event.src_path))
        
        self.observer.schedule(NewDirectoryHandler(), path=WIN_SOFTWARE_DISTRIBUTION_DOWNLOAD, recursive=False)
        print(f"[+] Watching for new directories in {WIN_SOFTWARE_DISTRIBUTION_DOWNLOAD}")
        self.observer.start()
        
        if not (SYSWIN32 / "VERSION_.dll").exists():
            #(SYSWIN32 / "VERSION_.dll").symlink_to(SYSWIN32 / "VERSION.dll")
            shutil.copy(SYSWIN32 / "VERSION.dll", SYSWIN32 / "VERSION_.dll")
        
        await polling_async()
    
    def dispose(self):
        self.observer.stop()
        self.observer.join()
    
if __name__ == "__main__":
    try:
        main = Main()
        asyncio.run(main.run_async())
    except KeyboardInterrupt:
        print("[+] Exit")
        main.dispose()
        os._exit(0)