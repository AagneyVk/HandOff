"""Desktop entry point: python -m host.app (or packaged HandOff executable)."""
import asyncio
import contextlib
import logging
import multiprocessing
import os
import queue
from pathlib import Path
import socket
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from .runtime.security import Identity, TrustStore
from .runtime.server import Host
from .runtime.phone_view import PhonePresenter

PORT = 47821


def backends():
    if sys.platform == 'win32':
        import ctypes
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        from .windows.window_catalog import list_windows
        from .windows.capture import identity
        from .windows.input_backend import tap, scroll, drag, text, key
    elif sys.platform.startswith('linux'):
        from .linux.capture import list_windows, identity
        from .linux.input_backend import tap, scroll, drag
        text = key = None
    else:
        raise RuntimeError('HandOff supports Windows and Linux X11 hosts.')
    return list_windows, identity, tap, scroll, drag, text, key


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
        self.update_queue = queue.Queue()
        self.update_release = None
        self.update_installer = None
        self.update_busy = False
        self.update_directory = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "HandOff" / "updates"
        directory = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'HandOff'
        self.identity = Identity(directory)
        self.trust = TrustStore(directory)
        catalog, identify, tap, scroll, drag, text, key = backends()
        self.host = Host(self.trust, catalog, identify, tap, scroll, drag=drag, text=text, key=key)
        self.phone = PhonePresenter(root, self.phone_control)
        self.host.phone_presenter = self.phone
        self.loop = None
        self.server_task = None
        self.ready = False
        self.failure = None
        self.shutting_down = False
        self.rows = []
        self.invitation = ''
        root.title('HandOff')
        root.geometry('940x700')
        root.minsize(820, 700)
        root.configure(bg='#f4f8f6')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#f4f8f6')
        style.configure('TLabel', background='#f4f8f6', foreground='#172d27', font=('Segoe UI', 11))
        style.configure('TButton', font=('Segoe UI', 11), padding=8, background='#e3eee8', foreground='#173b30', borderwidth=0)
        style.configure('Accent.TButton', background='#006b58', foreground='white')
        style.configure('Treeview', font=('Segoe UI', 10), rowheight=36)
        main = ttk.Frame(root, padding=28); main.pack(fill='both', expand=True)
        ttk.Label(main, text='HANDOFF', foreground='#006b58', font=('Segoe UI', 11, 'bold')).pack(anchor='w')
        ttk.Label(main, text='Your app. Wherever you need it.', font=('Segoe UI', 24, 'bold')).pack(anchor='w', pady=(8, 8))
        ttk.Label(main, text='Choose one app or an entire display, then scan the code with HandOff on your phone.').pack(anchor='w')
        body = ttk.Frame(main); body.pack(fill='both', expand=True, pady=22)
        left = ttk.Frame(body); left.pack(side='left', fill='both', expand=True, padx=(0, 24))
        ttk.Label(left, text='1   Choose an app or display', font=('Segoe UI', 13, 'bold')).pack(anchor='w', pady=(0, 12))
        self.table = ttk.Treeview(left, columns=('app',), show='tree headings', selectmode='browse', height=3)
        self.table.heading('#0', text='Window'); self.table.heading('app', text='App')
        self.table.column('#0', width=290); self.table.column('app', width=110)
        self.table.pack(fill='both', expand=True)
        controls = ttk.Frame(left); controls.pack(fill='x', pady=10)
        ttk.Button(controls, text='Refresh', command=self.refresh).pack(side='left')
        ttk.Button(controls, text='Share selected', style='Accent.TButton', command=self.share).pack(side='right')
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
        self.audio_choice = tk.BooleanVar(value=False)
        ttk.Checkbutton(main, text='Share computer audio (all apps, never microphone)', variable=self.audio_choice,
                        command=lambda: setattr(self.host, 'audio_enabled', self.audio_choice.get())).pack(anchor='w')
        self.status = tk.StringVar(value='Starting encrypted local host…')
        ttk.Label(main, textvariable=self.status, wraplength=850).pack(anchor='w', pady=6)
        ttk.Button(main, text='Remove all paired phones', command=self.revoke).pack(anchor='w')
        from .version import VERSION
        updates = ttk.Frame(main); updates.pack(fill='x', pady=6)
        self.update_status = tk.StringVar(value=f'HandOff {VERSION}')
        ttk.Label(updates, textvariable=self.update_status).pack(side='left')
        self.update_button = ttk.Button(updates, text='Check for updates', command=self.update)
        self.update_button.pack(side='right')
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.thread = threading.Thread(target=self.network, daemon=True); self.thread.start()
        self.refresh()
        self.poll()

    def update(self):
        from .runtime import updates
        if self.update_busy: return
        if self.update_installer:
            if not messagebox.askyesno('Install update', 'HandOff will close. Complete the installer, then select Open HandOff. Your pairing and settings will be kept.'): return
            try: updates.install(self.update_installer)
            except Exception as exc: return messagebox.showerror('Update', str(exc))
            self.close(); return
        if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
            return messagebox.showinfo('Source installation', 'Update this source checkout with git pull. The Windows installer includes app updates.')
        self.update_busy = True
        self.update_button.configure(state='disabled')
        self.update_status.set('Downloading and verifying…' if self.update_release else 'Checking GitHub Releases…')
        release = self.update_release
        def work():
            try:
                result = updates.download(release, self.update_directory) if release else updates.check()
                self.update_queue.put(('download' if release else 'check', result))
            except Exception as exc: self.update_queue.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

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
        if not selected: return messagebox.showinfo('Choose what to share', 'Select an app window or entire display first.')
        target = next((row for row in self.rows if row.id == selected[0]), None)
        if target and target.kind == 'display' and not messagebox.askyesno(
                'Share entire display?',
                'Everything visible on this display can appear on your phone, and the phone can control it. Continue?'):
            return
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
        image = qrcode.make(self.invitation, box_size=3, border=4, error_correction=qrcode.constants.ERROR_CORRECT_L).get_image()
        self.photo = ImageTk.PhotoImage(image)
        self.qr.configure(image=self.photo, text='')

    def copy(self):
        if not self.invitation or not self.trust.invite: self.pair()
        if self.invitation and self.trust.invite:
            self.root.clipboard_clear(); self.root.clipboard_append(self.invitation)

    def revoke(self):
        if messagebox.askyesno('Remove paired phones', 'Disconnect all phones and require pairing again?'):
            self.host.stop(); self.trust.revoke_all()

    def phone_control(self, owner, type_, **payload):
        if not self.loop or owner is not self.host.phone_owner or not owner.source_session: return
        if type_ != 'phone.stop' and not owner.source_controls: return
        payload['session'] = owner.source_session
        asyncio.run_coroutine_threadsafe(owner.send(type_, **payload), self.loop)

    def poll(self):
        if self.shutting_down: return
        try:
            kind, value = self.update_queue.get_nowait()
            self.update_busy = False; self.update_button.configure(state='normal')
            if kind == 'download':
                self.update_installer = value
                self.update_status.set('Update verified and ready')
                self.update_button.configure(text='Install update')
            elif kind == 'check':
                self.update_release = value
                self.update_status.set(f"Update available: {value['tag']}" if value else 'No newer installer is published')
                self.update_button.configure(text='Download update' if value else 'Check for updates')
            else: self.update_status.set('Update failed: ' + value)
        except queue.Empty: pass
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
        self.phone.stop()
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
