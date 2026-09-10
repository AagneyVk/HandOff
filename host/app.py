"""Desktop entry point: python -m host.app (or packaged HandOff executable)."""
import asyncio
import contextlib
import logging
import multiprocessing
import os
from pathlib import Path
import socket
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from .runtime.security import Identity, TrustStore
from .runtime.server import Host

PORT = 47821


def backends():
    if sys.platform == 'win32':
        import ctypes
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        from .windows.window_catalog import list_windows
        from .windows.capture import identity
        from .windows.input_backend import tap, scroll
    elif sys.platform.startswith('linux'):
        from .linux.capture import list_windows, identity
        from .linux.input_backend import tap, scroll
    else:
        raise RuntimeError('HandOff supports Windows and Linux X11 hosts.')
    return list_windows, identity, tap, scroll


def local_addresses():
    values = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if not info[4][0].startswith('127.'): values.add(info[4][0])
    except OSError: pass
    return sorted(values)


class Desktop:
    def __init__(self, root):
        self.root = root
        directory = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'HandOff'
        self.identity = Identity(directory)
        self.trust = TrustStore(directory)
        self.host = Host(self.trust, *backends())
        self.loop = None
        self.server_task = None
        self.ready = False
        self.failure = None
        self.shutting_down = False
        self.rows = []
        self.invitation = ''
        root.title('HandOff')
        root.geometry('940x660')
        root.minsize(820, 600)
        root.configure(bg='#f4f8f6')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#f4f8f6')
        style.configure('TLabel', background='#f4f8f6', foreground='#172d27', font=('Segoe UI', 11))
        style.configure('TButton', font=('Segoe UI', 11), padding=10)
        style.configure('Accent.TButton', background='#006b58', foreground='white')
        style.configure('Treeview', font=('Segoe UI', 10), rowheight=36)
        main = ttk.Frame(root, padding=28); main.pack(fill='both', expand=True)
        ttk.Label(main, text='HANDOFF', foreground='#006b58', font=('Segoe UI', 11, 'bold')).pack(anchor='w')
        ttk.Label(main, text='Your app. Wherever you need it.', font=('Segoe UI', 24, 'bold')).pack(anchor='w', pady=(8, 8))
        ttk.Label(main, text='Choose an app to share, then scan the code with HandOff on your phone.').pack(anchor='w')
        body = ttk.Frame(main); body.pack(fill='both', expand=True, pady=22)
        left = ttk.Frame(body); left.pack(side='left', fill='both', expand=True, padx=(0, 24))
        ttk.Label(left, text='1   Choose your app', font=('Segoe UI', 13, 'bold')).pack(anchor='w', pady=(0, 12))
        self.table = ttk.Treeview(left, columns=('app',), show='tree headings', selectmode='browse', height=7)
        self.table.heading('#0', text='Window'); self.table.heading('app', text='App')
        self.table.column('#0', width=290); self.table.column('app', width=110)
        self.table.pack(fill='both', expand=True)
        controls = ttk.Frame(left); controls.pack(fill='x', pady=10)
        ttk.Button(controls, text='Refresh', command=self.refresh).pack(side='left')
        ttk.Button(controls, text='Share selected app', style='Accent.TButton', command=self.share).pack(side='right')
        ttk.Button(left, text='Stop sharing', command=self.host.stop).pack(fill='x')
        right = ttk.Frame(body); right.pack(side='right', fill='y')
        ttk.Label(right, text='2   Pair your phone', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        addresses = local_addresses()
        self.address = tk.StringVar(value=addresses[0] if addresses else '')
        ttk.Combobox(right, textvariable=self.address, values=addresses, width=27).pack(pady=8)
        self.qr = ttk.Label(right, text='Generate a pairing code\nwhen your phone is ready.', anchor='center')
        self.qr.pack(fill='both', expand=True)
        ttk.Button(right, text='New pairing code', command=self.pair).pack(fill='x', pady=6)
        ttk.Button(right, text='Copy pairing link', command=self.copy).pack(fill='x')
        self.pair_status = tk.StringVar(value='Codes expire after 5 minutes and work once.')
        ttk.Label(right, textvariable=self.pair_status, wraplength=270).pack(pady=8)
        self.status = tk.StringVar(value='Starting encrypted local host…')
        ttk.Label(main, textvariable=self.status, wraplength=850).pack(anchor='w', pady=6)
        ttk.Button(main, text='Remove all paired phones', command=self.revoke).pack(anchor='w')
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.thread = threading.Thread(target=self.network, daemon=True); self.thread.start()
        self.refresh()
        self.poll()

    def network(self):
        async def run():
            self.loop = asyncio.get_running_loop()
            self.server_task = asyncio.current_task()
            server = await asyncio.start_server(self.host.handle, '0.0.0.0', PORT, ssl=self.identity.context, ssl_handshake_timeout=5)
            self.ready = True
            try:
                async with server: await server.serve_forever()
            finally:
                for task in asyncio.all_tasks():
                    if task is not asyncio.current_task(): task.cancel()
        try: asyncio.run(run())
        except asyncio.CancelledError: pass
        except Exception as exc: self.failure = str(exc)

    def refresh(self):
        try:
            self.rows = self.host.catalog()
            for row in self.table.get_children(): self.table.delete(row)
            for row in self.rows: self.table.insert('', 'end', iid=row.id, text=row.title, values=(row.app,))
        except Exception as exc: messagebox.showerror('Could not list apps', str(exc))

    def share(self):
        selected = self.table.selection()
        if not selected: return messagebox.showinfo('Choose an app', 'Select a window from the list first.')
        try: self.host.approve(selected[0])
        except Exception as exc: messagebox.showerror('Could not share', str(exc))

    def pair(self):
        if not self.ready: return messagebox.showinfo('Host is starting', 'Wait for the host to be ready.')
        address = self.address.get().strip()
        try:
            socket.inet_pton(socket.AF_INET, address)
        except OSError:
            return messagebox.showerror('Computer address', 'Enter the LAN IPv4 address of this computer.')
        import qrcode
        from PIL import ImageTk
        self.invitation = self.trust.invitation(address, PORT, self.identity.fingerprint)
        image = qrcode.make(self.invitation).get_image()
        image = image.resize((270, 270))
        self.photo = ImageTk.PhotoImage(image)
        self.qr.configure(image=self.photo, text='')

    def copy(self):
        if not self.invitation or not self.trust.invite: self.pair()
        if self.invitation and self.trust.invite:
            self.root.clipboard_clear(); self.root.clipboard_append(self.invitation)

    def revoke(self):
        if messagebox.askyesno('Remove paired phones', 'Disconnect all phones and require pairing again?'):
            self.host.stop(); self.trust.revoke_all()

    def poll(self):
        if self.shutting_down: return
        if self.failure:
            self.status.set('Host could not start: ' + self.failure)
        elif self.ready:
            self.status.set(self.host.status + f'   •   {len(self.trust.devices)} paired phone(s)')
        import time
        remaining = max(0, int(self.trust.expires - time.monotonic())) if self.trust.invite else 0
        if self.invitation and not remaining:
            self.qr.configure(image='', text='Code used or expired.\nGenerate a new code to pair.')
            self.invitation = ''
        self.pair_status.set(f'Code expires in {remaining}s' if remaining else 'Codes expire after 5 minutes and work once.')
        self.root.after(500, self.poll)

    def close(self):
        self.shutting_down = True
        self.host.stop()
        if self.loop and self.server_task:
            with contextlib.suppress(RuntimeError): self.loop.call_soon_threadsafe(self.server_task.cancel)
        self.thread.join(timeout=2)
        self.root.destroy()


def main():
    multiprocessing.freeze_support()
    logging.basicConfig(level=logging.INFO)
    if sys.platform == 'win32':
        import ctypes
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    root = tk.Tk()
    try: Desktop(root)
    except Exception as exc:
        messagebox.showerror('HandOff could not start', str(exc)); root.destroy(); return
    root.mainloop()


if __name__ == '__main__': main()
