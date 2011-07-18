#!/usr/bin/python
# -*- coding: utf-8 -*-

import codecs
import getopt
import os
import sys

def Usage():
    print sys.argv[0] + ' - convert <n>-gram.fwk to SRILM format.'
    print 'Usage: '  + sys.argv[0] + '-n <ngram-order> -o <output-filename> ' \
          '[-r] [-e <input-encoding>]'
    print 'Input files are <n>-gram.fwk distributed' \
          ' at http://plata.ar.media.kyoto-u.ac.jp/gologo/lm.html.'
    print 'Input files should be present in the current directory.'
    print 'UTF-8 will be used for input if <input-encoding> is not specified; '
    print 'UTF-8 will always be used for output.'
    print '-r: reverse Kana and Kanji (output will be Kana/Kanji).'

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hrn:o:e:')
    except getopt.GetoptError:
        Usage()
        sys.exit(2)

    n = 0
    input_encoding = 'utf-8'
    output_filename = ''
    reverse = False

    for k, v in opts:
        if k == '-h':
            usage()
            sys.exit()
        elif k == '-e':
            input_encoding = v
        elif k == '-n':
            n = int(v)
        elif k == '-o':
            output_filename = v
        elif k == '-r':
            reverse = True

    if output_filename == '':
        Usage()

    f_out = codecs.open(output_filename, 'w', 'utf-8')
    for i in range(1, n + 1):
        f_in = codecs.open(str(i) + '-gram.fwk', 'r', input_encoding)
        print 'Processing %d-gram...' % i
        for line in f_in:
            line = line.rstrip('\n')
            line = line.strip(' ')
            fields = line.split(' ')
            if reverse:
                for j in range(1, len(fields)):
                    fields[j] = '/'.join(reversed(fields[j].split('/')))

            if fields[1] == 'BT':
                fields[1] = '<s>'
            if len(fields) > 3 and fields[2] == 'BT':
                continue
            if fields[-1] == 'BT':
                fields[-1] = '</s>'

            f_out.write(' '.join(fields[1:] + fields[0:1]) + '\n')
            if i == 1 and fields[1] == '<s>':
                f_out.write('</s>' + ' ' + fields[0] + '\n')

        f_in.close()
        print 'Done.'

    f_out.close()

if __name__ == '__main__':
    main()
