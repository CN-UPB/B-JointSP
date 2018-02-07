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


# solve with heuristic
def heuristic(network_file, template_file, source_file, graphml_network=False, cpu=None, mem=None, dr=None):
	# nodes, links, templates, sources, fixed, prev_embedding, events = reader.read_scenario(scenario, graphml_network, cpu, mem, dr)
	if graphml_network:
		nodes, links = reader.read_graphml_network(network_file, cpu, mem, dr)
	else:
		nodes, links = reader.read_network(network_file)
	template, source_components = reader.read_template(template_file, return_src_components=True)
	templates = [template]
	sources = reader.read_sources(source_file, source_components)
	fixed = []
	input_files = [network_file, template_file, source_file]
	# TODO: support >1 template
	# TODO: support fixed, prev_embedding, events

	seed = random.randint(0, 9999)
	seed_subfolder = False
	random.seed(seed)
	print("Using seed {}".format(seed))

	# set up logging into file Data/logs/heuristic/scenario_timestamp_seed.log
	# logging.disable(logging.CRITICAL)		# disable logging
	timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
	os.makedirs("logs/heuristic/obj{}".format(obj), exist_ok=True)
	logging.basicConfig(filename="logs/heuristic/obj{}/{}_{}_{}.log".format(obj, os.path.basename(network_file)[:-4], timestamp, seed),
						level=logging.DEBUG, format="%(asctime)s(%(levelname)s):\t%(message)s", datefmt="%H:%M:%S")

	logging.info("Starting initial embedding at {}".format(timestamp))
	print("Initial embedding\n")
	init_time, runtime, obj_value, changed, overlays = control.solve(nodes, links, templates, {}, sources, fixed, obj)
	result = writer.write_heuristic_result(init_time, runtime, obj_value, changed, overlays.values(), input_files, obj, -1, "Initial embedding", nodes, links, seed, seed_subfolder, sources)

	# if events exists, update input accordingly and solve again for each event until last event is reached
	# event_no = 0
	# while events is not None and event_no is not None:
	# 	print("\n------------------------------------------------\n")
	# 	logging.info("\n------------------------------------------------\n")
	# 	logging.info("Embedding event {} at {}".format(event_no, datetime.now().strftime("%Y-%m-%d_%H-%M-%S")))
	#
	# 	new_no, event, templates, sources, fixed = reader.read_event(events, event_no, templates, sources, fixed)
	# 	init_time, runtime, obj_value, changed, overlays = control.solve(nodes, links, templates, overlays, sources, fixed, obj)
	# 	result = writer.write_heuristic_result(init_time, runtime, obj_value, changed, overlays.values(), scenario, obj, event_no, event, nodes, links, seed, seed_subfolder, sources)
	# 	event_no = new_no

	# TODO: wrap result into a result class with all inputs and outputs?
	return result, overlays, templates


def parse_args():
	parser = argparse.ArgumentParser(description="B-JointSP heuristic calculates an optimized placement")
	parser.add_argument("-n", "--network", help="Network input file (.graphml)", required=True, default=None, dest="network")
	parser.add_argument("-t", "--template", help="Template input file (.csv)", required=True, default=None, dest="template")
	parser.add_argument("-s", "--sources", help="Sources input file (.csv)", required=True, default=None, dest="sources")
	return parser.parse_args()


def main():
	args = parse_args()
	# TODO: allow to set cpu, mem, dr as args; or take them from graphml
	heuristic(args.network, args.template, args.sources, graphml_network=True, cpu=10, mem=10, dr=50)


if __name__ == '__main__':
	main()
