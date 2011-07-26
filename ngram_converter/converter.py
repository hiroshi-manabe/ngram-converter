#!/usr/bin/env python
# coding: utf-8

import marisa
import mmap
import os
import struct
import sys

kBOSString = '<s>'
kEOSString = '</s>'
kUnknownString = 'UNK'
kScoreSize = 1  # sizeof(unsigned char)
kRecordSize = kScoreSize * 2  # score and backoff score
kPackString = 'B'  # unsigned char
kScoreMax = (256 ** kScoreSize) - 1
kScoreFactor = kScoreMax / -7  # e ** -7 is small enough as a probability

def PackScores(scores):
    def ConvertScore(s):
        s *= kScoreFactor
        if s < 0:
            s = 0
        elif s > kScoreMax:
            s = kScoreMax
        return s

    return struct.pack(kPackString * 2, *(ConvertScore(s) for s in scores))


def UnpackScores(byte_seq):
    scores = struct.unpack(kPackString * 2, byte_seq)
    return (s * kScoreFactor for s in scores)


class MMapStore(object):
    def __init__(self, filename, record_size, record_num = 0, is_writing = False):
        self.record_size = record_size
        self.is_writing = is_writing
        if is_writing and record_num == 0:
            raise ValueError

        if is_writing:
            self.fp = open(filename, 'wb')
            self.fp.write('\0' * record_size * record_num)
            self.fp.close()
            self.fp = open(filename, 'r+b')
            self.mmap = mmap.mmap(self.fp.fileno(), 0, access=mmap.ACCESS_WRITE)

        else:
            self.fp = open(filename, 'rb')
            self.mmap = mmap.mmap(self.fp.fileno(), 0, access=mmap.ACCESS_READ)

    def WriteRecord(self, record_no, record):
        if not self.is_writing:
            raise TypeError
        self.mmap[record_no * self.record_size:
                  (record_no + 1) * self.record_size] = record

    def ReadRecord(self, record_no):
        return self.mmap[record_no * self.record_size:
                         (record_no + 1) * self.record_size]

    def Close(self):
        self.mmap.close()
        self.fp.close()


class Pair(object):
    def __init__(self, src_str, dst_str, start_pos, end_pos):
        self.src_str = src_str
        self.dst_str = dst_str
        self.start_pos = start_pos
        self.end_pos = end_pos

    def __str__(self):
        if self.dst_str == '':
            return self.src_str
        elif self.src_str == kUnknownString:
            return kUnknownString
        else:
            return self.src_str.encode('utf-8') + '/' + self.dst_str.encode('utf-8')


class LM(object):
    kLookupTrieExt = '.lookup'
    kPairTrieExt = '.pair'
    kNgramTrieExt = '.ngram'
    kNgramScoresExt = '.scores'

    def BuildDics(self, dicname_prefix, vocab_file, lm_file):
        print 'Started loading vocabulary...'

        keyset_lookup = marisa.Keyset()
        keyset_pair = marisa.Keyset()

        fin = open(vocab_file, 'r')
        for line in fin:
            line = line.rstrip()
            elems = line.split('/')
            if len(elems) == 2:
                (lookup, rest) = elems
                keyset_lookup.push_back(lookup)

            keyset_pair.push_back(line)

        fin.close()
        print 'Loaded vocabulary.'
        
        trie_lookup = marisa.Trie()
        trie_lookup.build(keyset_lookup)
        trie_lookup.save(dicname_prefix + self.kLookupTrieExt)

        trie_pair = marisa.Trie()
        trie_pair.build(keyset_pair)
        trie_pair.save(dicname_prefix + self.kPairTrieExt)

        keyset_ngram = marisa.Keyset()

        fin_lm = open(lm_file, 'r')
        print 'Started loading ngram strings...'

        for line in fin_lm:
            line = line.rstrip()
            elems = line.split('\t')
            if len(elems) < 2:
                continue

            pairs = elems[1].split(' ')
            pairs.reverse()
            keyset_ngram.push_back(' '.join(pairs) + ' ')
        fin_lm.close()
        print 'Loaded ngram strings.'
        ngram_size = keyset_ngram.num_keys()

        trie_ngram = marisa.Trie()
        trie_ngram.build(keyset_ngram)
        trie_ngram.save(dicname_prefix + self.kNgramTrieExt)

        fin_lm = open(lm_file, 'r')
        agent = marisa.Agent()

        ngram_scores = MMapStore(dicname_prefix + self.kNgramScoresExt,
                                 kRecordSize,
                                 ngram_size,
                                 is_writing = True)

        print 'Started loading ngram scores...'
        count = 0
        for line in fin_lm:
            line = line.rstrip()
            elems = line.split('\t')

            if len(elems) < 2:
                continue
            elif len(elems) == 2:
                elems.append('')

            pairs = elems[1].split(' ')
            pairs.reverse()
            agent.set_query(' '.join(pairs) + ' ')
            trie_ngram.lookup(agent)
            id = agent.key_id()
            score = float(elems[0])
            backoff_score = float(elems[2]) if elems[2] != '' else 0
            ngram_scores.WriteRecord(id, PackScores((score, backoff_score)))
        
        ngram_scores.Close()
        fin_lm.close()

        print 'Loaded ngram scores.'
        return

    def LoadDics(self, dicname_prefix, order):
        if order <= 0:
            raise ValueError
        self.order = order
        self.trie_lookup = marisa.Trie()
        self.trie_lookup.load(dicname_prefix + self.kLookupTrieExt)

        self.trie_pair = marisa.Trie()
        self.trie_pair.load(dicname_prefix + self.kPairTrieExt)

        self.trie_ngram = marisa.Trie()
        self.trie_ngram.load(dicname_prefix + self.kNgramTrieExt)

        self.ngram_scores = MMapStore(dicname_prefix + self.kNgramScoresExt,
                                      kRecordSize,
                                      is_writing = False)
        return

    def GetNgramScores(self, ngram_list, prev_backoff_scores):
        ngram_str = ' '.join(str(x) for x in ngram_list) + ' '
        agent = marisa.Agent()
        agent.set_query(ngram_str)
        backoff_scores = []
        max_n = 0
        max_n_score = 0.0
        score = 0.0
        while self.trie_ngram.common_prefix_search(agent):
            ngram_str = agent.key_str()
            id = agent.key_id()
            (ngram_score, ngram_backoff) = UnpackScores(
                self.ngram_scores.ReadRecord(id))
                
            n = ngram_str.count(' ')
            if n > max_n:
                max_n = n
                max_n_score = ngram_score

        for i in reversed(range(max_n - 1, len(prev_backoff_scores))):
            score += prev_backoff_scores[i]

        score += max_n_score
        if max_n == self.max_n:
            max_n -= 1

        return (score, max_n, backoff_scores)

    def GetPairsAt(self, src_str, start_pos):
        agent_lookup = marisa.Agent()
        agent_pair = marisa.Agent()
        agent_lookup.set_query(src_str[start_pos:].encode('utf-8'))
        count = 0

        while self.trie_lookup.common_prefix_search(agent_lookup):
            agent_pair.set_query(agent_lookup.key_str() + '/')
            while self.trie_pair.predictive_search(agent_pair):
                (src, dst) = (x.decode('utf-8') for x in agent_pair.key_str().split('/'))
                count += 1
                yield Pair(src, dst, start_pos, start_pos + len(src))

        if count == 0:
            yield Pair(kUnknownString, src_str[start_pos], start_pos, start_pos + 1)

    def __init__(self):
        self.max_n = 0
        self.trie_lookup = None
        self.trie_pair = None
        self.trie_ngram = None
        self.fp_scores = None
        self.mmap_scores = None


