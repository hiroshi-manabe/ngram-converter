#!/usr/bin/python
# -*- coding: utf-8 -*-

import ngram_converter.converter

import getopt
import sys

def Usage():
    print 'converter_sample.py - convert Kana to Kanji or vice versa.'
    print 'Usage: converter_sample.py ' \
          '--order=<order> --dicname-prefix=<prefix for the dictionary files> ' \
          '[--interactive]'
    print 'If --interactive option is supplied, this program will prompt the user ' \
          'to type input strings and print the conversion results each time.'
    print 'Otherwise, it will read input strings from the standard input and output the ' \
          'results to the standard output.'
    exit(-2)


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], '',
                                   ['order=', 'dicname-prefix=', 'interactive'])
    except getopt.GetoptError:
        Usage()
        sys.exit(2)

    order = 0
    dicname_prefix = ''
    interactive = False

    for k, v in opts:
        if k == '--order':
            order = v
        elif k == '--dicname-prefix':
            dicname_prefix = v
        elif k == '--interactive':
            interactive = True

    if dicname_prefix == '' or order == 0:
        Usage()


    order = 0
    dicname_prefix = ''
    interactive = False

    for k, v in opts:
        if k == '--order':
            order = v
        elif k == '--dicname-prefix':
            dicname_prefix = v
        elif k == '--interactive':
            interactive = True

    if dicname_prefix == '' or order == 0:
        Usage()

    lm = ngram_converter.converter.LM()
    lm.LoadDics(dicname_prefix, order)
    converter = ngram_converter.converter.Converter(lm)

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
