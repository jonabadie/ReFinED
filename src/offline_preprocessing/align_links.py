import argparse
import ujson as json
import logging
import os
import sys
from typing import Dict, FrozenSet, Set
from tqdm.auto import tqdm
from collections import defaultdict

from offline_preprocessing.preprocessing_utils import DENY_CLASSES

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
LOG = logging.getLogger(__name__)
EXCLUDE_LIST_AND_DISAMBIGUATION_PAGES = True


def main():
    parser = argparse.ArgumentParser(description='Process cleaned Wikipedia, extract links, merge files.')
    parser.add_argument(
        "--processed_clean_wiki_file",
        type=str,
        default='cleaned_output/processed_clean_wiki_file.json',
        help="File path for cleaned wikipedia text with links extracted."
    )
    parser.add_argument(
        "--wikidata_enwiki_file",
        type=str,
        default='output/enwiki.json',
        help="File path for Wikidata site links file."
    )
    parser.add_argument(
        "--subclasses_file",
        type=str,
        default='output/subclass_p279.json',
        help="File path for Wikidata subclasses file."
    )
    parser.add_argument(
        "--instance_of_file",
        type=str,
        default='output/instance_of_p31.json',
        help="File path for Wikidata instance_of (classes) file."
    )
    parser.add_argument(
        "--redirects_file",
        type=str,
        default='wiki_output/redirects.json',
        help="File path for redirects file."
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default='output_aligned',
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
    if os.path.exists(args.output_dir) and os.listdir(args.output_dir) and not args.overwrite_output_dir:
        raise ValueError(f"Output directory ({args.output_dir}) already exists and is not empty. Use "
                         f"--overwrite_output_dir to overwrite.")
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    subclasses, subclasses_reversed = load_subclasses(args.subclasses_file)
    instance_of: Dict[str, Set[str]] = load_instance_of(args.instance_of_file)
    if EXCLUDE_LIST_AND_DISAMBIGUATION_PAGES:
        # list, surnames, redirects, and disambiguation (+ name disambiguation)
        deny_classes = DENY_CLASSES
    else:
        # otherwise exclude all wikimedia internal entities
        # this may discard some useful entities e.g. YouTube (becuase it is an instance of Q72610003)
        deny_classes = set(_explore_class_tree(subclasses_reversed, 'Q17442446', frozenset()))

    redirects: Dict[str, str] = load_redirects(args.redirects_file)
    wikipedia_to_qcode: Dict[str, str] = load_wikipedia_to_qcode(args.wikidata_enwiki_file)
    align_links_to_wikidata(args.processed_clean_wiki_file, args.output_dir, redirects, wikipedia_to_qcode,
                            instance_of, deny_classes, subclasses)


    # def _get_implied_classes(self, direct_classes: FrozenSet[int], remove_self=True) -> FrozenSet[int]:
    #     """
    #     From a set of (direct) classes this method will generate all of the classes that can be implied.
    #     When remove_self is True it means that a class cannot be implied from itself (but it can still be implied
    #     by other of the direct classes).
    #     :param direct_classes: the set of classes for implied classes to be generated from
    #     :param remove_self: when true a classes implication is not reflexive (e.g. human does not imply human)
    #     :return: set of classes that can be implied from direct_classes
    #     """
    #     if remove_self:
    #         all_implied_classes = set()
    #     else:
    #         all_implied_classes = set(direct_classes)
    #
    #     # keep track of the classes that have been explored to prevent work from being repeated
    #     explored_classes = set()
    #     for direct_class in direct_classes:
    #         implied_classes = self._explore_class_tree(direct_class, frozenset(explored_classes))
    #         if remove_self:
    #             implied_classes = implied_classes - {direct_class}
    #
    #         explored_classes.update(implied_classes)
    #         all_implied_classes.update(implied_classes)
    #
    #     return frozenset(all_implied_classes)
    #

# use different dict for other (wrap both in method)
def _explore_class_tree(subclasses_reversed: Dict[str, Set[str]], qcode: str, explored_classes: FrozenSet[str]) \
        -> FrozenSet[str]:
    """
    Recursively explores the class hierarchy (parent classes, parent of parents, etc.)
    Returns all of the explored classes (these are all impliable from the class provided as an argument (evi_class))
    :param qcode: class id for class to explore
    :param explored_classes: the classes impliable from class_id
    :return: a set of classes that are (indirect) direct ancestors of class_id
    """
    # This method will explore evi_class so add it to the explored_classes set to prevent repeating the work
    explored_classes = set(explored_classes)
    explored_classes.add(qcode)
    explored_classes.copy()

    # Base case: Evi class has no super classes so return the explored classes
    if qcode not in subclasses_reversed:
        return frozenset(explored_classes)

    # General case: Explore all unexplored super classes
    for super_class in subclasses_reversed[qcode]:
        if super_class not in explored_classes:
            explored_classes.add(super_class)
            explored_super_classes = _explore_class_tree(subclasses_reversed, super_class, frozenset(explored_classes))
            explored_classes.update(explored_super_classes)
    return frozenset(explored_classes)


def load_instance_of(file_path: str) -> Dict[str, Set[str]]:
    LOG.info('Loading instance_of (classes)')
    instance_of = dict()
    with open(file_path, 'r') as f:
        for line in tqdm(f, total=80e+6, desc='Loading Wikidata instance_of (classes)'):
            line = json.loads(line)
            instance_of[line['qcode']] = set(line['values'])
    LOG.info(f'Loaded instance_of, size = {len(instance_of)}')
    return instance_of


def load_subclasses(file_path: str):
    LOG.info('Loading subclasses')
    subclasses = dict()
    subclasses_reversed = defaultdict(set)
    with open(file_path, 'r') as f:
        for line in tqdm(f, total=2e+6, desc='Loading Wikidata subclasses'):
            line = json.loads(line)
            subclasses[line['qcode']] = line['values']
            for superclass in line['values']:
                subclasses_reversed[superclass].add(line['qcode'])
    LOG.info(f'Loaded subclasses, size = {len(subclasses)}')
    return subclasses, subclasses_reversed


def load_redirects(file_path: str):
    backslash = '\\'
    double_backslash = backslash * 2
    unescape_quotes = lambda string: string.replace(double_backslash, '').replace(backslash, '').replace('&amp;', '&')
    LOG.info('Loading redirects')
    redirects = dict()
    with open(file_path, 'r') as f:
        for line in tqdm(f, total=9e+6, desc='Loading Wikipedia page redirects'):
            line = json.loads(line)
            redirects[unescape_quotes(line['wiki_title'])] = unescape_quotes(line['dest_title'])
    LOG.info(f'Loaded redirects, size = {len(redirects)}')
    return redirects


def load_wikipedia_to_qcode(file_path: str):
    LOG.info('Loading enwiki sitelinks')
    enwiki_to_qcode = dict()
    with open(file_path, 'r') as f:
        for line in tqdm(f, total=9e+6, desc='Loading enwiki sitelinks'):
            line = json.loads(line)
            enwiki_to_qcode[line['values'].replace(' ', '_')] = line['qcode']
    LOG.info(f'Loaded enwiki_to_qcode, size = {len(enwiki_to_qcode)}')
    return enwiki_to_qcode


def align_links_to_wikidata(processed_clean_wiki_file_path: str, output_dir: str, redirects: Dict[str, str],
                            wikipedia_to_qcode: Dict[str, str], instance_of: Dict[str, Set[str]],
                            wikimedia_internal_classes: Set[str], subclasses: Dict[str, Set[str]]):
    aligned_links_file = open(f'{output_dir}/wikitext_aligned_wd.json', 'w')
    with open(processed_clean_wiki_file_path, 'r') as f:
        for line in tqdm(f, total=6e+6):
            line = json.loads(line)
            new_hyperlinks = []
            for hyperlink in line['hyperlinks']:
                wiki_page_title = hyperlink['uri'].replace('&amp;', '&').replace('&lt;', '<') \
                        .replace('&gt;', '>').replace('&le;', '≤').replace('&ge;', '≥')
                wiki_page_title = wiki_page_title[0].upper() + wiki_page_title[1:]
                if wiki_page_title in redirects:
                    wiki_page_title = redirects[wiki_page_title]
                if wiki_page_title in wikipedia_to_qcode:
                    qcode = wikipedia_to_qcode[wiki_page_title]
                    if qcode in instance_of and len(instance_of[qcode] & wikimedia_internal_classes) > 0:
                        # exclude list pages, disambiguation pages, surname pages
                        continue
                    hyperlink['qcode'] = qcode
                    new_hyperlinks.append(hyperlink)
            line['clean_hyperlinks'] = new_hyperlinks
            del line['hyperlinks']
            aligned_links_file.write(json.dumps(line) + '\n')
    aligned_links_file.close()


if __name__ == '__main__':
    main()
