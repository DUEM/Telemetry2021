"""Split a raw capture into CAN frames.

The board writes each frame as

    [millis 4B LE][CAN ID 2B BE][DLC 1B][data, DLC bytes][CRC16 2B BE][0x7E]

The end of frame marker 0x7E is not escaped, so a 0x7E byte inside a frame
(in the timestamp, data or CRC) splits it into two or more pieces. Splitting
on 0x7E alone loses those frames: each piece fails the CRC check.

`FrameAssembler` puts them back together. A piece that is not a complete frame
is re-joined, with the 0x7E it was split on, to the pieces after it until the
result has the length its DLC declares and a valid CRC. A piece that is itself
a complete frame is never absorbed into a join. A piece that cannot be
completed is passed on unchanged, so the parser still reports it as a CRC
failure (or DLC mismatch), exactly as before.
"""

from crccheck.crc import Crc16Modbus

END_OF_FRAME_MARKER = b"\x7E"

# millis (4) + CAN ID (2) + DLC (1) + CRC (2), plus up to 8 data bytes
FRAME_OVERHEAD = 9
MAX_FRAME_LENGTH = FRAME_OVERHEAD + 8


def frame_is_complete(frame: bytes) -> bool:
    """True if `frame` has the length its DLC declares and a valid CRC."""
    return (
        FRAME_OVERHEAD <= len(frame) <= MAX_FRAME_LENGTH
        and len(frame) == FRAME_OVERHEAD + frame[6]
        and Crc16Modbus.calc(frame[:-2]) == int.from_bytes(frame[-2:], "big")
    )


class FrameAssembler:
    """Re-join frames split by an unescaped end of frame marker.

    Feed it the pieces between markers, in order, with `push`; it returns the
    frames that are ready. Call `flush` at the end of the stream to get any
    pieces still held back. Works the same for a whole file or a live serial
    stream; a piece is held only until enough later pieces have arrived to
    decide.
    """

    def __init__(self):
        self._pending: list[bytes] = []  # an incomplete piece and the pieces after it
        self.rejoined = 0  # frames recovered by re-joining

    def push(self, piece: bytes) -> list[bytes]:
        """Add the next piece; return the frames that are now ready, in order."""
        piece = bytes(piece)
        if frame_is_complete(piece):
            ready = self._drain(final=True)
            ready.append(piece)
            return ready
        self._pending.append(piece)
        return self._drain(final=False)

    def flush(self) -> list[bytes]:
        """End of stream: return everything still held back."""
        return self._drain(final=True)

    def _drain(self, final: bool) -> list[bytes]:
        ready = []
        while self._pending:
            joined = self._pending[0]
            for k in range(1, len(self._pending)):
                joined += END_OF_FRAME_MARKER + self._pending[k]
                if len(joined) > MAX_FRAME_LENGTH:
                    break
                if frame_is_complete(joined):
                    ready.append(joined)
                    self.rejoined += 1
                    self._pending = self._pending[k + 1:]
                    break
            else:
                # No join completed. Wait if one more piece could still fit.
                if not final and len(joined) < MAX_FRAME_LENGTH:
                    return ready
                ready.append(self._pending.pop(0))  # give up on this piece
                continue
            if len(joined) > MAX_FRAME_LENGTH:
                ready.append(self._pending.pop(0))
        return ready


def read_frames(hex_file) -> list:
    """Read a capture file and return the CAN frames in it.

    Frames split by a 0x7E inside them are re-joined (see `FrameAssembler`).

    Args:
        hex_file: path to the .BIN capture

    Returns:
        The frames, with the end of frame marker removed. Pieces that could
        not be made into a complete frame are returned as they are.
    """
    with open(hex_file, mode="rb") as file:
        pieces = file.read().split(END_OF_FRAME_MARKER)
    assembler = FrameAssembler()
    frames = []
    for piece in pieces:
        frames.extend(assembler.push(piece))
    frames.extend(assembler.flush())
    return frames
