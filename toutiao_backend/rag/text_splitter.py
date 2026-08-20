from typing import List


def split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        if end < text_length:
            last_period = text.rfind('。', start, end)
            last_comma = text.rfind('，', start, end)
            last_space = text.rfind(' ', start, end)
            
            split_pos = max(last_period, last_comma, last_space)
            if split_pos > start + chunk_overlap:
                end = split_pos + 1
        chunks.append(text[start:end].strip())
        start = end - chunk_overlap
    
    return chunks