import ctypes
import struct
from pathlib import Path
import mpq_split as mpq
storm = mpq.Storm(Path(__file__).with_name('stormlib')/'x64/StormLib.dll')


def read(archive, name):
    handle = ctypes.c_void_p()
    if not storm.lib.SFileOpenFileEx(archive, name.encode('ascii'), 0, ctypes.byref(handle)):
        raise FileNotFoundError(name)
    try:
        high, count = ctypes.c_uint32(), ctypes.c_uint32()
        size = storm.lib.SFileGetFileSize(handle, ctypes.byref(high))
        if high.value or size > 64*1024*1024:
            raise ValueError('Asset size out of bounds')
        output = ctypes.create_string_buffer(size)
        if not storm.lib.SFileReadFile(handle, output, size, ctypes.byref(count), None) or count.value != size:
            raise OSError('Asset read failed: '+name)
        return output.raw
    finally:
        storm.lib.SFileCloseFile(handle)


def frames(data):
    version, flags, encoding, termination, directions, count = struct.unpack_from('<6I',data)
    if version != 6 or directions*count > 10000:
        raise ValueError('Unsupported DC6')
    result = []
    for index in range(directions*count):
        pointer = struct.unpack_from('<I',data,24+4*index)[0]
        flip,width,height,offset_x,offset_y,unknown,following,length = struct.unpack_from('<3I2i3I',data,pointer)
        if not 0 < width <= 4096 or not 0 < height <= 4096:
            raise ValueError('DC6 dimensions out of bounds')
        pixels = bytearray(width*height)
        alpha = bytearray(width*height)
        column, row = 0, 0
        stream = memoryview(data)[pointer+32:pointer+32+length]
        cursor = 0
        while cursor < len(stream) and row < height:
            command = stream[cursor]
            cursor += 1
            if command == 128:
                row += 1
                column = 0
            elif command & 128:
                column += command & 127
            else:
                if column+command > width or cursor+command > len(stream):
                    raise ValueError('Invalid DC6 run')
                line = row if flip else height-row-1
                start = line*width+column
                pixels[start:start+command] = stream[cursor:cursor+command]
                alpha[start:start+command] = b'\xff'*command
                cursor += command
                column += command
        result.append((width,height,offset_x,offset_y,bytes(pixels),bytes(alpha)))
    return result


