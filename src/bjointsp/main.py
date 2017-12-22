#!/usr/bin/env python3

import random
import sys
import logging
from datetime import datetime
import os
import bjointsp.read_write.reader as reader
import bjointsp.read_write.writer as writer
from bjointsp.mip import tep_extended
from bjointsp.heuristic import control
import bjointsp.objective as objective


# set objective for MIP and heuristic
obj = objective.COMBINED


# solve with MIP
def mip(scenario):
	nodes, links, templates, sources, fixed, prev_embedding, events = reader.read_scenario(scenario)

	# create sparate folders for different repetitions (for running in parallel)
	if len(sys.argv) >= 4:
		repetition = int(sys.argv[3])
		rep_subfolder = True
		print("Repetition {}".format(repetition))
	else:
		repetition = None
		rep_subfolder = False
	model = tep_extended.solve(nodes, links, templates, prev_embedding, sources, fixed, scenario, obj, rep=repetition)
	writer.write_mip_result(model, scenario, nodes, links, obj, sources, rep=repetition, rep_subfolder=rep_subfolder)


# solve with MIP; optimizing one objective and bounding the others
def pareto(scenario):
	nodes, links, templates, sources, fixed, prev_embedding, events = reader.read_scenario(scenario)

	# get objective and bounds from arguments
	obj = objective.get_objective(sys.argv[3])
	# bounds have to be ordered: over-sub, changed, resources, delay (without the one that's optimized)
	bounds = (float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6]))
	# bounds = (float(sys.argv[4]), float(sys.argv[5]))
	# run with specified objective and bounds
	model = tep_extended.solve(nodes, links, templates, prev_embedding, sources, fixed, scenario, obj, bounds)
	writer.write_mip_result(model, scenario, nodes, links, obj, sources, bounds=bounds)


# solve with heuristic
def heuristic(scenario):
	nodes, links, templates, sources, fixed, prev_embedding, events = reader.read_scenario(scenario)

	# use specified or random seed
	if len(sys.argv) >= 4:
		seed = int(sys.argv[3])
		seed_subfolder = True		# put result in sub-folder of the chosen seed
	else:
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
	writer.write_heuristic_result(init_time, runtime, obj_value, changed, overlays.values(), scenario, obj, -1, "Initial embedding", nodes, links, seed, seed_subfolder, sources)

	# if events exists, update input accordingly and solve again for each event until last event is reached
	event_no = 0
	while events is not None and event_no is not None:
		print("\n------------------------------------------------\n")
		logging.info("\n------------------------------------------------\n")
		logging.info("Embedding event {} at {}".format(event_no, datetime.now().strftime("%Y-%m-%d_%H-%M-%S")))

		new_no, event, templates, sources, fixed = reader.read_event(events, event_no, templates, sources, fixed)
		init_time, runtime, obj_value, changed, overlays = control.solve(nodes, links, templates, overlays, sources, fixed, obj)
		writer.write_heuristic_result(init_time, runtime, obj_value, changed, overlays.values(), scenario, obj, event_no, event, nodes, links, seed, seed_subfolder, sources)
		event_no = new_no


def main():
	if len(sys.argv) < 3:
		print("MIP usage: python main.py mip <scenario> (<repetition>)")
		print("Heuristic usage: python main.py heuristic <scenario> (<seed>)")
		print("Pareto usage: python main.py pareto <scenario> <objective> <bound1> <bound2> <bound3>")
		# print("Pareto usage: python3 main.py pareto <scenario> <objective> <bound1> <bound2>")
		exit(1)
	method = sys.argv[1]
	scenario = sys.argv[2]

	if method == "mip":
		mip(scenario)
	elif method == "pareto":
		pareto(scenario)
	elif method == "heuristic":
		heuristic(scenario)
	else:
		print("Invalid solving method: {}. Use 'mip', 'heuristic', or 'pareto'".format(method))


if __name__ == "__main__":
	main()
