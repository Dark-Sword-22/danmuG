import os
import datetime
import jieba
import pprint
from collections import defaultdict
from gensim import corpora
from gensim import models
from gensim import similarities
from pipeit import *

jieba.load_userdict(os.path.abspath('./nlp/jieba_userdict.txt'))
STOPLIST = set('的,了,个,呢,呀,哈,哈哈,哈哈哈,哈哈哈哈,哈哈哈哈哈,哈哈哈哈哈哈,啦,？,?,！,，,(,),（,）,【,】, ~,",“,”,‘,’,—,-,。,.,啊,阿,吗,喂, '.split(','))

def split_string(string):
    return [_ for _ in jieba.lcut_for_search(string) if _ not in STOPLIST]

def load_processed_corpus_single_file(file_path, filter=False, debug=False):
    texts = (
        Read(file_path).split('\n')[6:] 
        | Map(lambda x:(split_string(x[22:]), x[22:]))
        | Filter(lambda x: x[0] != [])
        | list
    )
    if filter:
        frequency = defaultdict(int)
        for text, _ in texts:
            for token in text:
                frequency[token] += 1
        processed_corpus = [([token for token in text if frequency[token] > 1], source) for text, source in texts] | Filter(lambda x:len(x[0]) > 1) | list
        if debug: pprint.pprint(processed_corpus)
        return processed_corpus
    else:
        return texts

def flt_uncommon(processed_corpus):
    frequency = defaultdict(int)
    for text, _ in processed_corpus:
        for token in text:
            frequency[token] += 1
    processed_corpus = [([token for token in text if frequency[token] > 1], source) for text, source in processed_corpus] | Filter(lambda x:len(x[0]) > 1) | list
    return processed_corpus

def train_nlp_model(src_dir, file_name, passes = 5, file_count = 3):
    src_files = []
    for src_files in os.walk(src_dir):
        src_files = (
            src_files[2] 
            | Filter(lambda x:x[:5] == 'danmu' and os.path.splitext(x)[1] == '.txt') 
            | Map(lambda x: os.path.join(src_dir, x))
            | Filter(lambda x: os.stat(x).st_size >= 1024) 
            | list
        ); break
    src_files.sort(key = lambda x:datetime.datetime.strptime(os.path.split(x)[1][6:6+19], '%Y-%m-%d-%H-%M-%S'), reverse = True)
    
    file_path = os.path.join(src_dir, file_name)

    processed_corpus = []
    snake_idx, count, positive = 0, 0, -1
    if file_path in src_files:
        processed_corpus.extend(load_processed_corpus_single_file(file_path))
        snake_idx = src_files.index(file_path)
        src_files.remove(file_path)
        count += 1
    
    while count < file_count:
        snake_idx= snake_idx - 1 if positive % 3==1 else -snake_idx
        positive += 1
        count += 1
        try:
            processed_corpus.extend(load_processed_corpus_single_file(src_files))
            count += 1
        except:
            ...
    processed_corpus = flt_uncommon(processed_corpus)

    dictionary = corpora.Dictionary(processed_corpus | Map(lambda x:x[0]))
    bow_corpus = [dictionary.doc2bow(text) for text, _ in processed_corpus]
    lda = models.LdaModel(bow_corpus, id2word=dictionary, num_topics=100, passes = passes)
    index = similarities.SparseMatrixSimilarity(lda[bow_corpus], num_features=120)
    return processed_corpus, lda, index, dictionary

def string_query(string, require_num, taged, processed_corpus, model, index, dictionary):
    query_bow = dictionary.doc2bow(split_string(string))
    sims = index[model[query_bow]]
    sims_top = sorted(enumerate(sims), key=lambda x: x[1], reverse=True)[:require_num * 2]
    if len(sims_top) < require_num * 2:
        raise 
    documents_top = [processed_corpus[document_number][1] for document_number, score in sims_top]
    res = list(set(documents_top))
    res.sort(key = documents_top.index)
    if taged:
        res = ' '.join(res[:require_num] | Map(lambda x:f"#{x}#"))
    else:
        res = ', '.join(res[:require_num] | Map(lambda x:f"#{x}"))
    return res