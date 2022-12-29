import argparse
from datetime import datetime
import re
import sqlite3
import time
import unicodedata

TONE_SUBS = {
    '2': '\u0301',
    '3': '\u0300',
    '5': '\u0302',
    '7': '\u0304',
    '8': '\u030D',
    '9': '\u0306',
}

ROC_SUBS = [
    (r'ts', 'ch'),
    (r'ua', 'oa'),
    (r'ue', 'oe'),
    (r'oo', 'o\u0358'),
    (r'ing', 'eng'),
    (r'ik', 'ek'),
    (r'nn', '\u207F'),
]

ROC_SUBS_ASCII = [
    (r'ts', 'ch'),
    (r'ua', 'oa'),
    (r'ue', 'oe'),
    (r'oo', 'ou'),
    (r'ing', 'eng'),
    (r'ik', 'ek'),
]

def get_cursor(file):
    con = sqlite3.connect(file)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    return cur

def tone_index(text):
    match = re.match(r'o[ae][a-z]', text, re.I)
    if match is not None:
        return match.start() + 2
    else:
        for v in ['o', 'a', 'e', 'u', 'i', 'n', 'm']:
            index = text.find(v)
            if index > -1:
                return index + 1

def rojascii_to_pojascii(text):
    for sub in ROC_SUBS_ASCII:
        text = re.sub(sub[0], sub[1], text)
    return text

def rocascii_to_poj(text):
    text = unicodedata.normalize('NFD', text)
    for sub in ROC_SUBS:
        text = re.sub(sub[0], sub[1], text)
    tone = None
    if '235789'.find(text[-1]) > -1:
        tone = text[-1]
        text = text[:-1]
        index = tone_index(text)
        text = text[0:index] + TONE_SUBS[tone] + text[index:]
    return unicodedata.normalize('NFC', text)

def get_row_toj(row):
    orig = row[1]
    new = row[2]
    han = row[3]

    toj = ''
    i = 0

    for orig_chat in re.split(r'-+', orig):
        j = i + len(orig_chat)
        new_chat = new[i:j]
        if orig_chat == new_chat:
            if new_chat == '':
                print('empty')
            toj += rocascii_to_poj(new_chat)
            i += len(orig_chat)
            while i < len(new) and re.match(r'\W', new[i]):
                toj += new[i]
                i += 1
    return toj

def alpha_only(reading):
    return ''.join(ch for ch in reading if ch.isalpha())

def get_qstrings(reading):
    roc_reading = reading.lower()
    poj_reading = rojascii_to_pojascii(roc_reading)
    roc_alphas = alpha_only(roc_reading)
    poj_alphas = alpha_only(poj_reading)

    syls = re.split(r'-+', roc_reading)
    n_syls = len(syls)

    if n_syls == 1:
        return [poj_reading] if poj_reading == roc_reading else [poj_reading, roc_reading]
    if n_syls == 2:
        return [poj_alphas] if poj_alphas == roc_alphas else [poj_alphas, roc_alphas]
    else:
        roc_initials = ''
        poj_initials = ''
        for syl in syls:
            m = re.match(r'tsh?|[ptk]h', syl, re.IGNORECASE)
            init = syl[m.start():m.end()] if m is not None else syl[0]
            roc_initials += init
            poj_initials += init.replace('ts', 'ch')
        if poj_initials == roc_initials and poj_alphas == roc_alphas:
            return [poj_initials, poj_alphas]
        elif poj_initials == roc_initials and poj_alphas != roc_alphas:
            return [poj_initials, poj_alphas, roc_alphas]
        else:
            return [poj_initials, roc_initials, poj_alphas, roc_alphas]

def build_db(file, word_list, qstring_list):
    now = datetime.now()
    con = sqlite3.connect(file)
    con.executescript(f'''
        DROP TABLE IF EXISTS words;
        DROP TABLE IF EXISTS qstring_word_mappings;
        DROP TABLE IF EXISTS cooked_information;
        CREATE TABLE words (id INTEGER PRIMARY KEY, reading, value, probability);
        CREATE TABLE qstring_word_mappings (qstring, word_id);
        CREATE TABLE cooked_information (key, value);
        INSERT INTO cooked_information VALUES
            ('version_timestamp', '{now.strftime("%Y%m%d")}'),
            ('cooked_timestamp_utc', '{round(time.time(), 1)}'),
            ('cooked_datetime_utc', '{now.strftime("%Y-%m-%d %H:%M UTC")}');

        CREATE INDEX words_index_key ON words (reading);
        CREATE INDEX qstring_word_mappings_index_qstring ON qstring_word_mappings (qstring);
    ''')

    words_table = []
    qstrings_table = []

    for row in word_list:
        words_table.append((row['id'], row['reading'], row['value'], 1))
    
    for row in qstring_list:
        qstrings_table.append((row['qstring'], row['word_id']))

    c = con.cursor()
    c.executemany('INSERT INTO words VALUES (?, ?, ?, ?)', words_table)
    c.executemany('INSERT INTO qstring_word_mappings VALUES (?, ?)', qstrings_table)
    con.commit()

##############################################################################
#
# __main__
#
##############################################################################

parser = argparse.ArgumentParser(
    description="""Build FHL Database""",
    formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument('-i', "--input", metavar='FILE', required=False, help='csv input file')
parser.add_argument('-o', "--output", metavar='FILE', required=False, help='the output database file (TalmageOverride.db)')

def read_csv(filename):
    import csv
    with open(filename) as csvfile:
        reader = csv.reader(csvfile, delimiter='\t')
        return [row for row in reader]

if __name__ == '__main__':
    args = parser.parse_args()
    input_file = args.input if args.input else 'db2.csv'
    output_file = args.output if args.output else 'TalmageOverride.db'

    word_list = []
    qstring_list = []

    id = 1

    inputs = read_csv(input_file)
    for row in inputs:
        if not row:
            continue
        toj = get_row_toj(row)
        word_list.append({
            'id': id,
            'reading': row[1],
            'value': toj,
        })
        qstrings = get_qstrings(row[1])
        for qstr in qstrings:
            qstring_list.append({
                'qstring': qstr,
                'word_id': id
            })
        id += 1
        word_list.append({
            'id': id,
            'reading': row[1],
            'value': row[3],
        })
        for qstr in qstrings:
            qstring_list.append({
                'qstring': qstr,
                'word_id': id
            })
        id += 1

    qstring_list = sorted(qstring_list, key=lambda x: x['qstring'])

    build_db(output_file, word_list, qstring_list)
