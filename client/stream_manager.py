# -*- coding: utf-8 -*-
# ==============================================================================
#   HLSManager Desktop Client (Stream Manager GUI)
# ==============================================================================
# Graphical interface for managing video streams and scheduling on the server.
# Built with Tkinter and Paramiko for SSH connectivity.
#
# Author: Mohammad Akbarpour
# Version: 1.0 (Final)
# ==============================================================================


import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import paramiko
import os
import threading
from tkcalendar import DateEntry
from datetime import datetime
import pytz
import re
import queue
from ttkthemes import ThemedTk

# --- Paths on the server ---
REMOTE_VIDEO_DIR = "/var/videos"
REMOTE_PLAYER_HTML_PATH = "/var/www/player/index.html"
REMOTE_PLAYER_TEMPLATE_PATH = "/var/www/player_template.html"
REMOTE_IDLE_TEMPLATE_PATH = "/var/www/idle_template.html"
FFMPEG_PATH = "/usr/bin/ffmpeg"

# --- Default HTML templates ---
DEFAULT_PLAYER_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>پخش زنده آنلاین</title>
    <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #121212;
            --text-color: #e0e0e0;
            --card-bg: #1e1e1e;
            --header-color: #ffffff;
            --shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
        }
        body {
            margin: 0;
            font-family: 'Vazirmatn', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .container {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2vw 4vw;
            max-width: 1200px;
            width: 100%;
            margin: 0 auto;
        }
        .class-info {
            width: 100%;
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: var(--card-bg);
            border-radius: 15px;
            box-shadow: var(--shadow);
        }
        .class-info h1 {
            font-size: clamp(1.5rem, 4vw, 2.5rem);
            margin: 0 0 10px;
            color: var(--header-color);
        }
        .class-info .description {
            font-size: clamp(0.9rem, 2vw, 1.1rem);
            line-height: 1.7;
            max-width: 800px;
            margin: 0 auto;
            opacity: 0.8;
        }
        .video-wrapper {
            position: relative;
            width: 100%;
            max-width: 1000px;
            aspect-ratio: 16/9;
            background: #000;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: var(--shadow);
        }
        .video-js {
            width: 100%;
            height: 100%;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="class-info">
            <h1>پخش زنده آنلاین</h1>
            <div class="description">به پخش زنده خوش آمدید. استریم به زودی آغاز خواهد شد.</div>
        </div>
        <div class="video-wrapper">
            <video id="live-video" class="video-js vjs-big-play-centered" controls playsinline></video>
        </div>
    </div>

    <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
    <script>
        var player = videojs("live-video", {
            liveui: true,
            fluid: true,
            autoplay: true,
            muted: true
        });

        player.src({
            src: "/hls/stream.m3u8",
            type: "application/x-mpegURL"
        });

        player.ready(function() {
            var playPromise = this.play();
            if (playPromise !== undefined) {
                playPromise.then(() => {
                    this.muted(false);
                    this.volume(1.0);
                }).catch(error => {
                    console.log("پخش خودکار توسط مرورگر ممکن نشد. کاربر باید برای شروع روی دکمه پلی کلیک کند.");
                });
            }
        });
    </script>
</body>
</html>
"""
DEFAULT_IDLE_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>آفلاین</title>
    <style>
        body, html { margin: 0; padding: 0; height: 100%; display: flex; justify-content: center; align-items: center; background-color: #1f2937; color: #f9fafb; font-family: sans-serif; text-align: center; }
        .container { max-width: 600px; padding: 2rem; }
        h1 { font-size: 2.5rem; margin-bottom: 1rem; }
        p { font-size: 1.2rem; color: #d1d5db; }
    </style>
</head>
<body>
    <div class="container">
        <h1>پخش زنده‌ای وجود ندارد</h1>
        <p>لطفاً بعداً مراجعه کنید.</p>
    </div>
</body>
</html>
"""


class LoginWindow(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.parent = parent
        self.callback = callback
        self.title("Login to Server")
        self.geometry("350x230")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding="20")
        frame.pack(expand=True, fill="both")
        ttk.Label(frame, text="Server IP:").grid(row=0, column=0, sticky="w", pady=5)
        self.ip_entry = ttk.Entry(frame)
        self.ip_entry.grid(row=0, column=1, sticky="ew")
        ttk.Label(frame, text="Port:").grid(row=1, column=0, sticky="w", pady=5)
        self.port_entry = ttk.Entry(frame)
        self.port_entry.grid(row=1, column=1, sticky="ew")
        self.port_entry.insert(0, "22")
        ttk.Label(frame, text="Username:").grid(row=2, column=0, sticky="w", pady=5)
        self.user_entry = ttk.Entry(frame)
        self.user_entry.grid(row=2, column=1, sticky="ew")
        self.user_entry.insert(0, "root")
        ttk.Label(frame, text="Password:").grid(row=3, column=0, sticky="w", pady=5)
        self.pass_entry = ttk.Entry(frame, show="*")
        self.pass_entry.grid(row=3, column=1, sticky="ew")
        connect_btn = ttk.Button(frame, text="Connect", command=self.attempt_login)
        connect_btn.grid(row=4, column=0, columnspan=2, pady=15)
        self.ip_entry.focus_set()
        self.bind("<Return>", lambda event: self.attempt_login())
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        self.parent.destroy()

    def attempt_login(self):
        ip = self.ip_entry.get().strip()
        port_str = self.port_entry.get().strip()
        user = self.user_entry.get().strip()
        password = self.pass_entry.get()
        if not all([ip, port_str, user]):
            messagebox.showerror("Error", "IP, Port, and Username are required.", parent=self)
            return
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Error", "Port must be a number.", parent=self)
            return
        self.destroy()
        self.callback(ip, port, user, password)


class App:
    def __init__(self, root):
        self.root = root
        self.root.set_theme("arc")
        self.root.title("Stream Manager Pro")
        self.root.geometry("800x750")

        self.ssh_client = None
        self.local_timezone = pytz.timezone('Asia/Tehran')
        self.ui_queue = queue.Queue()
        self.last_uploaded_path = None
        self.is_stream_live = False

        self.placeholder_label = ttk.Label(self.root, text="Please wait, loading login screen...", font=("", 14))
        self.placeholder_label.pack(expand=True)
        self.root.after(100, self.open_login_window)
        self.process_ui_queue()

    def open_login_window(self):
        LoginWindow(self.root, self.handle_login_attempt)

    def handle_login_attempt(self, ip, port, user, password):
        self.placeholder_label.config(text=f"Connecting to {ip}...")
        self.root.update_idletasks()

        # The connection is handled in a separate thread to prevent the program from freezing
        threading.Thread(target=self._try_connect, args=(ip, port, user, password), daemon=True).start()

    def _try_connect(self, ip, port, user, password):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, port=port, username=user, password=password, timeout=10)

            self.ssh_client = ssh
            self.ui_queue.put(self.on_login_success)
        except Exception as e:
            self.ui_queue.put(lambda: self.on_login_failure(e))

    def on_login_success(self):
        self.placeholder_label.destroy()
        self.build_main_ui()

    def on_login_failure(self, error):
        messagebox.showerror("Connection Failed", str(error))
        self.placeholder_label.config(text="Login failed. Please try again.")
        self.root.after(100, self.open_login_window)

    def build_main_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(pady=10, padx=10, fill="both", expand=True)
        self.create_main_tab()
        self.create_queue_tab()
        self.create_settings_tab()
        self.status_bar = ttk.Label(self.root, text="  Connection successful. Ready.", anchor=tk.W, relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.run_in_thread(self.check_stream_status)
        self.auto_refresh_queue()

    def update_status_bar(self, text):
        self.ui_queue.put(lambda: self.status_bar.config(text=f"  {text}"))

    def create_main_tab(self):
        main_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(main_tab, text='  ▶️ Main Control & Scheduling  ')
        status_frame = ttk.LabelFrame(main_tab, text="Status & Control", padding="10")
        status_frame.pack(fill=tk.X, pady=5)
        self.status_label = ttk.Label(status_frame, text="Connecting...", font=("", 12))
        self.status_label.pack(pady=5)
        control_buttons_frame = ttk.Frame(status_frame)
        control_buttons_frame.pack(pady=5, fill=tk.X)
        self.check_btn = ttk.Button(control_buttons_frame, text="🔄 Check Status",
                                    command=lambda: self.run_in_thread(self.check_stream_status))
        self.check_btn.pack(side=tk.LEFT, expand=True, padx=5)
        self.stop_btn = ttk.Button(control_buttons_frame, text="⏹️ Hard Stop Stream", state=tk.DISABLED,
                                   command=self.stop_stream)
        self.stop_btn.pack(side=tk.LEFT, expand=True, padx=5)
        upload_frame = ttk.LabelFrame(main_tab, text="1. Select & Upload Video", padding="10")
        upload_frame.pack(fill=tk.X, pady=10)
        self.file_path_label = ttk.Label(upload_frame, text="No file selected.")
        self.file_path_label.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.upload_btn = ttk.Button(upload_frame, text="📂 Browse & Upload",
                                     command=lambda: self.run_in_thread(self.browse_and_upload))
        self.upload_btn.pack(side=tk.RIGHT)
        self.upload_progress = ttk.Progressbar(main_tab, orient="horizontal", length=100, mode="determinate")
        self.upload_progress.pack(fill=tk.X, padx=10, pady=(0, 10))
        action_frame = ttk.LabelFrame(main_tab, text="2. Choose Action (for last uploaded video)", padding="10")
        action_frame.pack(fill=tk.X, pady=5)
        self.start_now_btn = ttk.Button(action_frame, text="🚀 Start Streaming NOW", state=tk.DISABLED,
                                        command=lambda: self.run_in_thread(self.start_stream_now))
        self.start_now_btn.pack(pady=5, fill=tk.X)
        schedule_subframe = ttk.Frame(action_frame)
        schedule_subframe.pack(fill=tk.X, pady=10)
        time_frame = ttk.Frame(schedule_subframe)
        time_frame.pack(fill=tk.X)
        tehran_now = datetime.now(self.local_timezone)
        self.minute_spinbox = ttk.Spinbox(time_frame, from_=0, to=59, width=3, format="%02.0f")
        self.minute_spinbox.set(f"{tehran_now.minute:02}")
        self.minute_spinbox.pack(side=tk.RIGHT)
        ttk.Label(time_frame, text=":").pack(side=tk.RIGHT)
        self.hour_spinbox = ttk.Spinbox(time_frame, from_=0, to=23, width=3, format="%02.0f")
        self.hour_spinbox.set(f"{tehran_now.hour:02}")
        self.hour_spinbox.pack(side=tk.RIGHT)
        ttk.Label(time_frame, text="Time (Tehran):").pack(side=tk.RIGHT, padx=(0, 5))
        self.date_entry = DateEntry(time_frame, width=12, background='darkblue', foreground='white', borderwidth=2,
                                    date_pattern='yyyy-mm-dd')
        self.date_entry.set_date(tehran_now)
        self.date_entry.pack(side=tk.RIGHT, padx=10)
        self.schedule_btn = ttk.Button(schedule_subframe, text="⏰ Schedule for Later", state=tk.DISABLED,
                                       command=lambda: self.run_in_thread(self.schedule_stream_later))
        self.schedule_btn.pack(pady=5, fill=tk.X)

    def create_queue_tab(self):
        queue_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(queue_tab, text='  🕒 Schedule Queue  ')
        queue_frame = ttk.LabelFrame(queue_tab, text="Scheduled Stream Queue", padding="10")
        queue_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        cols = ('job_id', 'server_time', 'tehran_time', 'video')
        self.queue_tree = ttk.Treeview(queue_frame, columns=cols, show='headings')
        self.queue_tree.heading('job_id', text='Job ID')
        self.queue_tree.heading('server_time', text='Scheduled Time (Server)')
        self.queue_tree.heading('tehran_time', text='Scheduled Time (Tehran)')
        self.queue_tree.heading('video', text='Video File')
        self.queue_tree.column('job_id', width=60, anchor=tk.CENTER)
        self.queue_tree.column('server_time', width=200)
        self.queue_tree.column('tehran_time', width=200)
        self.queue_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(queue_frame, orient="vertical", command=self.queue_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.queue_tree.configure(yscrollcommand=scrollbar.set)
        queue_buttons_frame = ttk.Frame(queue_tab)
        queue_buttons_frame.pack(fill=tk.X, pady=5)
        ttk.Button(queue_buttons_frame, text="🔄 Refresh Now",
                   command=lambda: self.run_in_thread(self.refresh_queue)).pack(side=tk.RIGHT)
        ttk.Button(queue_buttons_frame, text="🗑️ Cancel Selected Job", command=self.cancel_selected_job).pack(
            side=tk.RIGHT, padx=10)

    def create_settings_tab(self):
        settings_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(settings_tab, text='  ⚙️ Page Settings  ')
        idle_frame = ttk.LabelFrame(settings_tab, text="Set Custom Idle/Offline Page", padding="10")
        idle_frame.pack(fill=tk.X, pady=10)
        self.idle_page_label = ttk.Label(idle_frame, text="No custom idle page set.")
        self.idle_page_label.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        ttk.Button(idle_frame, text="📂 Browse...", command=lambda: self.browse_for_template('idle')).pack(
            side=tk.RIGHT, padx=5)
        ttk.Button(idle_frame, text="💾 Set as Idle Page",
                   command=lambda: self.run_in_thread(self.set_template_page, 'idle')).pack(side=tk.RIGHT)
        player_frame = ttk.LabelFrame(settings_tab, text="Set Custom Player Page", padding="10")
        player_frame.pack(fill=tk.X, pady=10)
        self.player_page_label = ttk.Label(player_frame, text="No custom player page set.")
        self.player_page_label.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        ttk.Button(player_frame, text="📂 Browse...", command=lambda: self.browse_for_template('player')).pack(
            side=tk.RIGHT, padx=5)
        ttk.Button(player_frame, text="💾 Set as Player Page",
                   command=lambda: self.run_in_thread(self.set_template_page, 'player')).pack(side=tk.RIGHT)

    def process_ui_queue(self):
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(100, self.process_ui_queue)

    def run_in_thread(self, target_func, *args):
        threading.Thread(target=target_func, args=args, daemon=True).start()

    def execute_command(self, command):
        try:
            if not self.ssh_client or not self.ssh_client.get_transport().is_active():
                raise Exception("SSH connection lost.")
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            err_output = stderr.read().decode().strip()
            if err_output:
                if "not found" not in err_output.lower():
                    print(f"SSH Command Error: {err_output}")
            return stdout.read().decode().strip(), err_output
        except Exception as e:
            self.ui_queue.put(
                lambda: messagebox.showerror("Connection Error", f"An error occurred: {e}\nPlease log in again."))
            self.ui_queue.put(self.root.destroy)
            return "", str(e)

    def check_stream_status(self):
        self.ui_queue.put(lambda: self.status_label.config(text="Checking status..."))
        command = "ps aux | grep '[f]fmpeg.*rtmp://localhost/live/stream'"
        out, err = self.execute_command(command)
        if "SSH connection lost" in err: return
        self.is_stream_live = bool(out)
        status_text = "✅ Stream is LIVE" if self.is_stream_live else "❌ No stream is currently playing."
        color = "green" if self.is_stream_live else "red"
        self.ui_queue.put(lambda: self.status_label.config(text=status_text, foreground=color))
        self.ui_queue.put(lambda: self.stop_btn.config(state=tk.NORMAL if self.is_stream_live else tk.DISABLED))

    def stop_stream(self):
        if messagebox.askyesno("Confirm Hard Stop", "This will kill the stream instantly. Are you sure?"):
            command = f"pkill -9 -f '{FFMPEG_PATH}.*rtmp://localhost/live/stream'"
            self.execute_command(command)
            idle_script = f"if [ -f {REMOTE_IDLE_TEMPLATE_PATH} ]; then cp {REMOTE_IDLE_TEMPLATE_PATH} {REMOTE_PLAYER_HTML_PATH}; else echo '{DEFAULT_IDLE_HTML}' > {REMOTE_PLAYER_HTML_PATH}; fi"
            self.execute_command(idle_script)
            self.check_stream_status()
            self.update_status_bar("Stream stopped successfully.")

    def browse_and_upload(self):
        filepath = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mkv")])
        if not filepath: return
        filename = os.path.basename(filepath)
        remote_path = f'"{REMOTE_VIDEO_DIR}/{filename}"'
        self.ui_queue.put(lambda: self.file_path_label.config(text=filepath))
        self.ui_queue.put(lambda: self.upload_progress.config(value=0))

        def progress_callback(bytes_transferred, total_bytes):
            percentage = (bytes_transferred / total_bytes) * 100
            self.ui_queue.put(lambda: self.upload_progress.config(value=percentage))
            self.update_status_bar(f"Uploading {filename}... {int(percentage)}%")

        try:
            sftp = self.ssh_client.open_sftp()
            sftp.put(filepath, remote_path.strip('"'), callback=progress_callback)
            sftp.close()
            self.last_uploaded_path = remote_path
            self.update_status_bar(f"✅ Upload of '{filename}' complete. Ready for action.")
            self.ui_queue.put(lambda: self.start_now_btn.config(state=tk.NORMAL))
            self.ui_queue.put(lambda: self.schedule_btn.config(state=tk.NORMAL))
        except Exception as e:
            messagebox.showerror("Upload Error", str(e))
            self.update_status_bar(f"❌ Upload Error: {e}")

    def _start_or_schedule(self, remote_path, schedule_time_str=None, tehran_time_str=None):
        remote_script_path = "/root/stream_starter.sh"
        log_file = "/tmp/ffmpeg.log"
        player_setup_cmd = f"if [ -f {REMOTE_PLAYER_TEMPLATE_PATH} ]; then cp {REMOTE_PLAYER_TEMPLATE_PATH} {REMOTE_PLAYER_HTML_PATH}; else echo '{DEFAULT_PLAYER_HTML}' > {REMOTE_PLAYER_HTML_PATH}; fi"
        idle_setup_cmd = f"if [ -f {REMOTE_IDLE_TEMPLATE_PATH} ]; then cp {REMOTE_IDLE_TEMPLATE_PATH} {REMOTE_PLAYER_HTML_PATH}; else echo '{DEFAULT_IDLE_HTML}' > {REMOTE_PLAYER_HTML_PATH}; fi"
        script_content = f"""#!/bin/bash
echo "--- Stream script started at $(date) ---" > {log_file}
{player_setup_cmd}
echo "--- Starting ffmpeg... ---" >> {log_file}
{FFMPEG_PATH} -re -i {remote_path} -c:v copy -c:a copy -f flv rtmp://localhost/live/stream >> {log_file} 2>&1
FFMPEG_EXIT_CODE=$?
echo "--- ffmpeg finished with code: $FFMPEG_EXIT_CODE ---" >> {log_file}
{idle_setup_cmd}
rm {remote_path}
echo "--- Cleanup complete. ---" >> {log_file}
"""
        with self.ssh_client.open_sftp().file(remote_script_path, 'w') as f:
            f.write(script_content)
        self.execute_command(f"chmod +x {remote_script_path}")
        if schedule_time_str:
            server_tz, _ = self.execute_command("cat /etc/timezone")
            if not server_tz: server_tz = "UTC"
            self.execute_command(f"TZ={server_tz.strip()} at -f {remote_script_path} {schedule_time_str}")
            msg = f"Stream scheduled successfully for {tehran_time_str} (Tehran Time)."
            self.ui_queue.put(lambda: messagebox.showinfo("Scheduling Successful", msg))
            self.update_status_bar(f"⏰ {msg}")
            self.run_in_thread(self.refresh_queue)
        else:
            self.execute_command(f"nohup {remote_script_path} &")
            msg = "Stream sent to server. It should be live in a few seconds."
            self.ui_queue.put(lambda: messagebox.showinfo("Stream Started", msg))
            self.update_status_bar(f"🚀 {msg}")
        self.last_uploaded_path = None
        self.ui_queue.put(lambda: self.start_now_btn.config(state=tk.DISABLED))
        self.ui_queue.put(lambda: self.schedule_btn.config(state=tk.DISABLED))

    def start_stream_now(self):
        if not self.last_uploaded_path: messagebox.showwarning("Error", "Please upload a video first."); return
        self.run_in_thread(self._start_or_schedule, self.last_uploaded_path)

    def schedule_stream_later(self):
        if not self.last_uploaded_path: messagebox.showwarning("Error", "Please upload a video first."); return
        hour, minute, gregorian_date = self.hour_spinbox.get(), self.minute_spinbox.get(), self.date_entry.get_date()
        server_tz_str, _ = self.execute_command("cat /etc/timezone")
        if not server_tz_str: server_tz_str = "UTC"
        naive_dt = datetime.combine(gregorian_date, datetime.min.time()).replace(hour=int(hour), minute=int(minute))
        local_dt = self.local_timezone.localize(naive_dt)
        server_tz = pytz.timezone(server_tz_str.strip())
        server_dt = local_dt.astimezone(server_tz)
        schedule_time_str = server_dt.strftime('%H:%M %Y-%m-%d')
        tehran_time_str = local_dt.strftime('%H:%M on %Y-%m-%d')
        self._start_or_schedule(self.last_uploaded_path, schedule_time_str, tehran_time_str)

    def auto_refresh_queue(self):
        self.run_in_thread(self.refresh_queue)
        self.root.after(30000, self.auto_refresh_queue)

    def refresh_queue(self):
        if not hasattr(self, 'queue_tree'): return
        current_selection = self.queue_tree.focus()
        out, err = self.execute_command("atq")
        if "SSH connection lost" in err: return
        server_tz_str, _ = self.execute_command("cat /etc/timezone")
        server_tz = pytz.timezone(server_tz_str.strip() if server_tz_str else "UTC")
        jobs_to_display = []
        if out:
            for line in out.strip().split('\n'):
                try:
                    parts = line.split()
                    job_id, server_time_str = parts[0], " ".join(parts[1:6])
                    server_dt_naive = datetime.strptime(server_time_str, '%a %b %d %H:%M:%S %Y')
                    server_dt_aware = server_tz.localize(server_dt_naive)
                    tehran_dt = server_dt_aware.astimezone(self.local_timezone)
                    tehran_time_str_display = tehran_dt.strftime('%A, %Y-%m-%d at %H:%M')
                    job_content, _ = self.execute_command(f"at -c {job_id}")
                    video_match = re.search(r'-i ("|\')(/var/videos/.+?)\1', job_content)
                    video_name = os.path.basename(video_match.group(2)) if video_match else "Unknown"
                    jobs_to_display.append(
                        (job_id, server_dt_aware.strftime('%c %Z'), tehran_time_str_display, video_name))
                except (ValueError, IndexError) as e:
                    print(f"Could not parse job line: {line} - Error: {e}")
                    continue

        def _update_ui():
            if hasattr(self, 'queue_tree'):
                self.queue_tree.delete(*self.queue_tree.get_children())
                for job in jobs_to_display: self.queue_tree.insert("", "end", values=job)
                if current_selection and self.queue_tree.exists(current_selection):
                    self.queue_tree.focus(current_selection)
                    self.queue_tree.selection_set(current_selection)

        self.ui_queue.put(_update_ui)

    def cancel_selected_job(self):
        if not hasattr(self, 'queue_tree'): return
        selected_item = self.queue_tree.focus()
        if not selected_item: messagebox.showwarning("No Selection", "Please select a job to cancel."); return
        job_id = self.queue_tree.item(selected_item)['values'][0]
        video_name = self.queue_tree.item(selected_item)['values'][3]
        if messagebox.askyesno("Confirm Cancellation",
                               f"Are you sure you want to cancel the scheduled stream for '{video_name}' (Job ID: {job_id})?"):
            self.run_in_thread(lambda: (self.execute_command(f"atrm {job_id}"), self.refresh_queue(),
                                        self.update_status_bar(f"🗑️ Job {job_id} cancelled.")))

    def browse_for_template(self, template_type):
        filepath = filedialog.askopenfilename(title=f"Select HTML file for {template_type}",
                                              filetypes=[("HTML files", "*.html *.htm")])
        if filepath:
            if template_type == 'idle':
                self.idle_page_label.config(text=filepath)
            elif template_type == 'player':
                self.player_page_label.config(text=filepath)

    def set_template_page(self, template_type):
        if template_type == 'idle':
            local_path = self.idle_page_label.cget("text")
            remote_path = REMOTE_IDLE_TEMPLATE_PATH
            if "No custom" in local_path: messagebox.showwarning("Error",
                                                                 "Please select an idle HTML file first."); return
        elif template_type == 'player':
            local_path = self.player_page_label.cget("text")
            remote_path = REMOTE_PLAYER_TEMPLATE_PATH
            if "No custom" in local_path: messagebox.showwarning("Error",
                                                                 "Please select a player HTML file first."); return
        try:
            sftp = self.ssh_client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            msg = f"Custom {template_type} page has been set on the server."
            messagebox.showinfo("Success", msg)
            self.update_status_bar(f"✅ {msg}")
            if template_type == 'idle' and not self.is_stream_live:
                self.execute_command(f"cp {REMOTE_IDLE_TEMPLATE_PATH} {REMOTE_PLAYER_HTML_PATH}")
                messagebox.showinfo("Applied", "Idle page has been applied live.")
                self.update_status_bar("Idle page applied live.")
        except Exception as e:
            messagebox.showerror("Upload Error", str(e))
            self.update_status_bar(f"❌ Template upload error: {e}")


if __name__ == "__main__":
    root = ThemedTk(theme="arc")
    app = App(root)
    root.mainloop()
