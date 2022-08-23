import bz2
import ujson as json

from tqdm.auto import tqdm
import argparse
import os


def get_triples(entity):
    qcode = entity['id']
    triples = {}
    for pcode, objs in entity['claims'].items():
        # group by pcode -> [list of qcodes]
        for obj in objs:
            if not obj['mainsnak']['datatype'] == 'wikibase-item' or obj['mainsnak']['snaktype'] == 'somevalue' \
                    or 'datavalue' not in obj['mainsnak']:
                continue
            if pcode not in triples:
                triples[pcode] = []
            triples[pcode].append(obj['mainsnak']['datavalue']['value']['id'])
    return {'qcode': qcode, 'triples': triples}


def main():
    parser = argparse.ArgumentParser(description='Build lookup dictionaries from Wikidata JSON dump.')
    parser.add_argument(
        "--dump_file_path",
        default='latest-all.json.bz2',
        type=str,
        help="file path to JSON Wikidata dump file (latest-all.json.bz2)"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default='output',
        help="Directory where the lookups will be stored"
    )
    parser.add_argument(
        "--overwrite_output_dir",
        action="store_true",
        help="Overwrite the content of the output directory"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="mode for testing (only processes first 500 lines)"
    )
    args = parser.parse_args()
    args.output_dir = args.output_dir.rstrip('/')
    number_lines_to_process = 500 if args.test else 1e20
    if os.path.exists(args.output_dir) and os.listdir(args.output_dir) and not args.overwrite_output_dir:
        raise ValueError(f"Output directory ({args.output_dir}) already exists and is not empty. Use "
                         f"--overwrite_output_dir to overwrite.")
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    i = 0
    output_files = {
        'triples': open(f'{args.output_dir}/triples.json', 'w')
    }

    with bz2.open(args.dump_file_path, 'rb') as f:
        for line in tqdm(f, total=50e6):
            i += 1
            if len(line) < 3:
                continue
            line = line.decode('utf-8').rstrip(',\n')
            line = json.loads(line)
            entity_content = get_triples(line)
            qcode = entity_content['qcode']
            triples = entity_content['triples']
            output_files['triples'].write(json.dumps({'qcode': qcode, 'triples': triples}) + '\n')

            if i > number_lines_to_process:
                break

    for file in output_files.values():
        file.close()


if __name__ == '__main__':
    main()
