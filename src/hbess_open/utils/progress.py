"""Optional progress-bar adapter; analysis remains usable without tqdm."""

try:
    from tqdm.auto import tqdm as tqdm
except ImportError:
    def tqdm(iterable, *args, **kwargs):
        del args, kwargs
        return iterable
