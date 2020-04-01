#!/usr/bin/env python3

import argparse
import logging
import os
import random

import bjointsp.objective as objective
import bjointsp.read_write.reader as reader
import bjointsp.read_write.writer as writer

from datetime import datetime
from bjointsp.heuristic import control

logger = logging.getLogger('bjointsp')

# set objective for MIP and heuristic
obj = objective.COMBINED


# solve with heuristic; interface to place-emu: triggers placement
# By Default we send the paths to the template_file as well as the source_file, but for being able to parallel run
# multiple instances of BJointSP we want them to be objects. When sending source and template objects we also set
# 'source_template_object' to True so that BJointSP is able to handle the difference
# fixed_vnfs may be a path to a file with fixed VNF instances or a list of dicts (containing the same info)
# optionally, networkx object can be passed directly and is used instead of the referenced network file
# in that case, optionally specify a networkx_cap attribute string to retrieve the current node and link capacity
# print_best = whether or not to print the best overlay found at the end
def place(network_file, template_file, source_file, source_template_object=False, fixed_vnfs=None,
          prev_embedding_file=None, cpu=None, mem=None, dr=None, networkx=None, networkx_cap='cap', write_result=True,
          print_best=True):
    seed = random.randint(0, 9999)
    seed_subfolder = False
    random.seed(seed)

    # set up logging into file Data/logs/heuristic/scenario_timestamp_seed.log
    # logging.disable(logging.CRITICAL)     # disable logging
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    os.makedirs("logs/heuristic/obj{}".format(obj), exist_ok=True)
    logging.basicConfig(filename="logs/heuristic/obj{}/{}_{}_{}.log".format(obj, os.path.basename(network_file)[:-4],
                                                                            timestamp, seed),
                        level=logging.DEBUG, format="%(asctime)s(%(levelname)s):\t%(message)s", datefmt="%H:%M:%S")

    # if a NetworkX object is passed, use that - including all of its capacities, delays, etc
    if networkx is not None:
        nodes, links = reader.read_networkx(networkx, cap=networkx_cap)
    else:
        nodes, links = reader.read_network(network_file, cpu, mem, dr)

    # When 'source_template_object' is True, we would need to read from objects instead of files
    template, source_components = reader.read_template(template_file, template_object=source_template_object,
                                                       return_src_components=True)
    sources = reader.read_sources(source_file, source_components, source_object=source_template_object)

    templates = [template]
    # print(template)
    # exit()
    components = {j for t in templates for j in t.components}
    fixed = []
    if fixed_vnfs is not None:
        fixed = reader.read_fixed_instances(fixed_vnfs, components)
    prev_embedding = {}
    if networkx is not None:
        prev_embedding = reader.read_prev_placement(networkx, templates)
    elif prev_embedding_file is not None:
        prev_embedding = reader.read_prev_embedding(prev_embedding_file, templates, nodes, links)

    input_files = [network_file, template_file, source_file, fixed_vnfs, prev_embedding_file]
    # TODO: support >1 template

    # print("Using seed {}".format(seed))

    logger.info("Starting initial embedding at {}".format(timestamp))
    # print("Initial embedding\n")
    init_time, runtime, obj_value, changed, overlays = control.solve(nodes, links, templates, prev_embedding, sources,
                                                                     fixed, obj, print_best=print_best)
    # If the write_result variable is True we receive the path to a result file
    # If the write_result variable is False we a result dict.
    result = writer.write_heuristic_result(runtime, obj_value, changed, overlays.values(), input_files, obj, nodes,
                                           links, seed, seed_subfolder, write_result, source_template_object)

    return result


def parse_args():
    parser = argparse.ArgumentParser(description="B-JointSP heuristic calculates an optimized placement")
    parser.add_argument("-n", "--network", help="Network input file (.graphml)", required=True, default=None,
                        dest="network")
    parser.add_argument("-t", "--template", help="Template input file (.yaml)", required=True, default=None,
                        dest="template")
    parser.add_argument("-s", "--sources", help="Sources input file (.yaml)", required=True, default=None,
                        dest="sources")
    parser.add_argument("-f", "--fixed", help="Fixed instances input file (.yaml)", required=False, default=None,
                        dest="fixed")
    parser.add_argument("-p", "--prev", help="Previous embedding input file (.yaml)", required=False, default=None,
                        dest="prev")
    return parser.parse_args()


def main():
    args = parse_args()
    place(args.network, args.template, args.sources, fixed_vnfs=args.fixed, prev_embedding_file=args.prev, cpu=10,
          mem=10, dr=50)


if __name__ == '__main__':
    main()
