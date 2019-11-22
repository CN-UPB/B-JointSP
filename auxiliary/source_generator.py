from overlay.flow import Flow
from read_write import reader
import random
from fixed.source import Source
import csv
from collections import defaultdict


# input: seed, substrate network, templates, number of sources, constant data rate
seed = 10
random.seed(seed)           # seed set here, then only passed for setting the file-name
network_file = "../Data/abilene/abilene-west.csv"
nodes, links = reader.read_network(network_file)
templates = list()
templates.append(reader.read_template("../Data/templates/bidirectional/video2.csv"))
# templates.append(reader.read_template("../Data/template2.csv"))
# templates.append(reader.read_template("../Data/template3.csv"))
num_sources = 10		# number of sources per template (only matters if place_flows=False)
num_flows = 6			# number of flows per source (or total if place_flows=True)
dr = 1					# flow strength, ie, data rate per flow
# map flows to random nodes (possibly multiple to the same) rather than mapping sources with a fixed #flows?
place_flows = True


# create the flows/sources at random locations
flows = defaultdict(list)
sources = []
for t in templates:
	# place the total number of flows at random locations
	if place_flows:
		# map flows to nodes
		for i in range(num_flows):
			# for each flow, choose a random node and set the given data rate
			node = random.choice(nodes.ids)
			# create flow and store in dict (append to list of flows at current node)
			flows[node].append(Flow("f{}".format(i), dr))

		# create sources at nodes where flows are mapped
		for v in flows.keys():
			if flows[v]:
				sources.append(Source(v, t.source(), flows[v]))

	# place sources at random (but distinct) locations, each with specified number of flows
	else:
		for i in range(num_sources):
			# for each source, choose a random node and set the given data rate
			node = random.choice(nodes.ids)

			# remove the node from nodes to prevent multiple sources at the same node
			nodes.ids.remove(node)

			# create flows
			flows = []
			for f in range(num_flows):
				flow_id = "f{}-{}".format(i, f)
				flows.append(Flow(flow_id, dr))

			# create source
			sources.append(Source(node, t.source(), flows))


# file name: network-sources_templates_number_dr_seed.csv
source_file = network_file[:-4]		# strip off .csv-ending
source_file += "-sources_"
for t in templates:
	source_file += "{}_".format(t.name)
if place_flows:
	source_file += "{}_{}_{}.csv".format(num_flows, dr, seed)
else:
	source_file += "{}_{}_{}_{}.csv".format(num_sources, num_flows, dr, seed)
print("Writing sources to {}".format(source_file))


# write sources to file
with open(source_file, "w", newline="") as csvfile:
	writer = csv.writer(csvfile, delimiter=" ")
	writer.writerow(["# sources: node_id, source component, flows (id, data rate)"])
	for src in sources:
		source_info = [src.location, src.component]
		sourc_str = "{} {} ".format(src.location, src.component)
		for f in src.flows:
			sourc_str += "{} {} ".format(f.id, f.src_dr)
			source_info.extend([f.id, f.src_dr])
		writer.writerow(source_info)
