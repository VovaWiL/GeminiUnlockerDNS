import os
import sys
import json
import time
import socket
import ctypes
import threading
import subprocess
import customtkinter as ctk
from tkinter import messagebox

CONFIG_FILE = "dns_list.json"

DEFAULT_DNS = [
    {
        "name": "dns.magicdns.ru",
        "primary": "109.120.177.170",
        "secondary": "45.88.163.92"
    },
    {
        "name": "dns-ai.ru",
        "primary": "194.87.196.13",
        "secondary": "45.151.102.219"
    },
    {
        "name": "xbox-dns.ru",
        "primary": "111.88.96.54",
        "secondary": "111.88.96.55"
    }
]


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def run_powershell(cmd):
    """Выполняет PowerShell-команду без всплывающего черного окна."""
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True,
        text=True,
        startupinfo=startupinfo,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    return result.returncode == 0, result.stderr.strip()


def measure_dns_ping(ip, domain="gemini.google.com", timeout=2.0):
    """Измеряет время отклика DNS-сервера (в мс) реальным пакетом на порт 53."""
    query = bytearray(b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00")
    for part in domain.split("."):
        query.append(len(part))
        query.extend(part.encode("ascii"))
    query.extend(b"\x00\x00\x01\x00\x01")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    start_time = time.perf_counter()
    try:
        sock.sendto(query, (ip, 53))
        data, _ = sock.recvfrom(512)
        ping_ms = int((time.perf_counter() - start_time) * 1000)
        # Проверка кода ответа DNS (RCODE == 0 означает успешный ответ без ошибки)
        if len(data) >= 12 and (data[3] & 0x0F) == 0:
            return ping_ms
        return None
    except Exception:
        return None
    finally:
        sock.close()


class GeminiUnlockerDNSApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GeminiUnlockerDNS")
        self.geometry("680x560")
        self.resizable(False, False)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.dns_list = self.load_dns_list()
        self.ping_results = {}
        self.active_dns_name = None

        self.build_ui()

    def load_dns_list(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        self.save_dns_list(DEFAULT_DNS)
        return [dict(item) for item in DEFAULT_DNS]

    def save_dns_list(self, data=None):
        if data is None:
            data = self.dns_list
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def build_ui(self):
        # Заголовок
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(15, 5))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="GeminiUnlockerDNS",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_lbl.pack(side="left")

        self.status_lbl = ctk.CTkLabel(
            header_frame,
            text="Статус: Ожидание",
            font=ctk.CTkFont(size=13),
            text_color="#A0A0A0"
        )
        self.status_lbl.pack(side="right", pady=5)

        subtitle_lbl = ctk.CTkLabel(
            self,
            text="Обход «App unavailable» для Gemini, Claude и ChatGPT с авто-подбором по пингу",
            font=ctk.CTkFont(size=12),
            text_color="#888888"
        )
        subtitle_lbl.pack(anchor="w", padx=20, pady=(0, 10))

        # Кнопки управления
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=20, pady=5)

        self.auto_btn = ctk.CTkButton(
            ctrl_frame,
            text="🚀 Подобрать и включить лучший DNS",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self.start_auto_select
        )
        self.auto_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.reset_btn = ctk.CTkButton(
            ctrl_frame,
            text="🔄 Сбросить DNS (Авто)",
            font=ctk.CTkFont(size=13),
            height=40,
             width=180,
            fg_color="#374151",
            hover_color="#4B5563",
            command=self.reset_dns
        )
        self.reset_btn.pack(side="right")

        # Список серверов
        self.list_frame = ctk.CTkScrollableFrame(self, label_text="Список DNS-серверов", height=250)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.render_dns_list()

        # Панель добавления своего DNS
        add_frame = ctk.CTkFrame(self)
        add_frame.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkLabel(
            add_frame,
            text="Добавить свой DNS-сервер:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(8, 4))

        self.name_entry = ctk.CTkEntry(add_frame, placeholder_text="Название (напр. my-dns.ru)", width=180)
        self.name_entry.grid(row=1, column=0, padx=(12, 6), pady=(0, 10))

        self.prim_entry = ctk.CTkEntry(add_frame, placeholder_text="Основной IP", width=155)
        self.prim_entry.grid(row=1, column=1, padx=6, pady=(0, 10))

        self.sec_entry = ctk.CTkEntry(add_frame, placeholder_text="Доп. IP (необяз.)", width=155)
        self.sec_entry.grid(row=1, column=2, padx=6, pady=(0, 10))

        add_btn = ctk.CTkButton(
            add_frame,
            text="+ Добавить",
            width=100,
            command=self.add_custom_dns
        )
        add_btn.grid(row=1, column=3, padx=(6, 12), pady=(0, 10))

    def render_dns_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        for idx, item in enumerate(self.dns_list):
            row = ctk.CTkFrame(self.list_frame, fg_color="#1F2937")
            row.pack(fill="x", pady=4, padx=4)

            is_active = (self.active_dns_name == item["name"])
            title_color = "#34D399" if is_active else "#FFFFFF"
            prefix = "✔ " if is_active else ""

            info_text = f"{prefix}{item['name']}\nОсновной: {item['primary']}   |   Доп: {item.get('secondary') or '—'}"
            lbl = ctk.CTkLabel(
                row,
                text=info_text,
                justify="left",
                font=ctk.CTkFont(size=12, weight="bold" if is_active else "normal"),
                text_color=title_color
            )
            lbl.pack(side="left", padx=12, pady=8)

            # Кнопка удаления
            del_btn = ctk.CTkButton(
                row,
                text="✕",
                width=32,
                height=28,
                fg_color="#7F1D1D",
                hover_color="#991B1B",
                command=lambda i=idx: self.delete_dns(i)
            )
            del_btn.pack(side="right", padx=(4, 10))

            # Кнопка ручного подключения
            apply_btn = ctk.CTkButton(
                row,
                text="Выбрать",
                width=80,
                height=28,
                fg_color="#2563EB" if not is_active else "#059669",
                command=lambda s=item: self.apply_single_dns(s)
            )
            apply_btn.pack(side="right", padx=4)

            # Индикатор пинга
            ping_val = self.ping_results.get(item["name"], "— мс")
            if isinstance(ping_val, int):
                ping_str = f"{ping_val} мс"
                ping_color = "#34D399" if ping_val < 80 else ("#FBBF24" if ping_val < 180 else "#F87171")
            elif ping_val == "Ошибка":
                ping_str = "Недоступен"
                ping_color = "#F87171"
            else:
                ping_str = str(ping_val)
                ping_color = "#9CA3AF"

            ping_lbl = ctk.CTkLabel(
                row,
                text=ping_str,
                width=85,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=ping_color
            )
            ping_lbl.pack(side="right", padx=8)

    def add_custom_dns(self):
        name = self.name_entry.get().strip()
        primary = self.prim_entry.get().strip()
        secondary = self.sec_entry.get().strip()

        if not name or not primary:
            messagebox.showwarning("Внимание", "Укажи название и основной IP-адрес!")
            return

        self.dns_list.append({
            "name": name,
            "primary": primary,
            "secondary": secondary
        })
        self.save_dns_list()
        self.name_entry.delete(0, "end")
        self.prim_entry.delete(0, "end")
        self.sec_entry.delete(0, "end")
        self.render_dns_list()

    def delete_dns(self, idx):
        removed = self.dns_list.pop(idx)
        if self.active_dns_name == removed["name"]:
            self.active_dns_name = None
        self.save_dns_list()
        self.render_dns_list()

    def set_system_dns(self, primary, secondary=None):
        """Устанавливает DNS на все активные адаптеры Windows."""
        addrs = f'"{primary}"' + (f',"{secondary}"' if secondary else "")
        ps_cmd = (
            f"Get-NetAdapter | Where-Object {{$_.Status -eq 'Up'}} | "
            f"ForEach-Object {{ Set-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex -ServerAddresses ({addrs}) }}; "
            f"Clear-DnsClientCache"
        )
        return run_powershell(ps_cmd)

    def apply_single_dns(self, server):
        self.status_lbl.configure(text=f"Проверка {server['name']}...", text_color="#FBBF24")
        self.update_idletasks()

        def worker():
            ping = measure_dns_ping(server["primary"])
            if ping is None and server.get("secondary"):
                ping = measure_dns_ping(server["secondary"])

            self.ping_results[server["name"]] = ping if ping is not None else "Ошибка"

            ok, err = self.set_system_dns(server["primary"], server.get("secondary"))
            if ok:
                self.active_dns_name = server["name"]
                self.after(0, lambda: self.status_lbl.configure(
                    text=f"Активен: {server['name']} ({ping if ping else '?'} мс)",
                    text_color="#34D399"
                ))
            else:
                self.after(0, lambda: messagebox.showerror(
                    "Ошибка прав доступа",
                    f"Не удалось изменить DNS. Запусти программу от имени Администратора!\n\n{err}"
                ))
                self.after(0, lambda: self.status_lbl.configure(text="Ошибка установки", text_color="#F87171"))

            self.after(0, self.render_dns_list)

        threading.Thread(target=worker, daemon=True).start()

    def start_auto_select(self):
        if not self.dns_list:
            messagebox.showwarning("Список пуст", "Добавь хотя бы один DNS-сервер!")
            return

        self.auto_btn.configure(state="disabled", text="⏳ Измеряем пинг серверов...")
        self.status_lbl.configure(text="Тестирование всех DNS...", text_color="#FBBF24")

        def worker():
            valid_servers = []
            for srv in self.dns_list:
                p1 = measure_dns_ping(srv["primary"])
                p2 = measure_dns_ping(srv["secondary"]) if srv.get("secondary") else None

                # Берем наименьший отклик из основного/дополнительного
                pings = [p for p in (p1, p2) if p is not None]
                if pings:
                    best_ping = min(pings)
                    self.ping_results[srv["name"]] = best_ping
                    valid_servers.append((best_ping, srv))
                else:
                    self.ping_results[srv["name"]] = "Ошибка"

                self.after(0, self.render_dns_list)

            # Сортируем по минимальному времени отклика (мс)
            valid_servers.sort(key=lambda x: x[0])

            applied = False
            for ping_ms, srv in valid_servers:
                ok, _ = self.set_system_dns(srv["primary"], srv.get("secondary"))
                if ok:
                    self.active_dns_name = srv["name"]
                    applied = True
                    self.after(0, lambda s=srv, p=ping_ms: self.status_lbl.configure(
                        text=f"Выбран лучший: {s['name']} ({p} мс)",
                        text_color="#34D399"
                    ))
                    break

            if not applied:
                self.after(0, lambda: self.status_lbl.configure(
                    text="Ошибка: ни один сервер не подошел",
                    text_color="#F87171"
                ))
                if not valid_servers:
                    self.after(0, lambda: messagebox.showerror(
                        "Ошибка",
                        "Ни один DNS-сервер из списка не ответил на запрос."
                    ))
                else:
                    self.after(0, lambda: messagebox.showerror(
                        "Нужны права Администратора",
                        "Запусти программу от имени Администратора для смены системного DNS!"
                    ))

            self.after(0, self.render_dns_list)
            self.after(0, lambda: self.auto_btn.configure(
                state="normal",
                text="🚀 Подобрать и включить лучший DNS"
            ))

        threading.Thread(target=worker, daemon=True).start()

    def reset_dns(self):
        ps_cmd = (
            "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
            "ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex -ResetServerAddresses }; "
            "Clear-DnsClientCache"
        )
        ok, err = run_powershell(ps_cmd)
        if ok:
            self.active_dns_name = None
            self.status_lbl.configure(text="Статус: Стандартный DNS (Авто)", text_color="#A0A0A0")
            self.render_dns_list()
        else:
            messagebox.showerror("Ошибка", f"Запусти программу от имени Администратора!\n{err}")


if __name__ == "__main__":
    # Авто-запрос прав администратора при запуске
    if sys.platform == "win32" and not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join([f'"{arg}"' for arg in sys.argv]), None, 1
        )
        sys.exit()

    app = GeminiUnlockerDNSApp()
    app.mainloop()
