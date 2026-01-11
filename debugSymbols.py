import struct
import os

def debug_shbin_symbols(filename):
    with open(filename, 'rb') as f:
        data = bytearray(f.read())

    magic = data[0:4].decode('ascii', errors='ignore')
    if magic != 'DVLB':
        print("Not a valid DVLB")
        return

    n_dvles = struct.unpack('<I', data[4:8])[0]
    dvle_offsets = [struct.unpack('<I', data[8 + i*4 : 12 + i*4])[0] for i in range(n_dvles)]

    for idx, dvle_off in enumerate(dvle_offsets):
        print(f"\n--- DVLE {idx} (Start Offset: {hex(dvle_off)}) ---")
        
        # Table Offsets from GBATEK documentation
        input_rel_off = struct.unpack('<I', data[dvle_off+0x30:dvle_off+0x34])[0]
        input_count   = struct.unpack('<I', data[dvle_off+0x34:dvle_off+0x38])[0]
        sym_rel_off   = struct.unpack('<I', data[dvle_off+0x38:dvle_off+0x3C])[0]
        
        input_abs_off = dvle_off + input_rel_off
        sym_abs_off   = dvle_off + sym_rel_off

        print(f"Input Register Table: {hex(input_abs_off)} ({input_count} entries)")
        print(f"Symbol Table Base:    {hex(sym_abs_off)}")

        for i in range(input_count):
            entry_off = input_abs_off + (i * 8)
            # 000h 4: Name Offset (in Symbol Table)
            # 004h 2: Register Start
            name_offset_in_sym = struct.unpack('<I', data[entry_off : entry_off+4])[0]
            reg_start = struct.unpack('<H', data[entry_off+4 : entry_off+6])[0]
            
            # The actual location of the string in the file
            actual_string_ptr = sym_abs_off + name_offset_in_sym
            
            # Read null-terminated string
            name_chars = []
            ptr = actual_string_ptr
            while ptr < len(data) and data[ptr] != 0:
                name_chars.append(chr(data[ptr]))
                ptr += 1
            name_found = "".join(name_chars)

            print(f"  Entry {i}: Reg {hex(reg_start)} -> Name Offset {hex(name_offset_in_sym)} -> File Address {hex(actual_string_ptr)}: '{name_found}'")

if __name__ == "__main__":
    debug_shbin_symbols("SpriteShader.shbin")