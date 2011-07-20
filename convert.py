#!/usr/bin/python
# -*- coding: utf-8 -*-

import codecs
import getopt
import marisa
import mmap
import os
import struct
import sys

kBOSString = '<s>'
kEOSString = '</s>'
kScoreSize = 2  # sizeof(unsigned short)
kPackString = 'H'  # unsigned short
kScoreMax = 256 ** kScoreSize - 1
kScoreFactor = kScoreMax / -20  # e ** -20 is small enough as a probability

def PackScore(orig_score):
    score = orig_score * kScoreFactor
    if score < 0:
        score = 0
    if score > kScoreMax:
        score = kScoreMax
    return struct.pack(kPackString, score)


class Pair(object):
    def __init__(self, src_str, dst_str, start_pos, end_pos):
        self.src_str = src_str
        self.dst_str = dst_str
        self.start_pos = start_pos
        self.end_pos = end_pos

    def __str__(self):
        if self.dst_str == '':
            return self.src_str
        else:
            return self.src_str + '/' + self.dst_str

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

        self.trie_lookup.build(keyset_lookup)
        self.trie_lookup.save(dicname_prefix + self.kLookupTrieExt)

        self.trie_pair.build(keyset_pair)
        self.trie_pair.save(dicname_prefix + self.kPairTrieExt)

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

        self.trie_ngram.build(keyset_ngram)
        self.trie_ngram.save(dicname_prefix + self.kNgramTrieExt)

        fin_lm = open(lm_file, 'r')
        agent = marisa.Agent()
        fout_scores = open(dicname_prefix + self.kNgramScoresExt, 'wb')
        fout_scores.write('\0' * ngram_size * kScoreSize * 2)
        fout_scores.close()
        fout_scores = open(dicname_prefix + self.kNgramScoresExt, 'r+b')
        mmap_scores = mmap.mmap(fout_scores.fileno(), 0)

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
            self.trie_ngram.lookup(agent)
            id = agent.key_id()
            score = float(elems[0])
            backoff = float(elems[2]) if elems[2] != '' else 0
            mmap_scores[id * 2 * kScoreSize:
                        (id * 2 + 1) * kScoreSize] = PackScore(score)
            mmap_scores[(id * 2 + 1) * kScoreSize:
                        (id * 2 + 2) * kScoreSize] = PackScore(backoff)
        
        mmap_scores.close()
        fout_scores.close()
        print 'Loaded ngram scores.'
        return

    def LoadDics(self, dicname_prefix):
        self.trie_lookup.load(dicname_prefix + self.kLookupTrieExt)
        self.trie_pair.load(dicname_prefix + self.kPairTrieExt)
        self.trie_ngram.load(dicname_prefix + self.kNgramTrieExt)
        self.fp_scores = open(dicname_prefix + self.kNgramScoresExt, 'rb')
        self.mmap_scores = mmap.mmap(self.fp_scores.fileno(), 0, prot=mmap.PROT_READ)
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
            if ngram_str[-1] != ' ':
                continue
            id = agent.key_id()
            (ngram_score, ngram_backoff) = struct.unpack(
                kPackString * 2,
                self.mmap_scores[id * 2 * kScoreSize:
                                 (id * 2 + 2) * kScoreSize])
            ngram_score *= kScoreFactor
            ngram_backoff *= kScoreFactor
                
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
        agent_lookup.set_query(src_str[start_pos:])
        while self.trie_lookup.common_prefix_search(agent_lookup):
            agent_pair.set_query(agent_lookup.key_str() + '/')
            while self.trie_pair.predictive_search(agent_pair):
                (src, dst) = agent_pair.key_str().split('/')
                yield Pair(src, dst, start_pos, start_pos + len(src))

    def __init__(self, max_n, dicname_prefix, vocab_file, lm_file, force_build = False):
        self.max_n = max_n
        self.trie_lookup = marisa.Trie()
        self.trie_pair = marisa.Trie()
        self.trie_ngram = marisa.Trie()
        self.fp_scores = None
        self.mmap_scores = None

        dic_exists = True if not force_build else False
        for ext in (self.kLookupTrieExt, self.kPairTrieExt, self.kNgramTrieExt,
                    self.kNgramScoresExt):
            if not os.path.isfile(dicname_prefix + ext):
                dic_exists = False

        if not dic_exists:
            self.BuildDics(dicname_prefix, vocab_file, lm_file)
        self.LoadDics(dicname_prefix)


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


def Usage():
    print 'convert.py - convert Kana to Kanji or vice versa.'
    print 'Usage: convert.py ' \
          '--order=<order> --dicname-prefix=<prefix for the dictionary files> ' \
          '[--lm=<lm_file>] [--vocab=<vocab_file>] [--force-build] ' \
          '[--interactive]'
    print 'Dictionary files with the designated prefix and the extensions ' \
          '".lookup", ".pair", ".ngram" and ".ngram_dic" will be generated.'
    print 'If there are files with these names, they will be loaded. In this case, ' \
          '--lm and --vocab options are not necessary and will be ignored.'
    print 'Use --force-build to ignore existing files and rebuild ' \
          'the dictionary files.'
    print 'If --interactive option is supplied, this program will prompt the user ' \
          'to type input strings and print the conversion results each time.'
    print 'Otherwise, it will read input strings from the standard input and output the ' \
          'results to the standard output.'
    exit(-2)


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], '',
                                   ['order=', 'dicname-prefix=', 'vocab=', 'lm=',
                                    'force-build', 'interactive'])
    except getopt.GetoptError:
        Usage()
        sys.exit(2)

    order = 0
    dicname_prefix = ''
    lm_file = ''
    vocab_file = ''
    force_build = False
    interactive = False

    for k, v in opts:
        if k == '--order':
            order = v
        elif k == '--dicname-prefix':
            dicname_prefix = v
        elif k == '--vocab':
            vocab_file = v
        elif k == '--lm':
            lm_file = v
        elif k == '--force-build':
            force_build = True
        elif k == '--interactive':
            interactive = True

    if dicname_prefix == '' or order == 0:
        Usage()

    lm = LM(order, dicname_prefix, vocab_file, lm_file, force_build)
    converter = Converter(lm)

    if interactive:
        while True:
            try:
                to_convert = raw_input('> ').rstrip('\n')
                print converter.Convert(to_convert)
            except EOFError:
                exit()
    else:
        for line in sys.stdin:
            to_convert = line.rstrip('\n')
            print converter.Convert(to_convert)

if __name__ == '__main__':
    main()
