from base64 import b64encode, b64decode
from typing import Any, List

from celery.canvas import signature, chain


def read_chunk(filename: str, offset: int, step: int, delimiter: str = "\n"):
    """
    A custom file iterator that doesn't rely on in-memory python objects
    This can read given file in chunks
    Each chunk starts at given offset and reads `step` number of bytes
    Then, everything after the last `delimiter` occurence is trimmed off

    By default, a chunk ends at the latest occurence of a newline character

    Params
    ------
    filename: str
        Name of the file to read from
    offset: int
        Byte offset, relative to start of the file, to start reading from
    step: int
        Maximum number of bytes to read - i.e maximum chunk size
    delimiter: str
        The delimiter character to stop at, defaults to newline

    Returns
    ------
    (next_offset: int, content: str)
        A Tuple containing the next offset to continue reading from, and the content read

    Example
    -------
    Given the file-
    ```
    Foo
    Bar
    Baz
    Qux
    ```
    `read_chunk('filename.txt', 0, 5)` results in `(4, 'Foo\n')`
    Now using the `4` as next offset, `read_chunk('filename.txt', 4, 5)` results in
    `Bar`
    If we did `read_chunk('filename.txt', 0, 10)`, that'd result in `(12, 'Bar\nBaz\n')`
    And it can continue from 12 and so on

    When the file has reached EOF, `read_chunk` will return an empty string as the second element of
    the tuple
    """
    with open(filename, "rb") as f:
        # Seek to the given offset (starting from beginning - i.e 0)
        f.seek(offset, 0)
        # Read step number of bytes from file
        content = f.read(step)
    if content == "":
        # Reached EOF - return same offset and empty content
        return (offset, "")
    # Try finding the `delimiter` byte closest to the end
    for i, b in enumerate(reversed(content)):
        if b == ord(delimiter):
            break
    else:
        # No `delimiter` found - possibly the first line of file
        i = 0
    content_len = len(content)
    """
    The position to "break" at (i.e start reading from on next call)
    should be (given offset + number of bytes read) - (offset of `delimiter` byte from
    the end of the read content)
    """
    breakpos = offset + content_len - i
    """
    Return the new breakpos to continue reading from, and the read content
    Trim off everything after the last `delimiter` from content (that should be part of
    the next read) and decode it to utf-8
    """
    return (breakpos, content[: -i or content_len].decode("utf-8"))


def chunks_of(ls: List[Any], n: int):
    # Divide a list `ls`, into `n` chunks of roughly equal size
    k, m = divmod(len(ls), n)
    return [ls[i * k + min(i, m) : (i + 1) * k + min(i + 1, m)] for i in range(n)]


def b64encode_id(_id: int):
    # Encode an int id to base64 string
    return b64encode(str(_id).encode("utf-8")).decode("utf-8")


def b64decode_id(b64_id: str):
    # Decode a base64 string to int id
    return int(b64decode(b64_id).decode("utf-8"))


def deserialize_chain(serialized_ch: List[dict]):
    # Build task signatures from list of dicts (serialized json)
    return chain(signature(x) for x in serialized_ch)
