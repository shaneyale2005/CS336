import time
import regex as re
import pickle
import os
import functools
import numpy as np
from abc import ABC
import multiprocessing
from encoder import Encoder
from collections.abc import Iterable, Iterator
from cs336_basics.pretokenization import find_chunk_boundaries

PAT = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"""


encoderInstance: Encoder = None

class Tokenizer(ABC):
    """Abstract interface for a tokenizer."""
    vocab: dict[int, bytes]
    inv_vocab: dict[bytes, int]
    special_tokens_pattern: str | None
    eos_id: int

    def __init__(self, vocab: dict[int, bytes], merges: list[tuple[bytes, bytes]], special_tokens: list[str] | None = None):
        self.vocab = vocab
        self.merges = merges
        self.special_tokens = special_tokens
        self.inv_vocab = {}
        for k, v in vocab.items():
            self.inv_vocab[v] = k

        self.special_tokens_pattern = None
        self.eos_id = -1
        if special_tokens:
            if "<|endoftext|>" in special_tokens:
                self.eos_id = self.inv_vocab["<|endoftext|>".encode("utf-8")]
            self.special_tokens_pattern = "|".join(map(re.escape, sorted(special_tokens, key=len, reverse=True)))

    @classmethod
    def from_files(cls, vocab_filepath: str, merges_filepath: str, special_tokens: list[str] | None=None):
        with open(vocab_filepath, 'rb') as f:
            vocab = pickle.load(f)
            
        with open(merges_filepath, 'rb') as f:
            merges = pickle.load(f)
            
        return cls(vocab, merges, special_tokens)
    
    def encoder(self):
        global encoderInstance
        # 每个进程一份
        if encoderInstance is None:
            encoderInstance = Encoder(self.inv_vocab)
        return encoderInstance

    def encode(self, text: str) -> list[int]:
        tokens = []
        start = 0
        if self.special_tokens_pattern:
            for m0 in re.finditer(self.special_tokens_pattern, text):
                
                for match in re.finditer(PAT, text[start:m0.start()]):
                    tokens.extend(self.encoder()._encode(match.group()))
                tokens.append(self.inv_vocab[m0.group().encode("utf-8")])
                start = m0.end()

        if start < len(text):
            for match in re.finditer(PAT, text[start:]):
                tokens.extend(self.encoder()._encode(match.group()))
        return tokens
    
    def encode_chunk(self, chuck: tuple[int], input_path: str) -> list[int]:
        start, end = chuck
        with open(input_path, "rb") as f:
            f.seek(start)
            chunk = f.read(end - start).decode("utf-8", errors="ignore")
            return self.encode(chunk)
        return None
    
    def encode_file(self, input_path: str, output_path: str, num_split: int = 4, num_processes: int = 1) -> None:
        boundaries = []
        with open(input_path, "rb") as f:
            boundaries = find_chunk_boundaries(
                f, num_split, "<|endoftext|>".encode("utf-8"))
        
        all_token_ids = []
        t0 = time.time()
        with multiprocessing.Pool(processes=num_processes) as pool:
            results = pool.imap_unordered(
                    functools.partial(self.encode_chunk, input_path=input_path),
                    zip(boundaries[:-1], boundaries[1:]),
                )
            
            for res in results:
                all_token_ids.extend(res)

        t1 = time.time()

        print("encode_file: ", t1-t0)

        np.save(output_path, np.array(all_token_ids, dtype=np.uint16))

    def encode_iterable(self, iterable: Iterable[str]) -> Iterator[int]:
        for text in iterable:
            # Encode each string and yield all its token IDs
            for token_id in self.encode(text):
                yield token_id

    def decode(self, ids: list[int]) -> str:
        text_bytes = []
        for id in ids:
            text_bytes.append(self.vocab[id])
        return b''.join(text_bytes).decode('utf-8', errors='replace')
    
    def decode_raw(self, ids: list[int]) -> str:
        text_bytes = []
        for id in ids:
            text_bytes.append(self.vocab[id])
        return text_bytes

