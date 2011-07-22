import ngram_converter.converter

import getopt
import sys

def Usage():
    print 'build_dics.py - build dictionaries for Kana-Kanji or Kanji-Kana conversion..'
    print 'Usage: build_dics.py ' \
          '--dicname-prefix=<prefix for the dictionary files> ' \
          '[--lm=<lm_file>] [--vocab=<vocab_file>'
    print 'Dictionary files with the designated prefix and the extensions ' \
          '".lookup", ".pair", ".ngram" and ".ngram_dic" will be generated.'
    exit(-2)

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], '',
                                   ['dicname-prefix=', 'vocab=', 'lm='])
    except getopt.GetoptError:
        Usage()
        sys.exit(2)

    dicname_prefix = ''
    lm_file = ''
    vocab_file = ''

    for k, v in opts:
        if k == '--dicname-prefix':
            dicname_prefix = v
        elif k == '--vocab':
            vocab_file = v
        elif k == '--lm':
            lm_file = v


    if dicname_prefix == '':
        Usage()

    lm = ngram_converter.converter.LM()
    lm.BuildDics(dicname_prefix, vocab_file, lm_file)

    print 'Finished.'

if __name__ == '__main__':
    main()
