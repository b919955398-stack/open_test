"""Caption formatting retained from the supplied appendix workflow."""


def caption_preprocessor(caption: str) -> str:
    return caption.replace("_", " ")
