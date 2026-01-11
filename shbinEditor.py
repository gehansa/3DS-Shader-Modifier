from tkinter import ttk, filedialog, messagebox
import struct, json, os
import tkinter as tk

def float_to_pica24(f):
    if f == 0: return 0
    try:
        packed = struct.pack('<f', f)
        i = struct.unpack('<I', packed)[0]
    except OverflowError:
        return 0 
    
    sign = (i >> 31) & 1
    exp  = (i >> 23) & 0xFF
    mant = i & 0x7FFFFF
    new_exp = exp - 127 + 63
    
    if new_exp <= 0: return 0
    if new_exp >= 127: new_exp = 127
    new_mant = mant >> 7
    return (sign << 23) | (new_exp << 16) | new_mant

def pica24_to_float(val):
    if val == 0: return 0.0
    sign = (val >> 23) & 1
    exp  = (val >> 16) & 0x7F
    mant = val & 0xFFFF
    new_exp = exp - 63 + 127
    new_mant = mant << 7
    i = (sign << 31) | (new_exp << 23) | new_mant
    return struct.unpack('<f', struct.pack('<I', i))[0]

class SHBINParser:
    def __init__(self):
        self.data = bytearray()
        self.dvles = []
        self.filename = ""

    def load(self, filename):
        self.filename = filename
        with open(filename, 'rb') as f:
            self.data = bytearray(f.read())
        self.parse()

    def parse(self):
        self.dvles = []
        magic = self.data[0:4].decode('ascii', errors='ignore')
        if magic != 'DVLB':
            raise ValueError("Not a valid DVLB .shbin file")
        
        n_dvles = struct.unpack('<I', self.data[4:8])[0]
        for i in range(n_dvles):
            offset = struct.unpack('<I', self.data[8 + i*4 : 12 + i*4])[0]
            self.parse_dvle(offset, i)

    def parse_dvle(self, offset, index):
        const_rel_off = struct.unpack('<I', self.data[offset+0x18:offset+0x1C])[0]
        const_count   = struct.unpack('<I', self.data[offset+0x1C:offset+0x20])[0]
        const_abs_off = offset + const_rel_off
        constants = []

        for i in range(const_count):
            entry_offset = const_abs_off + (i * 0x14)
            entry_type = self.data[entry_offset + 0x00]
            entry_id   = self.data[entry_offset + 0x02]
            entry_len  = self.data[entry_offset + 0x03]

            raw_vals = [0, 0, 0, 0]
            if entry_type == 2:
                for j in range(4):
                    raw_vals[j] = struct.unpack('<I', self.data[entry_offset+4+(j*4):entry_offset+8+(j*4)])[0]
            elif entry_type == 1:
                raw_vals = list(struct.unpack('BBBB', self.data[entry_offset+4:entry_offset+8]))
            elif entry_type == 0:
                raw_vals[0] = self.data[entry_offset+4]

            constants.append({
                "idx": i,
                "type": entry_type,
                "id": entry_id,
                "len": entry_len,
                "offset": entry_offset,
                "raw": raw_vals,
                "name": "",
                "array_index": None
            })


        input_rel_off = struct.unpack('<I', self.data[offset+0x30:offset+0x34])[0]
        input_count   = struct.unpack('<I', self.data[offset+0x34:offset+0x38])[0]
        sym_rel_off   = struct.unpack('<I', self.data[offset+0x38:offset+0x3C])[0]
        input_abs = offset + input_rel_off
        sym_abs   = offset + sym_rel_off

        input_names = []
        for i in range(input_count):
            entry_off = input_abs + (i * 8)

            name_offset = struct.unpack('<I', self.data[entry_off:entry_off+4])[0]
            reg_start   = struct.unpack('<H', self.data[entry_off+4:entry_off+6])[0]

            ptr = sym_abs + name_offset
            chars = []
            while self.data[ptr] != 0:
                chars.append(chr(self.data[ptr]))
                ptr += 1

            name = "".join(chars)
            input_names.append(name)

        for i, c in enumerate(constants):
            if i < len(input_names):
                c["name"] = input_names[i]

        grouped = []
        skip = set()
        for i, c in enumerate(constants):
            if i in skip:
                continue

            if c["type"] == 2 and c["len"] > 1:
                group = [c]
                for j in range(1, c["len"]):
                    if i+j < len(constants):
                        group.append(constants[i+j])
                        skip.add(i+j)

                base_name = c["name"]
                if base_name:
                    base_name = base_name.split("[")[0]

                for idx, g in enumerate(group):
                    g["name"] = f"{base_name}[{idx}]"

            grouped.append(c)

        self.dvles.append({
            "index": index,
            "constants": grouped
        })

    def update_value(self, dvle_idx, const_idx, raw_values):
        target = self.dvles[dvle_idx]['constants'][const_idx]
        offset = target['offset']
        target['raw'] = raw_values
        
        if target['type'] == 2:
            for j in range(4):
                struct.pack_into('<I', self.data, offset+4+(j*4), raw_values[j] & 0xFFFFFF)
        elif target['type'] == 1:
            struct.pack_into('BBBB', self.data, offset+4, *raw_values)
        elif target['type'] == 0:
            struct.pack_into('B', self.data, offset+4, raw_values[0])

    def save(self, filename):
        with open(filename, 'wb') as f:
            f.write(self.data)

    def to_json(self):
        export = {"filename": os.path.basename(self.filename), "dvles": []}
        for dvle in self.dvles:
            d_obj = {"index": dvle['index'], "uniforms": []}
            for c in dvle['constants']:
                readable = [pica24_to_float(x) for x in c['raw']] if c['type']==2 else c['raw']
                d_obj["uniforms"].append({
                    "name": c['name'],
                    "id": c['id'],
                    "type": "float" if c['type']==2 else "int/bool",
                    "values": readable
                })
            export["dvles"].append(d_obj)
        return json.dumps(export, indent=2)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("3DS Shader Editor (Named)")
        self.geometry("950x600")
        self.parser = SHBINParser()
        self.selected_dvle = None
        self.selected_const = None
        self.build_ui()

    def build_ui(self):
        toolbar = tk.Frame(self, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        tk.Button(toolbar, text="Open .shbin", command=self.open_file).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="Save .shbin", command=self.save_file).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="Export JSON", command=self.export_json).pack(side=tk.LEFT, padx=20, pady=2)

        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        tree_frame = tk.Frame(paned)
        self.tree = ttk.Treeview(tree_frame, columns=("Name", "Type", "Values"), show="headings")
        self.tree.heading("Name", text="Uniform Name")
        self.tree.heading("Type", text="Type")
        self.tree.heading("Values", text="Preview")
        self.tree.column("Name", width=180)
        self.tree.column("Type", width=50)
        self.tree.column("Values", width=250)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        paned.add(tree_frame, width=550)

        edit_frame = tk.LabelFrame(paned, text="Edit Value", padx=10, pady=10)
        paned.add(edit_frame, width=350)
        
        self.lbl_name = tk.Label(edit_frame, text="-", font=("Arial", 10, "bold"))
        self.lbl_name.pack(pady=5)

        self.vars = [tk.StringVar() for _ in range(4)]
        labels = ['X (R)', 'Y (G)', 'Z (B)', 'W (A)']
        for i, lab in enumerate(labels):
            row = tk.Frame(edit_frame)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=lab, width=6).pack(side=tk.LEFT)
            tk.Entry(row, textvariable=self.vars[i]).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(edit_frame, text="Apply Changes", command=self.apply, bg="#dddddd").pack(pady=15, fill=tk.X)

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Shader Binary", "*.shbin")])
        if path:
            self.parser.load(path)
            self.refresh_tree()

    def save_file(self):
        if not self.parser.data: return
        path = filedialog.asksaveasfilename(defaultextension=".shbin")
        if path:
            self.parser.save(path)
            messagebox.showinfo("Success", "Saved!")

    def export_json(self):
        if not self.parser.data: return
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if path:
            with open(path, 'w') as f:
                f.write(self.parser.to_json())
            messagebox.showinfo("Success", "JSON Exported!")

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for dvle in self.parser.dvles:
            parent = self.tree.insert("", "end", text=f"DVLE {dvle['index']}", open=True, values=("Header", "", ""))
            for i, c in enumerate(dvle['constants']):
                name = c['name'] if c['name'] else f"Unknown_ID_{c['id']:02X}"
                val_str = f"({pica24_to_float(c['raw'][0]):.2f}, ...)" if c['type']==2 else str(c['raw'])
                self.tree.insert(parent, "end", iid=f"{dvle['index']}_{i}", values=(name, "Float" if c['type']==2 else "Int", val_str))

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel or "_" not in sel[0]: return
        dvle_idx, const_idx = map(int, sel[0].split('_'))
        self.selected_dvle = dvle_idx
        self.selected_const = const_idx
        c = self.parser.dvles[dvle_idx]['constants'][const_idx]
        
        self.lbl_name.config(text=c['name'] if c['name'] else f"ID: {c['id']:02X}")
        for i in range(4):
            val = pica24_to_float(c['raw'][i]) if c['type']==2 else c['raw'][i]
            self.vars[i].set(f"{val:.6g}" if c['type']==2 else str(val))

    def apply(self):
        if self.selected_dvle is None: return
        c = self.parser.dvles[self.selected_dvle]['constants'][self.selected_const]
        new_raw = [0]*4
        try:
            for i in range(4):
                if c['type']==2: new_raw[i] = float_to_pica24(float(self.vars[i].get()))
                else: new_raw[i] = int(self.vars[i].get())
            self.parser.update_value(self.selected_dvle, self.selected_const, new_raw)
            self.refresh_tree()
            self.tree.selection_set(f"{self.selected_dvle}_{self.selected_const}")
        except ValueError: messagebox.showerror("Error", "Invalid Number")

if __name__ == "__main__":
    App().mainloop()