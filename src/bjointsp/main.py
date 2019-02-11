#!/usr/bin/env python3

import random
import logging
import argparse
from datetime import datetime
import os
import bjointsp.read_write.reader as reader
import bjointsp.read_write.writer as writer
from bjointsp.heuristic import control
import bjointsp.objective as objective


# set objective for MIP and heuristic
obj = objective.COMBINED


# solve with heuristic; interface to place-emu: triggers placement
def place(network_file, template_file, source_file, fixed_file=None, prev_embedding_file=None, cpu=None, mem=None, dr=None):
    seed = random.randint(0, 9999)
    seed_subfolder = False
    random.seed(seed)

    # set up logging into file Data/logs/heuristic/scenario_timestamp_seed.log
    # logging.disable(logging.CRITICAL)     # disable logging
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    os.makedirs("logs/heuristic/obj{}".format(obj), exist_ok=True)
    logging.basicConfig(filename="logs/heuristic/obj{}/{}_{}_{}.log".format(obj, os.path.basename(network_file)[:-4], timestamp, seed),
                        level=logging.DEBUG, format="%(asctime)s(%(levelname)s):\t%(message)s", datefmt="%H:%M:%S")

    nodes, links = reader.read_network(network_file, cpu, mem, dr)
    template, source_components = reader.read_template(template_file, return_src_components=True)
    templates = [template]
    # print(template)
    # exit()
    sources = reader.read_sources(source_file, source_components)
    components = {j for t in templates for j in t.components}
    fixed = []
    if fixed_file is not None:
        fixed = reader.read_fixed_instances(fixed_file, components)
    prev_embedding = {}
    if prev_embedding_file is not None:
        prev_embedding = reader.read_prev_embedding(prev_embedding_file, templates)

    input_files = [network_file, template_file, source_file, fixed_file, prev_embedding_file]
    # TODO: support >1 template

   
    print("Using seed {}".format(seed))


    logging.info("Starting initial embedding at {}".format(timestamp))
    print("Initial embedding\n")
    # TODO: make less verbose or only as verbose when asked for (eg, with -v argument)
    init_time, runtime, obj_value, changed, overlays = control.solve(nodes, links, templates, prev_embedding, sources, fixed, obj)
    result = writer.write_heuristic_result(runtime, obj_value, changed, overlays.values(), input_files, obj, nodes, links, seed, seed_subfolder)

    return result


def parse_args():
    parser = argparse.ArgumentParser(description="B-JointSP heuristic calculates an optimized placement")
    parser.add_argument("-n", "--network", help="Network input file (.graphml)", required=True, default=None, dest="network")
    parser.add_argument("-t", "--template", help="Template input file (.yaml)", required=True, default=None, dest="template")
    parser.add_argument("-s", "--sources", help="Sources input file (.yaml)", required=True, default=None, dest="sources")
    parser.add_argument("-f", "--fixed", help="Fixed instances input file (.yaml)", required=False, default=None, dest="fixed")
    parser.add_argument("-p", "--prev", help="Previous embedding input file (.yaml)", required=False, default=None, dest="prev")
    return parser.parse_args()


def main():
    args = parse_args()
    place(args.network, args.template, args.sources, fixed_file=args.fixed, prev_embedding_file=args.prev, cpu=10, mem=10, dr=50)


if __name__ == '__main__':
    main()