class PairManager(object):
    def __init__(self, lm):
        self.lm = lm
        self.pairs = []

    def Build(self, src):
        for pos in range(len(src)):
            self.pairs.append(self.lm.GetPairsAt(src, pos))
        self.pairs.append([Pair(kEOSString, '', len(src) + 1, -1)])

    def GetPairsAt(self, pos):
        return self.pairs[pos]


class Node(object):
    def __init__(self, pair, left_node, valid_n, score):
        self.pair = pair
        self.left_node = left_node
        self.score = score
        self.valid_n = valid_n
        self.backoff_scores = []

    def GetNgramList(self):
        ngram_list = []
        current_node = self
        for i in range(self.valid_n):
            ngram_list.append(current_node.pair)
            current_node = current_node.left_node
        return ngram_list

    def GetHashKey(self):
        return tuple(str(x) for x in self.GetNgramList())

    def GetEndPos(self):
        return self.pair.end_pos

    def GetDstStr(self):
        return self.pair.dst_str


class Lattice(object):
    def __init__(self):
        self.end_nodes = {}

    def AddNode(self, node):
        hash_key = node.GetHashKey()
        end_pos = node.GetEndPos()
        cur_best_node = self.end_nodes.setdefault(end_pos, {}).get(hash_key)
        if not cur_best_node or node.score > cur_best_node.score:
            self.end_nodes[end_pos][hash_key] = node

    def GetEndNodesAt(self, pos):
        if pos in self.end_nodes:
            return self.end_nodes[pos].itervalues()
        else:
            return []


class Converter(object):
    def __init__(self, lm):
        self.lm = lm

    def Convert(self, src):
        lattice = Lattice()
        pair_manager = PairManager(self.lm)
        pair_manager.Build(src)
        start_pair = Pair(kBOSString, '', -1, 0)
        start_node = Node(start_pair, None, 1, 0)
        lattice.AddNode(start_node)

        for pos in range(len(src) + 1):
            for pair in pair_manager.GetPairsAt(pos):
                for left_node in lattice.GetEndNodesAt(pos):
                    ngram_list = [pair] + left_node.GetNgramList()
                    (score, valid_n, backoff_scores) = self.lm.GetNgramScores(ngram_list,
                                                                              left_node.backoff_scores)
                    node = Node(pair, left_node, valid_n, left_node.score + score)
                    lattice.AddNode(node)

        best_end_node = None
        for end_node in lattice.GetEndNodesAt(-1):
            if best_end_node is None or end_node.score > best_end_node.score:
                best_end_node = end_node

        dst_str_list = []
        node = best_end_node
        while node:
            dst_str_list.append(node.GetDstStr())
            node = node.left_node

        return ''.join(reversed(dst_str_list))


def main():
    print 'A converter class.'
    exit(0)


if __name__ == '__main__':
    main()
