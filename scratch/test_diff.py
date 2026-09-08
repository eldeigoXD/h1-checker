import re
from difflib import SequenceMatcher

def highlight_missing_chunk(chunk, full_page_text):
    page_sentences = [s.strip() for s in re.split(r'(?<=[.!?\n])\s+', full_page_text) if len(s.strip()) > 10]
    chunk_words = set(chunk.lower().split())
    
    best_match = None
    best_score = 0
    if chunk_words and page_sentences:
        for s in page_sentences:
            s_words = set(s.lower().split())
            if not s_words: continue
            overlap = len(chunk_words.intersection(s_words))
            score = overlap / len(chunk_words) # simple coverage
            if score > best_score:
                best_score = score
                best_match = s
                
    if not best_match or best_score < 0.2:
        return [{'text': chunk, 'status': 'missing'}]
        
    a = chunk.split()
    b = best_match.split()
    sm = SequenceMatcher(None, [w.lower() for w in a], [w.lower() for w in b])
    
    result = []
    for opcode, a0, a1, b0, b1 in sm.get_opcodes():
        if opcode == 'equal':
            result.append({'text': " ".join(a[a0:a1]), 'status': 'found'})
        elif opcode in ('delete', 'replace'):
            if a0 != a1:
                result.append({'text': " ".join(a[a0:a1]), 'status': 'missing'})
            
    return result

if __name__ == "__main__":
    chunk = "Welcome to Hometown Toyota in Ontario, where you can find great deals."
    page = "Welcome to Hometown Honda in Ontario. We have great deals on cars."
    
    res = highlight_missing_chunk(chunk, page)
    print(res)
