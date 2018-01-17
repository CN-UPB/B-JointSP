#!/usr/bin/env python3

import random
import logging
from datetime import datetime
import os
import bjointsp.read_write.reader as reader
import bjointsp.read_write.writer as writer
from bjointsp.heuristic import control
import bjointsp.objective as objective


# set objective for MIP and heuristic
obj = objective.COMBINED


# solve with heuristic
def heuristic(scenario, graphml_network=False, cpu=None, mem=None, dr=None):
	nodes, links, templates, sources, fixed, prev_embedding, events = reader.read_scenario(scenario, graphml_network, cpu, mem, dr)

	seed = random.randint(0, 9999)
	seed_subfolder = False
	random.seed(seed)
	print("Using seed {}".format(seed))

	# set up logging into file Data/logs/heuristic/scenario_timestamp_seed.log
	# logging.disable(logging.CRITICAL)		# disable logging
	timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
	os.makedirs("logs/heuristic/obj{}".format(obj), exist_ok=True)
	logging.basicConfig(filename="logs/heuristic/obj{}/{}_{}_{}.log".format(obj, os.path.basename(scenario)[:-4], timestamp, seed),
						level=logging.DEBUG, format="%(asctime)s(%(levelname)s):\t%(message)s", datefmt="%H:%M:%S")

	logging.info("Starting initial embedding at {}".format(timestamp))
	print("Initial embedding\n")
	init_time, runtime, obj_value, changed, overlays = control.solve(nodes, links, templates, {}, sources, fixed, obj)
	result = writer.write_heuristic_result(init_time, runtime, obj_value, changed, overlays.values(), scenario, obj, -1, "Initial embedding", nodes, links, seed, seed_subfolder, sources)

	# if events exists, update input accordingly and solve again for each event until last event is reached
	event_no = 0
	while events is not None and event_no is not None:
		print("\n------------------------------------------------\n")
		logging.info("\n------------------------------------------------\n")
		logging.info("Embedding event {} at {}".format(event_no, datetime.now().strftime("%Y-%m-%d_%H-%M-%S")))

		new_no, event, templates, sources, fixed = reader.read_event(events, event_no, templates, sources, fixed)
		init_time, runtime, obj_value, changed, overlays = control.solve(nodes, links, templates, overlays, sources, fixed, obj)
		result = writer.write_heuristic_result(init_time, runtime, obj_value, changed, overlays.values(), scenario, obj, event_no, event, nodes, links, seed, seed_subfolder, sources)
		event_no = new_no

	return result


# TODO: execute heuristic as main; and parse inputs as arguments not as scenario.csv