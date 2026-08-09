"""Split a raw capture into CAN frames.

The xBee writes frames back to back separated by a single end of frame marker,
so framing is currently one split. This lives on its own so a more involved
strategy (escaped markers, length prefixes, resync after a corrupt frame) can
replace it without touching the callers.
"""

END_OF_FRAME_MARKER = b"\x7E"


def read_frames(hex_file) -> list:
    """Read a capture file and return the CAN frames in it.

    Args:
        hex_file: path to the .BIN capture

    Returns:
        The frames, with the end of frame marker removed.
    """
    with open(hex_file, mode="rb") as file:
        return bytearray().join(file.readlines()).split(END_OF_FRAME_MARKER)
