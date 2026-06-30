#!/usr/bin/env python3
# catsans's chip 8 emu 0.1.1
# FILES = OFF — everything is in this one script.
# CHIP‑8 interpreter + mGBA‑style blue UI, 60 fps, 600x400.

import os
import random
import sys
import tkinter as tk
from tkinter import filedialog, ttk

# ─── HARDWARE CONSTANTS ────────────────────────────────────────────
CHIP8_WIDTH  = 64
CHIP8_HEIGHT = 32
SCALE        = 5               # 64*5 = 320, 32*5 = 160
DISPLAY_W    = CHIP8_WIDTH * SCALE
DISPLAY_H    = CHIP8_HEIGHT * SCALE
WINDOW_W     = 600
WINDOW_H     = 400
CPU_HZ       = 700
TIMER_HZ     = 60
CYCLES_PER_FRAME = max(1, CPU_HZ // TIMER_HZ)   # ~11 cycles per frame

# Default ROM (tiny) — a simple "snake" / moving dot demo.
# This is embedded so you don't need any external file.
DEFAULT_ROM = bytes([
    0x6A, 0x0A,       # LD V[10], 10
    0x6B, 0x0A,       # LD V[11], 10
    0xDA, 0x84,       # DRW V[10], V[11], 4
    0x70, 0x01,       # ADD V[0], 1
    0x31, 0x20,       # SE V[1], 32
    0x12, 0x00,       # JP 0x200
    0x61, 0x00,       # LD V[1], 0
    0x12, 0x00,       # JP 0x200
])

# ─── CHIP‑8 CORE ──────────────────────────────────────────────────
class Chip8:
    def __init__(self):
        self.memory  = bytearray(4096)
        self.V       = [0] * 16
        self.I       = 0
        self.pc      = 0x200
        self.stack   = [0] * 16
        self.sp      = 0
        self.delay   = 0
        self.sound   = 0
        self.gfx     = [0] * (CHIP8_WIDTH * CHIP8_HEIGHT)
        self.key     = [0] * 16
        self.waiting = False
        self.wait_reg= 0

        # Load embedded font
        font = [
            0xF0,0x90,0x90,0x90,0xF0, 0x20,0x60,0x20,0x20,0x70,
            0xF0,0x10,0xF0,0x80,0xF0, 0xF0,0x10,0xF0,0x10,0xF0,
            0x90,0x90,0xF0,0x10,0x10, 0xF0,0x80,0xF0,0x10,0xF0,
            0xF0,0x80,0xF0,0x90,0xF0, 0xF0,0x10,0x20,0x40,0x40,
            0xF0,0x90,0xF0,0x90,0xF0, 0xF0,0x90,0xF0,0x10,0xF0,
            0xF0,0x90,0xF0,0x90,0x90, 0xE0,0x90,0xE0,0x90,0xE0,
            0xF0,0x80,0x80,0x80,0xF0, 0xE0,0x90,0x90,0x90,0xE0,
            0xF0,0x80,0xF0,0x80,0xF0, 0xF0,0x80,0xF0,0x80,0x80
        ]
        for i, b in enumerate(font):
            self.memory[0x50 + i] = b

        # Pre‑load the default embedded ROM so it runs immediately.
        self.load_rom(DEFAULT_ROM)

    def load_rom(self, data: bytes):
        self.reset()
        start = 0x200
        for i, b in enumerate(data[:3584]):   # max ROM size
            self.memory[start + i] = b

    def reset(self):
        self.V       = [0] * 16
        self.I       = 0
        self.pc      = 0x200
        self.stack   = [0] * 16
        self.sp      = 0
        self.delay   = 0
        self.sound   = 0
        self.gfx     = [0] * (CHIP8_WIDTH * CHIP8_HEIGHT)
        self.key     = [0] * 16
        self.waiting = False

    def set_key(self, key: int, pressed: bool):
        if 0 <= key <= 0xF:
            self.key[key] = 1 if pressed else 0
            if self.waiting and pressed:
                self.V[self.wait_reg] = key
                self.waiting = False

    def tick_timers(self):
        if self.delay > 0:
            self.delay -= 1
        if self.sound > 0:
            self.sound -= 1

    def step(self):
        if self.waiting:
            return

        op = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        self.pc += 2

        x = (op & 0x0F00) >> 8
        y = (op & 0x00F0) >> 4
        n = op & 0x000F
        kk = op & 0x00FF
        addr = op & 0x0FFF

        if op == 0x00E0:               # CLS
            self.gfx = [0] * (CHIP8_WIDTH * CHIP8_HEIGHT)
        elif op == 0x00EE:             # RET
            self.sp -= 1
            self.pc = self.stack[self.sp]
        elif (op & 0xF000) == 0x1000:  # JP addr
            self.pc = addr
        elif (op & 0xF000) == 0x2000:  # CALL addr
            self.stack[self.sp] = self.pc
            self.sp += 1
            self.pc = addr
        elif (op & 0xF000) == 0x3000:  # SE Vx, kk
            if self.V[x] == kk:
                self.pc += 2
        elif (op & 0xF000) == 0x4000:  # SNE Vx, kk
            if self.V[x] != kk:
                self.pc += 2
        elif (op & 0xF000) == 0x5000:  # SE Vx, Vy
            if self.V[x] == self.V[y]:
                self.pc += 2
        elif (op & 0xF000) == 0x6000:  # LD Vx, kk
            self.V[x] = kk
        elif (op & 0xF000) == 0x7000:  # ADD Vx, kk
            self.V[x] = (self.V[x] + kk) & 0xFF
        elif (op & 0xF000) == 0x8000:
            if n == 0:      # LD Vx, Vy
                self.V[x] = self.V[y]
            elif n == 1:    # OR
                self.V[x] |= self.V[y]
            elif n == 2:    # AND
                self.V[x] &= self.V[y]
            elif n == 3:    # XOR
                self.V[x] ^= self.V[y]
            elif n == 4:    # ADD Vx, Vy
                s = self.V[x] + self.V[y]
                self.V[0xF] = 1 if s > 0xFF else 0
                self.V[x] = s & 0xFF
            elif n == 5:    # SUB Vx, Vy
                self.V[0xF] = 1 if self.V[x] > self.V[y] else 0
                self.V[x] = (self.V[x] - self.V[y]) & 0xFF
            elif n == 6:    # SHR Vx
                self.V[0xF] = self.V[x] & 1
                self.V[x] >>= 1
            elif n == 7:    # SUBN Vx, Vy
                self.V[0xF] = 1 if self.V[y] > self.V[x] else 0
                self.V[x] = (self.V[y] - self.V[x]) & 0xFF
            elif n == 0xE:  # SHL Vx
                self.V[0xF] = (self.V[x] >> 7) & 1
                self.V[x] = (self.V[x] << 1) & 0xFF
        elif (op & 0xF000) == 0x9000:  # SNE Vx, Vy
            if self.V[x] != self.V[y]:
                self.pc += 2
        elif (op & 0xF000) == 0xA000:  # LD I, addr
            self.I = addr
        elif (op & 0xF000) == 0xB000:  # JP V0, addr
            self.pc = addr + self.V[0]
        elif (op & 0xF000) == 0xC000:  # RND Vx, kk
            self.V[x] = random.randint(0, 255) & kk
        elif (op & 0xF000) == 0xD000:  # DRW Vx, Vy, nibble
            cx = self.V[x] % CHIP8_WIDTH
            cy = self.V[y] % CHIP8_HEIGHT
            self.V[0xF] = 0
            for row in range(n):
                sprite = self.memory[self.I + row]
                for col in range(8):
                    if (sprite & (0x80 >> col)) == 0:
                        continue
                    px = (cx + col) % CHIP8_WIDTH
                    py = (cy + row) % CHIP8_HEIGHT
                    idx = py * CHIP8_WIDTH + px
                    if self.gfx[idx]:
                        self.V[0xF] = 1
                    self.gfx[idx] ^= 1
        elif (op & 0xF000) == 0xE000:
            if kk == 0x9E:   # SKP Vx
                if self.key[self.V[x] & 0xF]:
                    self.pc += 2
            elif kk == 0xA1: # SKNP Vx
                if not self.key[self.V[x] & 0xF]:
                    self.pc += 2
        elif (op & 0xF000) == 0xF000:
            if kk == 0x07:   # LD Vx, DT
                self.V[x] = self.delay
            elif kk == 0x0A: # LD Vx, K (wait for key)
                self.waiting = True
                self.wait_reg = x
            elif kk == 0x15: # LD DT, Vx
                self.delay = self.V[x]
            elif kk == 0x18: # LD ST, Vx
                self.sound = self.V[x]
            elif kk == 0x1E: # ADD I, Vx
                self.I = (self.I + self.V[x]) & 0xFFFF
            elif kk == 0x29: # LD F, Vx
                self.I = 0x50 + (self.V[x] * 5)
            elif kk == 0x33: # LD B, Vx
                v = self.V[x]
                self.memory[self.I]     = v // 100
                self.memory[self.I + 1] = (v // 10) % 10
                self.memory[self.I + 2] = v % 10
            elif kk == 0x55: # LD [I], Vx
                for i in range(x + 1):
                    self.memory[self.I + i] = self.V[i]
            elif kk == 0x65: # LD Vx, [I]
                for i in range(x + 1):
                    self.V[i] = self.memory[self.I + i]

# ─── GUI (mGBA blue hue, black buttons, 600x400) ──────────────────
BG           = "#0a0e1a"
PANEL        = "#0c1022"
BUTTON_BG    = "#000000"
BUTTON_FG    = "#5aaeff"       # blue text
BUTTON_ACTIVE= "#1a2a4a"
TEXT         = "#4a9eff"
TEXT_DIM     = "#2f6db8"
BORDER       = "#1a3a5c"
STATUS_BG    = "#080a14"

class Chip8Emu(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("catsans's chip 8 emu 0.1.1")
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.core = Chip8()
        self.running = False
        self.paused = False
        self.status_var = tk.StringVar(value="Embedded ROM loaded (FILES = OFF)")

        self._style()
        self._build_ui()
        self._bind_keys()
        self._refresh_loop()

    def _style(self):
        self.option_add("*Font", "TkDefaultFont 9")
        self.option_add("*Background", PANEL)
        self.option_add("*Foreground", TEXT)
        self.option_add("*Menu.background", PANEL)
        self.option_add("*Menu.foreground", TEXT)
        self.option_add("*Menu.activeBackground", BUTTON_ACTIVE)
        self.option_add("*Menu.activeForeground", BUTTON_FG)

    def _build_ui(self):
        # ─── Top bar (mGBA style) ──────────────────────────────────
        toolbar = tk.Frame(self, bg=PANEL, height=28)
        toolbar.pack(fill=tk.X, padx=4, pady=(2,0))
        toolbar.pack_propagate(False)

        def mk_btn(text, cmd):
            return tk.Button(
                toolbar,
                text=text,
                command=cmd,
                bg=BUTTON_BG,
                fg=BUTTON_FG,
                activebackground=BUTTON_ACTIVE,
                activeforeground=BUTTON_FG,
                relief=tk.FLAT,
                bd=1,
                highlightthickness=1,
                highlightbackground=BORDER,
                highlightcolor=BORDER,
                padx=10,
                pady=2,
            )
        mk_btn("Pause", self.toggle_pause).pack(side=tk.LEFT, padx=2)
        mk_btn("Reset", self.reset).pack(side=tk.LEFT, padx=2)
        mk_btn("Load ROM", self.load_rom).pack(side=tk.RIGHT, padx=2)

        # ─── Display + side panel ──────────────────────────────────
        main = tk.Frame(self, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        left = tk.Frame(main, bg=BORDER, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            left,
            width=DISPLAY_W,
            height=DISPLAY_H,
            bg="#0a0a12",
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(padx=4, pady=4)
        self.pixels = []
        for y in range(CHIP8_HEIGHT):
            row = []
            for x in range(CHIP8_WIDTH):
                row.append(self.canvas.create_rectangle(
                    x * SCALE, y * SCALE,
                    (x+1) * SCALE, (y+1) * SCALE,
                    fill="#0a0a12",
                    outline="#0a0a12",
                ))
            self.pixels.append(row)

        right = tk.Frame(main, bg=PANEL, width=180)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(4,0))
        right.pack_propagate(False)

        tk.Label(right, text="CONTROL", bg=PANEL, fg=TEXT, font=("TkDefaultFont",9,"bold")).pack(anchor="w", padx=8, pady=(8,4))
        tk.Label(right, text="CHIP-8 keypad", bg=PANEL, fg=TEXT_DIM, justify=tk.LEFT).pack(anchor="w", padx=8)
        tk.Label(right, text="1 2 3 4\nQ W E R\nA S D F\nZ X C V", bg=PANEL, fg=TEXT_DIM, justify=tk.LEFT).pack(anchor="w", padx=8, pady=4)
        tk.Label(right, text="FILES = OFF\nmGBA-style\ndark blue hue", bg=PANEL, fg=TEXT, justify=tk.LEFT).pack(anchor="w", padx=8, pady=(12,0))

        # ─── Status bar ────────────────────────────────────────────
        status = tk.Frame(self, bg=STATUS_BG, height=22)
        status.pack(fill=tk.X, side=tk.BOTTOM)
        status.pack_propagate(False)
        tk.Label(status, textvariable=self.status_var, bg=STATUS_BG, fg=TEXT_DIM, anchor="w").pack(fill=tk.X, padx=8)

    def _bind_keys(self):
        self.bind("<KeyPress>",   self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)

    def _on_key_press(self, e):
        k = KEY_MAP.get(e.keysym)
        if k is not None:
            self.core.set_key(k, True)

    def _on_key_release(self, e):
        k = KEY_MAP.get(e.keysym)
        if k is not None:
            self.core.set_key(k, False)

    def toggle_pause(self):
        self.paused = not self.paused
        self.status_var.set("Paused" if self.paused else "Running")

    def reset(self):
        self.core.load_rom(DEFAULT_ROM)
        self.paused = False
        self.status_var.set("Reset (FILES = OFF)")

    def load_rom(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Load CHIP‑8 ROM",
            filetypes=[("CHIP‑8 ROM", "*.ch8"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception as e:
            self.status_var.set(f"Error: {e}")
            return
        self.core.load_rom(data)
        self.paused = False
        self.status_var.set(f"Loaded: {os.path.basename(path)}")

    def _refresh_loop(self):
        # 60 fps timer — update display and run CPU cycles
        if not self.paused:
            for _ in range(CYCLES_PER_FRAME):
                self.core.step()
            self.core.tick_timers()
            self._draw_display()

        self.after(16, self._refresh_loop)   # ~60 Hz

    def _draw_display(self):
        gfx = self.core.gfx
        for y in range(CHIP8_HEIGHT):
            for x in range(CHIP8_WIDTH):
                idx = y * CHIP8_WIDTH + x
                color = "#4a9eff" if gfx[idx] else "#0a0a12"   # blue on dark
                self.canvas.itemconfig(self.pixels[y][x], fill=color, outline=color)

# ─── KEYMAP (standard CHIP‑8 hex layout) ──────────────────────────
KEY_MAP = {
    "1": 0x1, "2": 0x2, "3": 0x3, "4": 0xC,
    "q": 0x4, "w": 0x5, "e": 0x6, "r": 0xD,
    "a": 0x7, "s": 0x8, "d": 0x9, "f": 0xE,
    "z": 0xA, "x": 0x0, "c": 0xB, "v": 0xF,
}

# ─── ENTRY ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Chip8Emu()
    app.mainloop()